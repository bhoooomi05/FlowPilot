# FlowPilot AI

FlowPilot AI is a general-purpose document processing workspace. Upload invoices, assignments, receipts, forms, reports, and other PDFs or scanned images. FlowPilot detects the document type, selects invoice-specific or general metadata fields, lets users request custom fields, and supports review, correction, approval, and CSV/Excel export.

**Frontend:** plain HTML, CSS and vanilla JavaScript. There is no React, Node.js build, Vite or frontend bundle step. FastAPI serves the UI and API from one origin.

**AI:** Groq API is the primary AI extraction provider. The key is read only by the backend from `GROQ_API_KEY`; it is never sent to the browser. If the key is absent or the provider fails, FlowPilot uses a conservative fallback and shows a warning. Non-invoice documents do not receive invoice tax/total validation. No Ollama integration is used.

AI extraction can be wrong. The app validates required fields and arithmetic where possible, preserves original extracted values separately from user corrections, and only exports approved records.

## Local setup (Windows PowerShell)

Requirements:
- Python 3.11 or newer
- Tesseract OCR only if you need scanned PDF/image OCR
- A Groq API key if you want AI-assisted extraction: <https://console.groq.com/keys>

1. Extract the project ZIP.
2. Open PowerShell in the project root (the folder containing `backend`, `frontend`, and `scripts`).
3. Optional: copy `.env.example` to `.env` and add your key:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   Set `GROQ_API_KEY=your_actual_key` in `.env`. Do not commit or share `.env`.
4. Start the app:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\scripts\start.ps1
   ```

The script uses `python`, not the optional Windows `py` launcher. It creates a virtual environment and installs backend requirements on first run. Then open <http://localhost:8000>.

Useful URLs:
- Application: <http://localhost:8000>
- API documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>

The UI is served directly from `frontend/index.html`, `frontend/styles.css` and `frontend/app.js`; no Node.js install or frontend build is needed. For development with automatic backend reload, use `.\scripts\dev.ps1` (same URL).

## Environment variables

| Variable | Purpose | Local default |
|---|---|---|
| `GROQ_API_KEY` | Secret Groq API key; keep server-side only | Empty (rules fallback) |
| `GROQ_MODEL` | Groq chat model | `openai/gpt-oss-120b` |
| `GROQ_API_URL` | Groq-compatible chat completion endpoint | `https://api.groq.com/openai/v1/chat/completions` |
| `FP_DB_URL` | SQLAlchemy database URL | `sqlite:///./flowpilot.db` |
| `FP_UPLOAD_DIR` | Private upload storage directory | `backend/uploads` |
| `FP_MAX_MB` | Maximum file size in MB | `10` |
| `FP_MAX_PAGES` | Maximum PDF pages | `20` |
| `FP_COOKIE_SECURE` | Mark session cookie Secure behind HTTPS | `false` locally; `true` on Render |
| `FP_FRONTEND_DIR` | Optional override for static frontend directory | Project `frontend/` |
| `DATABASE_URL` | Optional platform database URL if `FP_DB_URL` is not set | Unset |

The application does not require Ollama. It does not need a Groq key to start, but AI extraction is unavailable without one.

## Deploy to Render

A `render.yaml` Blueprint is included. It configures one Python web service, a persistent disk for SQLite and uploads, HTTPS-only session cookies, a health check, and the Groq environment variables.

1. Push the extracted project to a GitHub repository. Do not commit `.env`, real API keys, uploaded documents or local database files.
2. In Render, choose **New → Blueprint** and connect the repository containing `render.yaml`.
3. Review the service plan and persistent disk cost. The included configuration uses a Starter web service and a 1 GB persistent disk so the SQLite database and uploaded documents survive redeploys. This configuration is not a guaranteed free deployment.
4. During Blueprint setup, provide `GROQ_API_KEY` when Render asks for the secret environment variable. Create it at <https://console.groq.com/keys>.
5. Deploy. Render builds with `pip install -r backend/requirements.txt` and starts Uvicorn on the platform-provided `$PORT`.
6. Open the service URL and test signup, login, upload, review, approval and exports. Confirm `/health` returns `{"status":"ok"}`.

### Render persistence and scaling

The included Blueprint stores SQLite and uploads under `/var/data`, mounted to a persistent disk. Keep this as a single-instance service: SQLite and a local persistent disk are not suitable for horizontally scaled instances. For multi-instance deployment, use managed PostgreSQL and object storage for uploads, then set `FP_DB_URL` and `FP_UPLOAD_DIR` to appropriate services.

If the service is deployed without persistent storage, local SQLite data and uploaded files can be lost during redeploys or restarts. Do not use ephemeral storage for important customer documents.

## Security and operational notes

- Session cookies are HttpOnly and use `SameSite=Lax`; set `FP_COOKIE_SECURE=true` in HTTPS production.
- Mutating requests with a mismatched `Origin` are rejected.
- Uploads are type-checked using file signatures, renamed to random server-side names and stored outside the public frontend directory.
- Document preview and data APIs enforce per-user ownership.
- Groq credentials are never exposed in HTML or JavaScript.
- CSV/XLSX export is limited to approved documents and protects against spreadsheet formula injection.
- Use a strong, unique Groq key; rotate it if it is ever exposed. Avoid sending sensitive documents to external AI providers unless you have permission and an appropriate data policy.
- OCR of scans requires Tesseract installed on the server and available on `PATH`. Digital PDFs can be processed without Tesseract.
- Document processing is synchronous. Very large batches can take time; background queues and worker processes are not included in this MVP.
- Tables are initialized using SQLAlchemy `create_all`; a versioned Alembic migration system is not included yet.
- Invoice extraction targets invoice-level fields and does not extract individual line items. Other document types use general metadata fields plus user-requested custom fields.
- Add production monitoring, tested backups, a documented retention policy and a formal security review before handling sensitive business data at scale.

## Tests

From the project root, create/activate a Python virtual environment, install dependencies, then run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q backend\tests
```

The frontend is vanilla JavaScript and has no frontend package installation/build step. Syntax-check the frontend with Node.js if installed:

```powershell
node --check frontend\app.js
```

## Recent improvements (October 2026)

- Landing page now explains the product and its three-step workflow (upload, review/correct, approve/export), with subtle motion and reduced-motion accessibility support.
- Document type detection routes invoices to invoice extraction and other documents to general metadata extraction. Rule-based invoice extraction handles common label variations, including `Invoice Date`, `Date`, `Invoice #`, `Bill To`, `Subtotal`, `Tax/GST`, `Grand Total`, and common date formats. Extraction remains conservative: verify fields against the original document before approval.
- In the Review extraction page, edit any input manually and select **Save corrections** before approving. If fields remain blank, check the PDF itself and the extraction warning; not every third-party invoice layout can be parsed by simple rules.

## Per-document Excel and custom fields

- Approved documents have an individual **↓ Excel** action in the Documents table. It downloads only that document as `<original-name>.xlsx`.
- During review, use **Extra fields to extract** to request fields such as Purchase Order Number, GSTIN, or Payment Terms. With `GROQ_API_KEY` configured, FlowPilot asks Groq to extract those values from the original document text. The values are suggestions and must be reviewed before approval.
- Custom field values are included as columns in the per-document Excel export and bulk exports.

### Local API key setup

A root `.env` file is included as a blank local template. Add your own `GROQ_API_KEY` value there. Never commit a real key; `.env` is ignored by Git.


Keep your real Groq API key in your local `.env` file only; do not commit or share that file.
