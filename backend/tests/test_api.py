import io, openpyxl
from conftest import make_pdf, INVOICE
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app

def up(c, blob, name="inv.pdf"): return c.post("/api/documents/upload", files={"files": (name, blob)})

def test_auth_required():
    c = TestClient(app)
    assert c.get("/api/documents").status_code == 401
    assert c.post("/api/auth/login", json={"email": "no@x.com", "password": "password123"}).status_code == 401

def test_register_validation_and_duplicate():
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"email": "bad", "password": "short"}).status_code == 422
    c.post("/api/auth/register", json={"email": "dup@x.com", "password": "password123"})
    assert c.post("/api/auth/register", json={"email": "dup@x.com", "password": "password123"}).status_code == 409

def test_pdf_extraction_and_validation(authed):
    d = up(authed, make_pdf(INVOICE)).json()[0]
    assert d["status"] == "needs_review" and d["method"] == "pdf-text" and d["provider"] == "rules"
    e = d["extracted"]
    assert e["invoice_number"] == "INV-1001" and e["total"] == 110.0 and e["invoice_date"] == "2026-03-01" and e["currency"] == "USD"
    assert d["warnings"] == []

def test_missing_and_inconsistent(authed):
    bad = [("Total: $999.00" if l.startswith("Total") else l) for l in INVOICE if "Invoice No" not in l]
    d = up(authed, make_pdf(bad)).json()[0]
    assert any("invoice_number" in w for w in d["warnings"]) and any("does not equal" in w for w in d["warnings"])

def test_rejects_bad_files(authed):
    assert "Unsupported" in up(authed, b"MZ evil", "a.pdf").json()[0]["error"]
    assert "Empty" in up(authed, b"").json()[0]["error"]
    assert up(authed, b"%PDF-1.4 garbage").json()[0]["status"] == "failed"

def test_blank_image_fails_honestly(authed):
    buf = io.BytesIO(); Image.new("RGB", (400, 100), "white").save(buf, "PNG")
    d = up(authed, buf.getvalue(), "s.png").json()[0]
    assert d["status"] == "failed" and d["error"]

def test_edit_preserves_original_and_approve(authed):
    d = up(authed, make_pdf(INVOICE)).json()[0]
    r = authed.patch(f"/api/documents/{d['id']}/extraction", json={"corrections": {"customer": "Fixed Co"}}).json()
    assert r["extracted"]["customer"] == "Widget Co" and r["effective"]["customer"] == "Fixed Co"
    assert authed.patch(f"/api/documents/{d['id']}/extraction", json={"corrections": {"hack": "x"}}).status_code == 422
    assert authed.post(f"/api/documents/{d['id']}/approve").json()["status"] == "completed"

def test_isolation(authed):
    d = up(authed, make_pdf(INVOICE)).json()[0]
    o = TestClient(app); o.post("/api/auth/register", json={"email": "other@x.com", "password": "password123"})
    assert o.get(f"/api/documents/{d['id']}").status_code == 404
    assert o.delete(f"/api/documents/{d['id']}").status_code == 404
    assert o.post(f"/api/documents/{d['id']}/approve").status_code == 404
    assert o.get("/api/documents").json()["total"] == 0

def test_export_approved_only_and_formula_injection(authed):
    evil = [INVOICE[0].replace("Acme", "=HYPERLINK(1)")] + INVOICE[1:]
    a = up(authed, make_pdf(evil)).json()[0]; up(authed, make_pdf(INVOICE))
    authed.post(f"/api/documents/{a['id']}/approve")
    csv = authed.get("/api/exports/csv").text
    assert "'=HYPERLINK" in csv and csv.count("INV-1001") == 1
    wb = openpyxl.load_workbook(io.BytesIO(authed.get("/api/exports/xlsx").content))
    assert wb.active["B2"].value.startswith("'=")

def test_dashboard_and_delete(authed):
    d = up(authed, make_pdf(INVOICE)).json()[0]; up(authed, b"%PDF-1.4 garbage")
    authed.post(f"/api/documents/{d['id']}/approve")
    s = authed.get("/api/dashboard/stats").json()
    assert (s["total"], s["completed"], s["failed"]) == (2, 1, 1) and "Estimate" in s["estimate_note"]
    assert authed.delete(f"/api/documents/{d['id']}").status_code == 204

def test_groq_provider_down_falls_back(authed, monkeypatch):
    from app import config, extract
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(extract, "groq_extract", lambda text: None)
    d = up(authed, make_pdf(INVOICE)).json()[0]
    assert d["provider"] == "rules" and any("Groq API was unavailable" in w for w in d["warnings"])

def test_preview_is_owner_only_and_safe(authed):
    d = up(authed, make_pdf(INVOICE)).json()[0]
    r = authed.get(f"/api/documents/{d['id']}/file")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.headers["x-content-type-options"] == "nosniff"
    o = TestClient(app); assert o.get(f"/api/documents/{d['id']}/file").status_code == 401
    o.post("/api/auth/register", json={"email": "snoop@x.com", "password": "password123"})
    assert o.get(f"/api/documents/{d['id']}/file").status_code == 404

def test_system_status_and_spa(authed, tmp_path, monkeypatch):
    s = authed.get("/api/system/status").json()
    assert s["ai_configured"] is False and s["ai_provider"] == "Rules-based fallback" and "ocr_available" in s
    import app.main as m
    (tmp_path / "index.html").write_text("<div id=root></div>"); monkeypatch.setattr(m, "DIST", tmp_path)
    c = TestClient(app)
    assert "root" in c.get("/app/documents").text and c.get("/api/nope").status_code == 404
    assert c.get("/../../etc/passwd").status_code in (200, 404) and "root:" not in c.get("/%2e%2e/%2e%2e/etc/passwd").text


def test_groq_extraction_validates_structured_response(monkeypatch):
    from app import config, extract
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": '{"supplier":"Acme Supplies Ltd","invoice_number":"INV-1001","invoice_date":"2026-03-01","due_date":"2026-03-31","customer":"Widget Co","currency":"USD","subtotal":100,"tax":10,"total":110}'}}]}
    monkeypatch.setattr(extract.httpx, "post", lambda *args, **kwargs: FakeResponse())
    data = extract.groq_extract("Invoice No: INV-1001")
    assert data["invoice_number"] == "INV-1001" and data["total"] == 110


def test_cross_origin_mutation_is_rejected(authed):
    response = authed.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_plain_frontend_assets_are_served():
    c = TestClient(app)
    page = c.get("/")
    assert page.status_code == 200 and "FlowPilot" in page.text and "app.js" in page.text
    css = c.get("/styles.css")
    js = c.get("/app.js")
    assert css.status_code == 200 and "--green" in css.text
    assert js.status_code == 200 and "Groq" in js.text
    assert c.get("/api").status_code == 404


def test_non_invoice_document_uses_general_fields_without_tax_warnings(authed, monkeypatch):
    from app import extract
    text = ["ASSIGNMENT 1", "Q1. Explain the five phases of open-source contribution.", "Introduction", "Conclusion"]
    d = up(authed, make_pdf(text), "assignment.pdf").json()[0]
    assert d["document_type"] == "assignment"
    assert "tax" not in d["extracted"] and "total" not in d["extracted"]
    assert d["warnings"] == []
    assert "document_summary" in d["extracted"]


def test_document_classifier_does_not_force_invoice_schema():
    from app import extract
    assert extract.detect_document_type("ASSIGNMENT 1\nQ1. Explain the topic.\nIntroduction\nConclusion") == "assignment"
    assert extract.validate({"_document_type": "assignment"}) == []
