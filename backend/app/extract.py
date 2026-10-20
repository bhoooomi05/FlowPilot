import json
import re
import shutil
import io
from datetime import datetime
from typing import Optional

import httpx
from pydantic import BaseModel, ValidationError, ConfigDict
from . import config


class ExtractError(Exception):
    pass


class Invoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    supplier: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    customer: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None


REQUIRED = ["supplier", "invoice_number", "invoice_date", "total"]
FIELDS = set(Invoice.model_fields)
GENERAL_FIELDS = {"document_title", "document_summary", "document_date", "reference_number"}


def detect_document_type(text):
    """Conservatively classify text before choosing a field schema."""
    content = (text or "").lower()
    if not content.strip():
        return "unknown"
    sample = content[:10000]
    scores = {
        "invoice": sum(bool(re.search(p, sample)) for p in [
            r"\btax invoice\b", r"\binvoice\s*(?:number|no\.?|#|id)\b",
            r"\binvoice\b", r"\bsubtotal\b", r"\bamount due\b",
            r"\bbill to\b", r"\bpayment terms\b", r"\btotal due\b",
        ]),
        "receipt": sum(bool(re.search(p, sample)) for p in [r"\breceipt\b", r"\bchange due\b", r"\bpaid\b", r"\btransaction id\b"]),
        "assignment": sum(bool(re.search(p, sample)) for p in [r"\bassignment\b", r"\bq\s*\d+\b", r"\bquestion\s*\d+\b", r"\bmarks?\b", r"\bsubmission\b"]),
        "report": sum(bool(re.search(p, sample)) for p in [r"\bexecutive summary\b", r"\bannual report\b", r"\bfindings\b", r"\brecommendations\b"]),
        "form": sum(bool(re.search(p, sample)) for p in [r"\bapplication form\b", r"\bplease fill\b", r"\bdate of birth\b", r"\bapplicant name\b"]),
    }
    # Prefer clear invoice/receipt evidence, but don't classify an academic/report PDF
    # as an invoice just because the word appears somewhere in its text.
    if scores["invoice"] >= 2 and scores["invoice"] >= max(scores["receipt"], scores["assignment"], scores["report"], scores["form"]):
        return "invoice"
    if scores["receipt"] >= 2 and scores["receipt"] > scores["invoice"]:
        return "receipt"
    other = max((k for k in scores if k not in ("invoice", "receipt")), key=lambda k: scores[k])
    if scores[other] >= 2:
        return "assignment" if other == "assignment" else other
    return "general_document"


def groq_general_extract(text, document_type):
    """Extract neutral summary fields for non-invoice documents."""
    prompt = (
        "Extract general document metadata from the text. Return JSON with exactly these keys: "
        "document_title, document_summary, document_date, reference_number. "
        "Use null when not clearly present. document_summary must be at most 3 concise sentences. "
        "Do not infer tax, subtotal, total, or invoice fields. Do not invent values. "
        f"Detected document type: {document_type}.\n\nDOCUMENT TEXT:\n{text[:14000]}"
    )
    payload = _groq_json(prompt, max_tokens=700)
    if payload is None:
        return None
    return {key: payload.get(key) for key in GENERAL_FIELDS if payload.get(key) not in (None, "")}


def _ocr(img):
    if not shutil.which("tesseract"):
        raise ExtractError("OCR is needed for this file, but Tesseract is not installed or is not on PATH")
    import pytesseract
    return pytesseract.image_to_string(img)


def read_text(path, mime):
    """Read embedded PDF text first; use Tesseract only when OCR is needed."""
    from PIL import Image
    if mime == "application/pdf":
        import fitz
        try:
            d = fitz.open(path)
        except Exception as exc:
            raise ExtractError("PDF is corrupted or unreadable") from exc
        if d.needs_pass:
            raise ExtractError("PDF is encrypted")
        if d.page_count == 0:
            raise ExtractError("PDF is empty")
        if d.page_count > config.MAX_PAGES:
            raise ExtractError(f"PDF exceeds the {config.MAX_PAGES}-page limit")
        text = "\n".join(p.get_text() for p in d)
        if len(text.strip()) >= 20:
            return text, "pdf-text"
        out = []
        for p in d:
            pix = p.get_pixmap(dpi=200)
            out.append(_ocr(Image.open(io.BytesIO(pix.tobytes("png")))))
        return "\n".join(out), "ocr"
    try:
        return _ocr(Image.open(path)), "ocr"
    except ExtractError:
        raise
    except Exception as exc:
        raise ExtractError("Image is corrupted or unreadable") from exc


def _num(s):
    m = re.findall(r"\d[\d,]*\.?\d*", s)
    try:
        return float(m[-1].replace(",", "")) if m else None
    except ValueError:
        return None


def _date(s):
    s = s.strip().rstrip(".")
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    return None


