import os, tempfile
_t = tempfile.mkdtemp()
os.environ.update(FP_DB_URL=f"sqlite:///{_t}/t.db", FP_UPLOAD_DIR=f"{_t}/up", GROQ_API_KEY="")
import fitz, pytest
from fastapi.testclient import TestClient
from app.main import app

INVOICE = ["Acme Supplies Ltd", "Invoice No: INV-1001", "Invoice Date: 2026-03-01", "Due Date: 2026-03-31",
           "Bill To: Widget Co", "Subtotal: $100.00", "Tax: $10.00", "Total: $110.00"]

def make_pdf(lines):
    d = fitz.open(); p = d.new_page(); y = 72
    for l in lines: p.insert_text((72, y), l); y += 18
    return d.tobytes()

@pytest.fixture
def client(): return TestClient(app)
_n = [0]
@pytest.fixture
def authed():
    _n[0] += 1
    c = TestClient(app); c.post("/api/auth/register", json={"email": f"u{_n[0]}@x.com", "password": "password123"}); return c
