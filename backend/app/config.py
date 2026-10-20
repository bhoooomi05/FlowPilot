import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)

# Render and other platforms may supply DATABASE_URL. Prefer the explicit
# FlowPilot variable, while accepting common PostgreSQL URL formats.
DB_URL = os.getenv("FP_DB_URL") or os.getenv("DATABASE_URL") or "sqlite:///./flowpilot.db"
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DB_URL.startswith("postgresql://"):
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)

UPLOAD_DIR = Path(os.getenv("FP_UPLOAD_DIR", str(ROOT / "backend" / "uploads")))
if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = (ROOT / UPLOAD_DIR).resolve()
else:
    UPLOAD_DIR = UPLOAD_DIR.resolve()
MAX_BYTES = int(float(os.getenv("FP_MAX_MB", "10")) * 1024 * 1024)
MAX_PAGES = int(os.getenv("FP_MAX_PAGES", "20"))
COOKIE_SECURE = os.getenv("FP_COOKIE_SECURE", "false").lower() == "true"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip() or "openai/gpt-oss-120b"
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
FRONTEND_DIR = Path(os.getenv("FP_FRONTEND_DIR", str(ROOT / "frontend"))).resolve()