def rules_extract(text):
    """Extract common invoice layouts using conservative label-based rules.

    Supports values on the same line or the following line, common date labels,
    and common amount labels. It intentionally does not guess missing fields.
    """
    d = {}
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    full = "\n".join(lines)

    def value_after_label(labels):
        pattern = re.compile(
            r"(?:^|\n)\s*(?:" + "|".join(labels) + r")\s*[:#\-]?\s*(.*?)\s*(?=\n|$)",
            re.I,
        )
        match = pattern.search(full)
        if match and match.group(1).strip():
            value = match.group(1).strip(" :#-\t")
            if value and not re.fullmatch(r"(?:date|number|no\.?|amount|total|due|invoice)", value, re.I):
                return value
        if match:
            following = full[match.end():].splitlines()
            if following and following[0].strip():
                return following[0].strip()
        return None

    supplier = value_after_label([r"supplier(?:\s+name)?", r"vendor(?:\s+name)?", r"from"])
    if supplier:
        d["supplier"] = supplier
    else:
        # Typical invoices put the supplier/company name in the first few lines.
        for line in lines[:5]:
            low = line.lower()
            if not re.search(r"invoice|bill to|ship to|date|www\.|@|\b(?:gstin|tax id)\b", low) and not re.fullmatch(r"[\d\W]+", line):
                d["supplier"] = line
                break

    invoice_no = value_after_label([r"invoice\s*(?:no\.?|number|#|id)", r"invoice#", r"inv\.?\s*(?:no\.?|#)"])
    if invoice_no:
        d["invoice_number"] = re.split(r"\s{2,}|\s+(?:invoice date|date)\b", invoice_no, flags=re.I)[0].strip()
    else:
        m = re.search(r"\b(?:invoice\s*(?:no\.?|number|#)|invoice#|inv\.?\s*no\.?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/_-]{2,})", full, re.I)
        if m:
            d["invoice_number"] = m.group(1)

    date_pattern = r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\.\d{1,2}\.\d{2,4}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})"
    for key, labels in (("invoice_date", r"invoice\s+date|date\s+of\s+invoice|issued\s+on|billing\s+date"), ("due_date", r"due\s+date|payment\s+due|due\s+by|pay\s+by")):
        m = re.search(r"(?:" + labels + r")\s*[:#\-]?\s*" + date_pattern, full, re.I)
        if not m:
            # Some PDFs place the date on the line after its label.
            m = re.search(r"(?:^|\n)\s*(?:" + labels + r")\s*[:#\-]?\s*(?:\n\s*)?" + date_pattern, full, re.I)
        if m:
            normalized = _date(m.group(1))
            if normalized:
                d[key] = normalized

    # Many basic templates use only "Date:" for the invoice date.
    if not d.get("invoice_date"):
        m = re.search(r"(?:^|\n)\s*date\s*[:#\-]?\s*" + date_pattern, full, re.I)
        if m:
            normalized = _date(m.group(1))
            if normalized:
                d["invoice_date"] = normalized

    customer = value_after_label([r"bill\s+to", r"billed\s+to", r"customer(?:\s+name)?", r"client(?:\s+name)?"])
    if customer:
        d["customer"] = customer

    amount_patterns = {
        "subtotal": r"sub\s*total|net\s+amount|amount\s+before\s+tax",
        "tax": r"(?:total\s+)?(?:tax|vat|gst|sales\s+tax)(?:\s*\(?\s*\d+(?:\.\d+)?\s*%\s*\)?)?",
        "total": r"grand\s+total|total\s+due|amount\s+due|balance\s+due|invoice\s+total|total\s+amount|total",
    }
    for key, label_pattern in amount_patterns.items():
        # Prefer the most specific amount label and accept currency symbols/codes.
        matches = list(re.finditer(r"(?:^|\n)\s*(?:" + label_pattern + r")\s*[:\-]?\s*(?:INR|USD|EUR|GBP|₹|\$|€|£)?\s*([\d][\d,]*(?:\.\d{1,2})?)", full, re.I))
        if matches:
            m = matches[-1] if key == "total" else matches[0]
            d[key] = _num(m.group(1))

    currencies = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}
    match = re.search(r"\b(USD|EUR|GBP|INR)\b|([$€£₹])", full, re.I)
    if match:
        d["currency"] = (match.group(1) or currencies[match.group(2)]).upper()
    return d


