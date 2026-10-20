import json, secrets, hashlib, hmac, uuid
from datetime import timedelta
from fastapi.responses import FileResponse
from urllib.parse import urlsplit
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Response, Request, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.orm import Session as DB
from . import config, extract, export
from .db import Base, engine, SessionLocal, User, Session, Document, now

config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(engine)  # TODO: Alembic migrations for production
app = FastAPI(title="FlowPilot AI")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + "$" + hashlib.scrypt(pw.encode(), salt=salt.encode(), n=2**14, r=8, p=1).hex()

def check_pw(pw, stored):
    return hmac.compare_digest(hash_pw(pw, stored.split("$")[0]), stored)

th = lambda t: hashlib.sha256(t.encode()).hexdigest()

def current_user(request: Request, db: DB = Depends(get_db)):
    tok = request.cookies.get("fp_session")
    s = db.get(Session, th(tok)) if tok else None
    if not s or s.expires_at.replace(tzinfo=now().tzinfo) < now():
        raise HTTPException(401, "Not authenticated")
    return db.get(User, s.user_id)

class Creds(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    password: str = Field(min_length=8, max_length=128)

def issue(db, user, resp):
    tok = secrets.token_urlsafe(32)
    db.add(Session(token_hash=th(tok), user_id=user.id, expires_at=now() + timedelta(days=7))); db.commit()
    resp.set_cookie("fp_session", tok, httponly=True, samesite="lax", secure=config.COOKIE_SECURE, max_age=7 * 86400)
    return {"email": user.email}

@app.get("/health")
def health(): return {"status": "ok"}

@app.post("/api/auth/register", status_code=201)
def register(c: Creds, resp: Response, db: DB = Depends(get_db)):
    email = c.email.lower()
    if db.scalar(select(User).where(User.email == email)): raise HTTPException(409, "Email already registered")
    u = User(email=email, password_hash=hash_pw(c.password)); db.add(u); db.commit()
    return issue(db, u, resp)

@app.post("/api/auth/login")
def login(c: Creds, resp: Response, db: DB = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == c.email.lower()))
    if not u or not check_pw(c.password, u.password_hash): raise HTTPException(401, "Invalid email or password")
    return issue(db, u, resp)

@app.post("/api/auth/logout")
def logout(request: Request, resp: Response, db: DB = Depends(get_db)):
    tok = request.cookies.get("fp_session")
    if tok and (s := db.get(Session, th(tok))): db.delete(s); db.commit()
    resp.delete_cookie("fp_session"); return {"ok": True}

@app.get("/api/auth/me")
def me(u: User = Depends(current_user)): return {"id": u.id, "email": u.email}

def ser(d: Document):
    raw_extracted = json.loads(d.extracted)
    raw_effective = d.effective()
    document_type = raw_extracted.get("_document_type", "invoice")
    extracted = {k: v for k, v in raw_extracted.items() if k != "_document_type"}
    effective = {k: v for k, v in raw_effective.items() if k != "_document_type"}
    return {"id": d.id, "name": d.original_name, "status": d.status, "mime": d.mime, "size": d.size, "method": d.method, "provider": d.provider,
            "document_type": document_type, "extracted": extracted, "corrected": json.loads(d.corrected), "effective": effective,
            "warnings": json.loads(d.warnings), "error": d.error, "approved": d.approved,
            "created_at": d.created_at, "processed_at": d.processed_at}

def owned(db, u, id):
    d = db.get(Document, id)
    if not d or d.user_id != u.id: raise HTTPException(404, "Document not found")
    return d

