import io
import pandas as pd

COLS = ["supplier", "invoice_number", "invoice_date", "due_date", "customer", "currency", "subtotal", "tax", "total", "document_title", "document_summary", "document_date", "reference_number"]

def safe(v):
    """Neutralise spreadsheet formula injection in untrusted strings."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v

def frame(docs):
    # Include user-requested fields alongside standard invoice fields.
    custom_columns = []
    prepared = []
    for d in docs:
        values = d.effective()
        for key in values:
            if key.startswith("custom:") and key not in custom_columns:
                custom_columns.append(key)
        prepared.append((d, values))
    rows = []
    for d, values in prepared:
        row = {"document": safe(d.original_name)}
        row.update({c: safe(values.get(c)) for c in COLS})
        row.update({c.removeprefix("custom:"): safe(values.get(c)) for c in custom_columns})
        rows.append(row)
    return pd.DataFrame(rows, columns=["document"] + COLS + [c.removeprefix("custom:") for c in custom_columns])

def to_csv(docs):
    return frame(docs).to_csv(index=False).encode("utf-8-sig")

def to_xlsx(docs):
    b = io.BytesIO()
    frame(docs).to_excel(b, index=False, engine="openpyxl")
    return b.getvalue()