def _groq_json(prompt, max_tokens=1200):
    """Call Groq and return a JSON object, logging safe diagnostics on failure."""
    if not config.GROQ_API_KEY:
        print("Groq is not configured: GROQ_API_KEY is empty.")
        return None

    try:
        response = httpx.post(
            config.GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.GROQ_MODEL,
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extract structured information from the provided document. "
                            "Return one valid JSON object only. Never invent missing values."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=httpx.Timeout(45.0, connect=10.0),
        )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Keep the key private. The API response body usually explains model,
            # authentication, permission, or quota errors.
            print(
                f"Groq API error: HTTP {exc.response.status_code}; "
                f"response: {exc.response.text[:1200]}"
            )
            return None

        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            print("Groq response error: response content was empty.")
            return None

        content = re.sub(
            r"^\s*```(?:json)?\s*|\s*```\s*$",
            "",
            content.strip(),
            flags=re.IGNORECASE,
        )
        payload = json.loads(content)
        if not isinstance(payload, dict):
            print("Groq response error: JSON response was not an object.")
            return None
        return payload

    except httpx.TimeoutException as exc:
        print(f"Groq timeout: {type(exc).__name__}")
    except httpx.RequestError as exc:
        print(f"Groq connection error: {type(exc).__name__}: {exc}")
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Groq response parsing error: {type(exc).__name__}: {exc}")
    except Exception as exc:
        print(f"Unexpected Groq integration error: {type(exc).__name__}: {exc}")

    return None


def groq_extract(text):
    """Extract invoice fields with Groq; return None for honest rules fallback."""
    prompt = (
        "Extract invoice fields from the supplied document text. Return one JSON object "
        "with these keys: supplier, invoice_number, invoice_date, due_date, customer, "
        "currency, subtotal, tax, total. Use ISO YYYY-MM-DD dates when unambiguous; "
        "use null for missing or ambiguous values. Amounts must be JSON numbers, not "
        "strings. Do not invent values.\n\nDOCUMENT TEXT:\n" + text[:12000]
    )
    payload = _groq_json(prompt, max_tokens=1200)
    if payload is None:
        return None

    try:
        payload = {key: value for key, value in payload.items() if key in FIELDS}
        parsed = Invoice.model_validate(payload).model_dump(exclude_none=True)
        for key in ("invoice_date", "due_date"):
            if parsed.get(key):
                parsed[key] = _date(str(parsed[key])) or parsed[key]
        for key in ("subtotal", "tax", "total"):
            if parsed.get(key) is not None:
                parsed[key] = float(parsed[key])
        return parsed
    except (ValidationError, ValueError, TypeError) as exc:
        print(f"Groq invoice validation error: {type(exc).__name__}: {exc}")
        return None

def validate(data):
    document_type = data.get("_document_type", "invoice")
    if document_type != "invoice":
        return []
    warnings = [f"Missing required field: {key}" for key in REQUIRED if data.get(key) in (None, "")]
    subtotal, tax, total = data.get("subtotal"), data.get("tax"), data.get("total")
    if None not in (subtotal, tax, total) and abs(subtotal + tax - total) > 0.01:
        warnings.append(f"Subtotal + tax ({subtotal + tax:.2f}) does not equal total ({total:.2f})")
    if data.get("invoice_date") and data.get("due_date") and data["due_date"] < data["invoice_date"]:
        warnings.append("Due date is before invoice date")
    return warnings


def run(path, mime):
    text, method = read_text(path, mime)
    if not text.strip():
        raise ExtractError("No text could be extracted")
    document_type = detect_document_type(text)
    if document_type == "invoice":
        data = groq_extract(text)
        provider, warnings = "groq", []
        if data is None:
            provider = "rules"
            if config.GROQ_API_KEY:
                warnings.append("Groq API was unavailable or returned invalid output; rules-based invoice extraction was used")
            data = {key: value for key, value in rules_extract(text).items() if value is not None}
    else:
        data = groq_general_extract(text, document_type)
        provider, warnings = "groq", []
        if data is None:
            provider = "rules"
            # Safe fallback: provide a short text excerpt rather than inventing invoice values.
            clean = re.sub(r"\s+", " ", text).strip()
            data = {"document_summary": clean[:700]} if clean else {}
            if config.GROQ_API_KEY:
                warnings.append("AI summary was unavailable; a text excerpt is shown instead")
    data["_document_type"] = document_type
    return data, method, provider, warnings + validate(data)


def groq_custom_extract(text, requested_fields):
    """Extract custom fields, tolerating key casing and whitespace differences."""
    if not requested_fields:
        return {}

    prompt = (
        "Extract values from the source document text. Return one valid JSON object only. "
        "Use the requested field names as JSON keys. If a value is absent or ambiguous, "
        "return null. Never infer or fabricate values.\nRequested fields: "
        + json.dumps(requested_fields, ensure_ascii=False)
        + "\n\nDOCUMENT TEXT:\n"
        + text[:14000]
    )
    payload = _groq_json(prompt, max_tokens=1000)
    if payload is None:
        print("Custom-field extraction failed: Groq returned no usable JSON. See the preceding diagnostic.")
        return None

    normalized = {str(key).strip().casefold(): value for key, value in payload.items()}
    result = {}
    for field in requested_fields:
        result[field] = normalized.get(str(field).strip().casefold())
        if isinstance(result[field], str):
            result[field] = result[field].strip() or None

    populated = sum(value is not None for value in result.values())
    print(f"Custom-field extraction returned {populated}/{len(result)} populated field(s).")
    return result