MAGIC = {b"%PDF": "application/pdf", b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg"}

def process(db, d):
    d.status, d.error = "processing", ""; db.commit()
    try:
        data, method, provider, warns = extract.run(config.UPLOAD_DIR / d.stored_name, d.mime)
        d.extracted, d.method, d.provider, d.warnings = json.dumps(data), method, provider, json.dumps(warns)
        d.status = "needs_review"
    except extract.ExtractError as e:
        d.status, d.error = "failed", str(e)
    except Exception:
        d.status, d.error = "failed", "Unexpected processing error"
    d.processed_at = now(); db.commit()

@app.post("/api/documents/upload", status_code=201)
async def upload(files: list[UploadFile] = File(...), u: User = Depends(current_user), db: DB = Depends(get_db)):
    out = []
    for f in files:
        blob = await f.read(config.MAX_BYTES + 1)
        if not blob: out.append({"name": f.filename, "error": "Empty file"}); continue
        if len(blob) > config.MAX_BYTES: out.append({"name": f.filename, "error": "File too large"}); continue
        mime = next((m for k, m in MAGIC.items() if blob.startswith(k)), None)
        if not mime: out.append({"name": f.filename, "error": "Unsupported file type (PDF, PNG, JPEG only)"}); continue
        stored = uuid.uuid4().hex  # random server-side name; original name never used as a path
        (config.UPLOAD_DIR / stored).write_bytes(blob)
        d = Document(user_id=u.id, original_name=(f.filename or "file")[:255], stored_name=stored, mime=mime, size=len(blob))
        db.add(d); db.commit(); process(db, d)  # synchronous in MVP
        out.append(ser(d))
    return out

@app.get("/api/documents")
def list_docs(status: str | None = None, q: str | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
              u: User = Depends(current_user), db: DB = Depends(get_db)):
    s = select(Document).where(Document.user_id == u.id)
    if status: s = s.where(Document.status == status)
    if q: s = s.where(Document.original_name.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(s.subquery()))
    rows = db.scalars(s.order_by(Document.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "page": page, "items": [ser(d) for d in rows]}

@app.get("/api/documents/{id}")
def get_doc(id: int, u: User = Depends(current_user), db: DB = Depends(get_db)): return ser(owned(db, u, id))

@app.delete("/api/documents/{id}", status_code=204)
def delete_doc(id: int, u: User = Depends(current_user), db: DB = Depends(get_db)):
    d = owned(db, u, id); (config.UPLOAD_DIR / d.stored_name).unlink(missing_ok=True); db.delete(d); db.commit()

@app.post("/api/documents/{id}/process")
def reprocess(id: int, u: User = Depends(current_user), db: DB = Depends(get_db)):
    d = owned(db, u, id)
    if d.status == "processing": raise HTTPException(409, "Already processing")
    d.approved = False; process(db, d); return ser(d)

class Patch(BaseModel):
    corrections: dict[str, str | float | None]
    @field_validator("corrections")
    @classmethod
    def known(cls, v):
        bad = {key for key in v if key not in set(export.COLS) and not key.startswith("custom:")}
        if bad: raise ValueError(f"Unknown fields: {sorted(bad)}")
        return v

@app.get("/api/documents/{id}/extraction")
def get_ext(id: int, u: User = Depends(current_user), db: DB = Depends(get_db)): return ser(owned(db, u, id))

@app.patch("/api/documents/{id}/extraction")
def patch_ext(id: int, p: Patch, u: User = Depends(current_user), db: DB = Depends(get_db)):
    d = owned(db, u, id)
    if d.status == "failed": raise HTTPException(409, "Cannot edit a failed document; retry processing")
    d.corrected = json.dumps({**json.loads(d.corrected), **p.corrections})  # original extraction left intact
    d.warnings = json.dumps(extract.validate(d.effective())); d.approved = False; d.status = "needs_review"; db.commit()
    return ser(d)

@app.post("/api/documents/{id}/approve")
def approve(id: int, u: User = Depends(current_user), db: DB = Depends(get_db)):
    d = owned(db, u, id)
    if d.status not in ("needs_review", "completed"): raise HTTPException(409, "Document is not ready for approval")
    d.approved, d.status = True, "completed"; db.commit(); return ser(d)

@app.post("/api/documents/{id}/reject")
def reject(id: int, u: User = Depends(current_user), db: DB = Depends(get_db)):
    d = owned(db, u, id); d.approved, d.status = False, "needs_review"; db.commit(); return ser(d)

def approved_docs(db, u, ids):
    s = select(Document).where(Document.user_id == u.id, Document.approved.is_(True))
    if ids: s = s.where(Document.id.in_([int(i) for i in ids.split(",") if i.strip().isdigit()]))
    return db.scalars(s.order_by(Document.id)).all()

@app.get("/api/exports/csv")
def exp_csv(ids: str | None = None, u: User = Depends(current_user), db: DB = Depends(get_db)):
    return Response(export.to_csv(approved_docs(db, u, ids)), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=flowpilot.csv"})

@app.get("/api/exports/xlsx")
def exp_xlsx(ids: str | None = None, u: User = Depends(current_user), db: DB = Depends(get_db)):
    return Response(export.to_xlsx(approved_docs(db, u, ids)),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=flowpilot.xlsx"})

@app.get("/api/documents/{id}/export.xlsx")
def export_single_document(id: int, u: User = Depends(current_user), db: DB = Depends(get_db)):
    """Download one approved document as its own Excel workbook."""
    d = owned(db, u, id)
    if d.status == "failed":
        raise HTTPException(409, "This document has no usable extraction. Reprocess it before exporting")
    from pathlib import Path
    stem = Path(d.original_name).stem
    stem = "".join(ch for ch in stem if ch.isalnum() or ch in "-_ ").strip()[:150] or "document"
    return Response(
        export.to_xlsx([d]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"', "Cache-Control": "private, no-store"},
    )

class CustomExtractRequest(BaseModel):
    fields: list[str] = Field(min_length=1, max_length=12)

@app.post("/api/documents/{id}/custom-extract")
def custom_extract(id: int, payload: CustomExtractRequest, u: User = Depends(current_user), db: DB = Depends(get_db)):
    """Use the configured Groq model to extract user-defined fields from this source document."""
    d = owned(db, u, id)
    cleaned = []
    for label in payload.fields:
        label = " ".join(str(label).split()).strip()
        if not label or len(label) > 60:
            raise HTTPException(422, "Each custom field must be 1–60 characters")
        if label.lower() not in [x.lower() for x in cleaned]:
            cleaned.append(label)
    if not config.GROQ_API_KEY:
        raise HTTPException(503, "Custom AI extraction requires GROQ_API_KEY in your .env file")
    try:
        text, _method = extract.read_text(config.UPLOAD_DIR / d.stored_name, d.mime)
        values = extract.groq_custom_extract(text, cleaned)
    except extract.ExtractError as exc:
        raise HTTPException(422, str(exc)) from exc
    if values is None:
        raise HTTPException(502, "The AI provider could not return valid custom-field results. Try again or enter values manually.")
    updates = {f"custom:{label}": values.get(label) for label in cleaned}
    d.corrected = json.dumps({**json.loads(d.corrected), **updates})
    d.approved = False
    d.status = "needs_review"
    d.warnings = json.dumps(extract.validate(d.effective()))
    db.commit()
    return ser(d)

@app.get("/api/jobs")
def jobs(u: User = Depends(current_user), db: DB = Depends(get_db)):
    rows = db.scalars(select(Document).where(Document.user_id == u.id).order_by(Document.created_at.desc()).limit(50)).all()
    return [{"id": d.id, "name": d.original_name, "status": d.status, "error": d.error, "processed_at": d.processed_at} for d in rows]

@app.get("/api/dashboard/stats")
def stats(u: User = Depends(current_user), db: DB = Depends(get_db)):
    c = dict(db.execute(select(Document.status, func.count()).where(Document.user_id == u.id).group_by(Document.status)).all())
    done = c.get("completed", 0)
    return {"total": sum(c.values()), "needs_review": c.get("needs_review", 0), "completed": done, "failed": c.get("failed", 0),
            "estimated_minutes_saved": done * 5, "estimate_note": "Estimate: assumes 5 minutes of manual entry per approved document"}


@app.get("/api/documents/{id}/file")
def preview(id: int, u: User = Depends(current_user), db: DB = Depends(get_db)):
    """Owner-only inline preview. Content type comes from validated magic bytes, never from the client."""
    d = owned(db, u, id)
    p = (config.UPLOAD_DIR / d.stored_name).resolve()
    if config.UPLOAD_DIR not in p.parents or not p.is_file(): raise HTTPException(404, "File no longer available")
    return FileResponse(p, media_type=d.mime, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
                        "Content-Disposition": "inline; filename=document"})

@app.get("/api/system/status")
def system_status(u: User = Depends(current_user)):
    import shutil
    return {
        "ocr_available": bool(shutil.which("tesseract")),
        "ai_configured": bool(config.GROQ_API_KEY),
        "ai_provider": "Groq" if config.GROQ_API_KEY else "Rules-based fallback",
        "ai_model": config.GROQ_MODEL if config.GROQ_API_KEY else None,
        "max_mb": config.MAX_BYTES // (1024 * 1024),
        "max_pages": config.MAX_PAGES,
    }

# Same-origin browser API: reject cross-origin state-changing requests when an
# Origin header is present. Requests without Origin remain usable for CLI/tests.
@app.middleware("http")
async def security_headers_and_origin_check(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        host = request.headers.get("host", "").lower()
        if origin:
            try:
                origin_host = urlsplit(origin).netloc.lower()
            except ValueError:
                origin_host = ""
            if not origin_host or origin_host != host:
                return Response("Cross-origin request rejected", status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response

# Serve the plain HTML/CSS/JavaScript frontend and API from one origin.
from pathlib import Path
DIST = config.FRONTEND_DIR

@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path == "api" or path.startswith(("api/", "docs", "openapi", "health")) or not (DIST / "index.html").exists():
        raise HTTPException(404, "Not found")
    root = DIST.resolve()
    requested = (root / path).resolve() if path else root / "index.html"
    if path and root in requested.parents and requested.is_file():
        return FileResponse(requested)
    if path and (".." in Path(path).parts or path.startswith(("/", "\\"))):
        raise HTTPException(404, "Not found")
    return FileResponse(root / "index.html")
