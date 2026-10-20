/* FlowPilot AI — plain JavaScript frontend. No framework or browser-side AI keys. */
(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const app = $('#app');
  const state = { user: null, page: 'home', authMode: 'login', docs: [], stats: null, system: null, selected: new Set(), query: '', status: '', pageNo: 1, total: 0, pageSize: 10, activeDoc: null, loading: false };
  const invoiceFields = [
    ['supplier', 'Supplier'], ['invoice_number', 'Invoice number'], ['invoice_date', 'Invoice date'],
    ['due_date', 'Due date'], ['customer', 'Customer'], ['currency', 'Currency'],
    ['subtotal', 'Subtotal'], ['tax', 'Tax'], ['total', 'Total']
  ];
  const generalFields = [['document_title', 'Document title'], ['document_summary', 'Document summary'], ['document_date', 'Document date'], ['reference_number', 'Reference number']];
  const symbols = { dashboard: '▦', upload: '↑', documents: '▤', workflow: '⌘', settings: '⚙' };
  const titles = { dashboard: 'Overview', upload: 'Upload documents', documents: 'Documents', review: 'Review extraction', workflow: 'Workflow', settings: 'Settings' };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const bytes = n => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`;
  const date = value => value ? new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
  const statusLabel = value => ({ needs_review: 'Needs review', completed: 'Approved', failed: 'Failed', processing: 'Processing', queued: 'Queued' }[value] || value || 'Unknown');
  const statusClass = value => ({ needs_review: 'pill-amber', completed: 'pill-green', failed: 'pill-red', processing: 'pill-blue', queued: 'pill-blue' }[value] || 'pill-blue');
  const fileKind = mime => mime === 'application/pdf' ? 'PDF' : mime === 'image/png' ? 'PNG' : 'JPG';

  async function request(path, options = {}) {
    let response;
    try { response = await fetch(path, { credentials: 'same-origin', ...options }); }
    catch (_) { throw new Error('Cannot reach FlowPilot. Check that the server is running and try again.'); }
    if (!response.ok) {
      let message = response.statusText || 'Request failed';
      try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail; else if (Array.isArray(body.detail)) message = body.detail.map(x => x.msg).join('; '); }
      catch (_) { /* response may be a plain-text error */ }
      throw new Error(message);
    }
    if (response.status === 204) return null;
    const type = response.headers.get('content-type') || '';
    return type.includes('application/json') ? response.json() : response;
  }
  const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  function toast(message, error = false) {
    const region = $('#toast-region'); if (!region) return;
    const node = document.createElement('div'); node.className = `toast${error ? ' error' : ''}`; node.textContent = message; region.append(node);
    setTimeout(() => node.remove(), 4200);
  }
  function logo() { return '<span class="brand-mark">f.</span>'; }
  function brand(compact = false) { return `<a href="#" class="brand" data-action="home">${logo()}<span>FlowPilot${compact ? '<small>DOCUMENT OPERATIONS</small>' : ''}</span></a>`; }

  function landing() {
    return `<header class="site-header">${brand(true)}<div class="header-actions"><button class="btn btn-quiet" data-action="auth-login">Log in</button><button class="btn btn-primary" data-action="auth-signup">Create an account <span>↗</span></button></div></header>
    <main class="landing"><section class="hero"><div><div class="eyebrow">DOCUMENT OPERATIONS, WITHOUT THE BUSYWORK</div><h1>Make room for work that <em>moves you forward.</em></h1><p class="hero-copy">Turn invoices and business documents into structured, reviewable data. FlowPilot handles the first pass so your team can focus on the details that matter.</p><div class="hero-actions"><button class="btn btn-primary" data-action="auth-signup">Get started <span>↗</span></button><button class="btn btn-secondary" data-action="auth-login">Sign in to your workspace</button></div><div class="hero-note"><i class="status-dot"></i> Human-reviewed by design · Your data stays in your workspace</div></div>
    <div class="preview-board"><div class="preview-top"><div class="window-dots"><i></i><i></i><i></i></div><span>PRODUCT PREVIEW</span><span>SAMPLE DATA</span></div><div class="preview-content"><div class="preview-title">Document overview <span class="tiny-tag">SAMPLE VIEW</span></div><div class="preview-stats"><div class="preview-stat"><span>Processed</span><strong>128</strong></div><div class="preview-stat"><span>Approved</span><strong>94</strong></div><div class="preview-stat"><span>To review</span><strong>12</strong></div></div><div class="preview-row head"><span>DOCUMENT</span><span>STATUS</span><span>AMOUNT</span></div><div class="preview-row"><span>March invoice.pdf</span><span><i class="pill pill-green">Approved</i></span><strong>$1,240</strong></div><div class="preview-row"><span>Supplier bill.pdf</span><span><i class="pill pill-amber">Review</i></span><strong>$385</strong></div><div class="preview-row"><span>Office order.png</span><span><i class="pill pill-green">Approved</i></span><strong>$96</strong></div><div class="preview-row"><span>Service invoice.pdf</span><span><i class="pill pill-blue">Processing</i></span><strong>—</strong></div></div></div></section>
    <section class="flow-strip" aria-label="FlowPilot process"><div class="flow-strip-label">THE FLOW</div><div class="flow-track"><span>Upload a document</span><b>→</b><span>Extract key fields</span><b>→</b><span>Review and correct</span><b>→</b><span>Export approved data</span><b>→</b><span>Upload a document</span><b>→</b><span>Extract key fields</span></div></section>
    <section class="features" id="how-it-works"><div class="section-head"><div><div class="eyebrow">WHY FLOWPILOT EXISTS</div><h2>Less manual data entry. More control.</h2></div><p>Small teams lose time copying invoice details into spreadsheets. FlowPilot turns that repetitive first pass into a reviewable workflow, without pretending AI is always right.</p></div><div class="feature-grid"><article class="feature reveal-card"><div class="feature-icon">↥</div><h3>1. Upload your files</h3><p>Upload invoices, assignments, receipts, forms, reports and other documents in PDF or image format. FlowPilot detects the type before selecting fields.</p></article><article class="feature reveal-card"><div class="feature-icon">⌁</div><h3>2. Review extracted fields</h3><p>FlowPilot detects the document type and selects a relevant field set. Invoice-specific tax validation is used only for invoices; other documents get general metadata and custom-field extraction.</p></article><article class="feature reveal-card"><div class="feature-icon">⇩</div><h3>3. Approve and export</h3><p>Correct any field manually, approve only after checking the source document, then export approved records to CSV or Excel.</p></article></div></section>
    <section class="why-section"><div class="why-copy"><div class="eyebrow">BUILT AROUND TRUST</div><h2>Automation should save time — not remove your judgement.</h2><p>FlowPilot is a document-processing assistant, not an accounting authority. It keeps the original extraction separate from your corrections, shows warnings, and leaves final approval with a person.</p><button class="btn btn-primary" data-action="auth-signup">Try FlowPilot <span>↗</span></button></div><div class="why-points"><div><span class="point-number">01</span><p><strong>Transparent review</strong><br>See what was found and what still needs attention.</p></div><div><span class="point-number">02</span><p><strong>Manual corrections</strong><br>Edit any extracted value before approval.</p></div><div><span class="point-number">03</span><p><strong>Controlled exports</strong><br>Only approved records are eligible for export.</p></div></div></section>
    <footer class="site-footer"><span>© ${new Date().getFullYear()} FlowPilot AI</span><span>AI assists. People approve.</span><a href="#how-it-works">How it works ↑</a></footer></main>`;
  }

  function authPage() {
    const signup = state.authMode === 'signup';
    return `<main class="auth-wrap"><section class="auth-aside"><div>${brand(true)}<div style="margin-top:75px"><div class="eyebrow">A BETTER WAY TO HANDLE PAPERWORK</div><h1>Less copying.<br>More clarity.</h1><p>Bring documents in, review what matters, and keep your business data organized without another complicated system.</p></div></div><div class="auth-aside-foot">FlowPilot AI · Document operations for small teams</div></section><section class="auth-main"><div class="auth-card"><div class="brand" style="margin-bottom:35px">${logo()}<span>FlowPilot</span></div><div class="eyebrow">YOUR WORKSPACE</div><h2>${signup ? 'Create your account' : 'Welcome back'}</h2><p>${signup ? 'Set up your workspace in a minute.' : 'Sign in to continue to your documents.'}</p><form id="auth-form"><div class="field"><label for="email">Work email</label><input id="email" name="email" type="email" autocomplete="email" placeholder="you@company.com" maxlength="255" required></div><div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="${signup ? 'new-password' : 'current-password'}" minlength="8" maxlength="128" placeholder="At least 8 characters" required>${signup ? '<span class="field-hint">Use at least 8 characters.</span>' : ''}</div><div id="auth-error" role="alert"></div><button class="btn btn-primary auth-submit" type="submit">${signup ? 'Create account' : 'Sign in'} <span>→</span></button></form><div class="auth-switch">${signup ? 'Already have an account?' : 'New to FlowPilot?'} <button class="text-button" data-action="toggle-auth">${signup ? 'Sign in' : 'Create an account'}</button></div><p class="field-hint center" style="margin-top:22px">Your Groq API key is stored on the server, never in this page.</p></div></section></main>`;
  }

  function shell(content) {
    const active = state.page === 'review' ? 'documents' : state.page;
    return `<div class="app-shell"><aside class="sidebar" id="sidebar"><div class="side-brand">${brand(true)}</div><div class="side-label">WORKSPACE</div><nav class="nav-list" aria-label="Main navigation">${[['dashboard','Overview'],['upload','Upload documents'],['documents','Documents'],['workflow','Workflow'],['settings','Settings']].map(([key,label]) => `<button class="nav-link ${active === key ? 'active' : ''}" data-page="${key}"><span class="nav-symbol">${symbols[key]}</span>${label}</button>`).join('')}</nav><div class="sidebar-bottom"><div class="help-card"><strong>Built for careful work</strong><p>Review extracted fields before approving them. AI can miss details.</p><button class="text-button small" data-page="workflow">View workflow →</button></div><div class="user-card"><div class="avatar">${esc((state.user?.email || 'U').slice(0,1).toUpperCase())}</div><div class="user-details"><strong>${esc(state.user?.email || 'Workspace user')}</strong><span>Personal workspace</span></div><button class="icon-button" title="Sign out" data-action="logout">↗</button></div></div></aside><div class="mobile-overlay" id="mobile-overlay" data-action="close-menu"></div><main class="main-area"><header class="topbar"><div style="display:flex;align-items:center;gap:13px"><button class="icon-button mobile-menu" data-action="menu" aria-label="Open navigation">☰</button><div class="crumb">Workspace <span style="padding:0 6px;color:#b0b5ac">/</span> <strong>${esc(titles[state.page] || 'Overview')}</strong></div></div><div class="top-actions"><span class="pill pill-green"><i class="status-dot"></i> Workspace active</span><span class="top-user">${esc(state.user?.email || '')}</span></div></header><section class="page" id="page-content">${content}</section></main></div>`;
  }

  const pageHeading = (title, subtitle, actions = '') => `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div>${actions ? `<div class="heading-actions">${actions}</div>` : ''}</div>`;
  function statCard(label, value, note, symbol) { return `<article class="stat-card"><div class="stat-top"><span>${label}</span><span class="stat-icon">${symbol}</span></div><div class="stat-value">${value}</div><div class="stat-note">${note}</div></article>`; }
  function fileCell(d) { return `<div class="doc-name"><span class="file-icon">${esc(fileKind(d.mime || ''))}</span><div><strong title="${esc(d.name)}">${esc(d.name)}</strong><span>${bytes(d.size || 0)} · ${date(d.created_at)}</span></div></div>`; }
  function docRows(items, selection = false) {
    if (!items.length) return `<tr><td colspan="${selection ? 6 : 5}"><div class="empty-state"><div class="empty-icon">▤</div><h3>No documents here yet</h3><p>Upload an invoice, assignment, receipt, form, report or another supported document to extract information.</p><button class="btn btn-primary btn-small" data-page="upload">Upload a document</button></div></td></tr>`;
    return items.map(d => `<tr>${selection ? `<td><input class="selection-check" type="checkbox" data-select-doc="${d.id}" ${state.selected.has(d.id) ? 'checked' : ''} aria-label="Select ${esc(d.name)}"></td>` : ''}<td>${fileCell(d)}</td><td><span class="pill ${statusClass(d.status)}">${esc(statusLabel(d.status))}</span></td><td>${esc(d.provider || '—')}</td><td>${date(d.processed_at || d.created_at)}</td><td><div class="row-actions"><button class="table-action" data-review="${d.id}">${d.status === 'failed' ? 'Inspect' : d.approved ? 'View' : 'Review'} →</button>${d.status !== 'failed' ? `<button class="btn btn-secondary btn-small" data-action="export-one" data-id="${d.id}" title="Download only this document as Excel">↓ Excel</button>` : ''}</div></td></tr>`).join('');
  }
  async function loadStats() { state.stats = await request('/api/dashboard/stats'); }
  async function loadDocs() {
    const params = new URLSearchParams({ page: String(state.pageNo), size: String(state.pageSize) });
    if (state.query) params.set('q', state.query); if (state.status) params.set('status', state.status);
    const result = await request(`/api/documents?${params}`); state.docs = result.items; state.total = result.total;
  }
  async function loadSystem() { state.system = await request('/api/system/status'); }

  function dashboard() {
    const s = state.stats || {};
    return `${pageHeading('Good work starts with a clear view.', 'A quick look at your document queue and recent activity.', '<button class="btn btn-primary" data-page="upload">＋ Upload documents</button>')}<div class="stats-grid">${statCard('Documents processed', s.total ?? '—', 'All documents in this workspace', '▤')}${statCard('Approved', s.completed ?? '—', 'Ready to export', '✓')}${statCard('Needs review', s.needs_review ?? '—', 'Waiting for your approval', '◷')}${statCard('Failed', s.failed ?? '—', 'Need another look', '!')}</div><div class="content-grid"><section class="panel"><div class="panel-header"><div><h2>Recent documents</h2><p>Your latest uploads and their current status.</p></div><button class="table-action" data-page="documents">All documents →</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Document</th><th>Status</th><th>Method</th><th>Updated</th><th></th></tr></thead><tbody id="recent-rows">${docRows(state.docs)}</tbody></table></div></section><div style="display:grid;gap:15px"><section class="panel"><div class="panel-header"><div><h2>Quick actions</h2><p>Move work forward.</p></div></div><div class="panel-body quick-actions"><button class="quick-action" data-page="upload"><span class="quick-action-icon">↑</span><span><strong>Upload documents</strong><span>PDF, PNG or JPEG</span></span><span class="quick-arrow">→</span></button><button class="quick-action" data-page="documents"><span class="quick-action-icon">▤</span><span><strong>Review extractions</strong><span>Check fields and warnings</span></span><span class="quick-arrow">→</span></button><button class="quick-action" data-action="export-csv"><span class="quick-action-icon">⇩</span><span><strong>Export approved data</strong><span>Download CSV</span></span><span class="quick-arrow">→</span></button></div></section><section class="panel"><div class="panel-header"><div><h2>Time saved</h2><p>A directional estimate, not a measured result.</p></div></div><div class="panel-body"><div class="stat-value" style="margin-top:0">${s.estimated_minutes_saved ?? 0} <span style="font:500 13px 'DM Sans';color:var(--muted)">min</span></div><div class="stat-note">${esc(s.estimate_note || 'Estimate based on approved documents.')}</div></div></section></div></div>`;
  }
  function uploadPage() {
    return `${pageHeading('Upload documents', 'Bring invoices and business documents into one reviewable workflow.')}<section class="panel"><div class="panel-body"><div class="upload-zone" id="upload-zone"><div class="upload-icon">↑</div><h3>Drop documents here</h3><p>Or choose files from your computer. Upload PDFs, PNGs and JPEGs.</p><button class="btn btn-primary" data-action="choose-files">Choose files</button><input class="hide" id="file-input" type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" multiple><div class="upload-note">Maximum ${state.system?.max_mb || 10} MB per file · Up to ${state.system?.max_pages || 20} pages per PDF · Review before export</div></div><div id="upload-results" class="upload-results"></div></div></section><div class="notice mt-12">FlowPilot uses Groq for AI-assisted extraction when a server-side API key is configured. If Groq is unavailable, the app falls back to document rules and tells you. Review all extracted values before approving.</div>`;
  }
  function documentsPage() {
    const approvedCount = state.docs.filter(d => d.approved).length;
    return `${pageHeading('Documents', 'Search your files, review extraction results and export approved records.', '<button class="btn btn-secondary" data-action="export-csv">Export CSV</button><button class="btn btn-secondary" data-action="export-xlsx">Export Excel</button><button class="btn btn-primary" data-page="upload">＋ Upload</button>')}<div class="toolbar"><input class="toolbar-input" id="search-docs" placeholder="Search by file name…" value="${esc(state.query)}"><select class="toolbar-input" id="status-filter" aria-label="Filter by status"><option value="">All statuses</option>${[['needs_review','Needs review'],['completed','Approved'],['failed','Failed'],['processing','Processing']].map(([v,l]) => `<option value="${v}" ${state.status===v?'selected':''}>${l}</option>`).join('')}</select><span class="toolbar-spacer"></span><span class="muted small">${state.total} documents · ${approvedCount} approved on this page</span></div><section class="panel"><div class="table-wrap"><table class="data-table"><thead><tr><th><input type="checkbox" class="selection-check" id="select-page" aria-label="Select page"></th><th>Document</th><th>Status</th><th>Extraction</th><th>Updated</th><th></th></tr></thead><tbody>${docRows(state.docs, true)}</tbody></table></div><div class="pagination"><span>Page ${state.pageNo} of ${Math.max(1, Math.ceil(state.total / state.pageSize))}</span><div class="pagination-actions"><button class="btn btn-secondary btn-small" data-action="prev-page" ${state.pageNo<=1?'disabled':''}>← Previous</button><button class="btn btn-secondary btn-small" data-action="next-page" ${state.pageNo>=Math.ceil(state.total/state.pageSize)?'disabled':''}>Next →</button></div></div></section><p class="field-hint mt-12">Exports contain approved documents only. Select rows to export a subset, or leave all rows unselected to export all approved documents.</p>`;
  }
  function workflowPage() {
    const docs = state.docs.slice(0, 12);
    const stages = [
      ['Upload', 'File accepted and safely stored.'], ['Extract', 'Text is read from the PDF or OCR is used for scans.'], ['Classify & validate', 'Detect document type and apply invoice-only checks where relevant.'], ['Review', 'A person corrects uncertain or missing values.'], ['Approve', 'Reviewed records are marked ready for export.'], ['Export', 'Approved records can be downloaded as CSV or Excel.']
    ];
    return `${pageHeading('Workflow', 'A straightforward path from an uploaded document to verified data.')}<section class="panel"><div class="panel-header"><div><h2>Processing stages</h2><p>Uploads currently process during the request; there is no background queue.</p></div></div><div class="panel-body"><div class="workflow-list">${stages.map((s,i)=>`<div class="workflow-step ${i < 3 ? 'done' : ''}"><div class="step-number">${i<3?'✓':String(i+1).padStart(2,'0')}</div><div><strong>${s[0]}</strong><p>${s[1]}</p></div><span class="pill ${i<3?'pill-green':'pill-blue'}">${i<3?'Active stage':'Next step'}</span></div>`).join('')}</div></div></section><section class="panel mt-12"><div class="panel-header"><div><h2>Recent workflow activity</h2><p>Live status from your document records.</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Document</th><th>Status</th><th>Last update</th><th></th></tr></thead><tbody>${docs.length ? docs.map(d=>`<tr><td>${fileCell(d)}</td><td><span class="pill ${statusClass(d.status)}">${esc(statusLabel(d.status))}</span></td><td>${date(d.processed_at || d.created_at)}</td><td><button class="table-action" data-review="${d.id}">Open →</button></td></tr>`).join('') : '<tr><td colspan="4"><div class="empty-state"><h3>No workflow activity yet</h3><p>Upload a document to start.</p><button class="btn btn-primary btn-small" data-page="upload">Upload document</button></div></td></tr>'}</tbody></table></div></section>`;
  }
  function settingsPage() {
    return `${pageHeading('Settings', 'Manage your account and review how FlowPilot handles document data.')}<div class="settings-grid"><section class="panel"><div class="panel-header"><div><h2>Account</h2><p>Your signed-in workspace identity.</p></div></div><div class="panel-body"><div class="setting-row"><div><strong>Email address</strong><p>${esc(state.user?.email)}</p></div></div><button class="btn btn-secondary mt-12" data-action="logout">Sign out</button></div></section><section class="panel"><div class="panel-header"><div><h2>Data handling</h2><p>How FlowPilot treats extracted information.</p></div></div><div class="panel-body"><div class="notice">Original extraction values are preserved separately from corrections. Only approved records are included in exports. Extraction results can be wrong, so review documents before approval.</div><p class="field-hint mt-12">Avoid uploading sensitive documents to any external AI service unless your organization has approved that use.</p></div></section></div>`;
  }
  function reviewPage() {
    const d = state.activeDoc;
    if (!d) return `${pageHeading('Review extraction', 'Open a document to inspect its extracted fields.')}<div class="panel"><div class="empty-state"><h3>No document selected</h3><button class="btn btn-primary" data-page="documents">Browse documents</button></div></div>`;
    const val = d.effective || {};
    const fields = d.document_type === 'invoice' ? invoiceFields : generalFields;
    const preview = d.mime === 'application/pdf' ? `<iframe class="preview-frame" title="Original document preview" src="/api/documents/${d.id}/file"></iframe>` : d.mime?.startsWith('image/') ? `<img class="preview-frame" style="object-fit:contain" alt="Uploaded document" src="/api/documents/${d.id}/file">` : '<div class="preview-fallback">Preview is unavailable for this file type.</div>';
    return `${pageHeading('Review extraction', esc(d.name), `<span class="pill ${statusClass(d.status)}">${esc(statusLabel(d.status))}</span><button class="btn btn-secondary" data-page="documents">← Back</button>`)}<div class="review-layout"><section class="panel"><div class="panel-header"><div><h2>Original document</h2><p>${esc(fileKind(d.mime))} · ${bytes(d.size || 0)}</p></div><a class="table-action" href="/api/documents/${d.id}/file" target="_blank" rel="noopener">Open separately ↗</a></div>${preview}</section><section class="panel"><div class="panel-header"><div><h2>Extracted information</h2><p>Detected type: <strong>${esc((d.document_type || 'general_document').replaceAll('_', ' '))}</strong>. Check every value before approving.</p></div></div><div class="panel-body"><div class="setting-row" style="padding-top:0"><div><strong>Extraction method</strong><p>${esc(d.method || '—')} · ${esc(d.provider || 'rules')}</p></div><span class="pill ${d.approved?'pill-green':'pill-amber'}">${d.approved?'Approved':'Review needed'}</span></div>${d.error ? `<div class="form-error">${esc(d.error)}</div>` : ''}${(d.warnings || []).length ? `<div class="warning-list">${d.warnings.map(w=>`<div class="warning-item">${esc(w)}</div>`).join('')}</div>` : '<div class="notice mt-12" style="margin-bottom:15px">No validation warnings. Review the original document before approval.</div>'}<form id="review-form" data-id="${d.id}"><div class="field-grid">${fields.map(([key,label])=>`<div class="field ${['supplier','customer'].includes(key)?'field-full':''}"><label for="field-${key}">${label}${d.corrected && Object.prototype.hasOwnProperty.call(d.corrected,key) ? ' · corrected' : ''}</label><input id="field-${key}" name="${key}" value="${esc(val[key] ?? '')}" ${['subtotal','tax','total'].includes(key)?'inputmode="decimal"':''} placeholder="Not found"></div>`).join('')}</div><div class="custom-extract-box"><div class="custom-extract-heading"><strong>Need different information?</strong><span>Enter any fields relevant to this document, such as course name, applicant ID, receipt number, payment terms or GSTIN. AI searches the original document when configured.</span></div><div class="field"><label for="custom-field-names">Extra fields to extract (comma-separated)</label><input id="custom-field-names" placeholder="e.g. Purchase Order Number, GSTIN, Payment Terms"></div><button class="btn btn-secondary btn-small" type="button" data-action="custom-extract" data-id="${d.id}">Extract these fields with AI</button><div class="custom-field-grid">${Object.entries(val).filter(([key])=>key.startsWith('custom:')).map(([key,value])=>`<div class="field"><label>${esc(key.slice(7))}</label><input name="${esc(key)}" value="${esc(value ?? '')}" placeholder="Not found"></div>`).join('')}</div><p class="field-hint">AI results are suggestions, not verified facts. Review and correct them before approval. You can also type values manually.</p></div><div class="review-actions"><button class="btn btn-primary" type="submit">Save corrections</button><button class="btn btn-secondary" type="button" data-action="approve" data-id="${d.id}" ${d.status==='failed'?'disabled':''}>Approve</button><button class="btn btn-secondary" type="button" data-action="reject" data-id="${d.id}">Send back</button><button class="btn btn-secondary" type="button" data-action="reprocess" data-id="${d.id}">Reprocess</button><button class="btn btn-danger btn-small" type="button" data-action="delete" data-id="${d.id}">Delete</button></div></form><p class="field-hint mt-12">Original extracted values are preserved. Saving a field creates a separate correction. Approving marks this record eligible for export.</p></div></section></div>`;
  }

  function pageContent() {
    if (state.page === 'dashboard') return dashboard();
    if (state.page === 'upload') return uploadPage();
    if (state.page === 'documents') return documentsPage();
    if (state.page === 'review') return reviewPage();
    if (state.page === 'workflow') return workflowPage();
    return settingsPage();
  }
  function render() {
    if (!state.user) { app.innerHTML = state.page === 'auth' ? authPage() : landing(); return; }
    app.innerHTML = shell(pageContent());
  }
  async function refreshPage() {
    try {
      if (!state.user) return;
      if (state.page === 'dashboard') { await Promise.all([loadStats(), loadDocs()]); }
      else if (state.page === 'documents' || state.page === 'workflow') await loadDocs();
      else if (state.page === 'upload' || state.page === 'settings') await loadSystem();
      if (state.page !== 'review') render();
    } catch (error) {
      if (error.message.includes('Not authenticated')) { state.user = null; state.page = 'home'; render(); }
      else toast(error.message, true);
    }
  }
  async function goPage(page) {
    state.page = page; state.selected.clear();
    $('#sidebar')?.classList.remove('open'); $('#mobile-overlay')?.classList.remove('show');
    if (page === 'review' && !state.activeDoc) state.page = 'documents';
    render(); await refreshPage();
  }
  async function openReview(id) {
    try { state.activeDoc = await request(`/api/documents/${id}`); state.page = 'review'; render(); }
    catch (error) { toast(error.message, true); }
  }
  async function downloadExport(format) {
    const ids = [...state.selected];
    const suffix = ids.length ? `?ids=${encodeURIComponent(ids.join(','))}` : '';
    const response = await fetch(`/api/exports/${format}${suffix}`, { credentials: 'same-origin' });
    if (!response.ok) { let message = 'Export failed'; try { message = (await response.json()).detail || message; } catch (_) {} throw new Error(message); }
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `flowpilot.${format}`; document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    toast(`${format.toUpperCase()} export downloaded.`);
  }
  async function downloadOne(id) {
    const response = await fetch(`/api/documents/${id}/export.xlsx`, { credentials: 'same-origin' });
    if (!response.ok) { let message = 'Excel download failed'; try { message = (await response.json()).detail || message; } catch (_) {} throw new Error(message); }
    const blob = await response.blob();
    const disposition = response.headers.get('content-disposition') || '';
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const a = document.createElement('a'); const url = URL.createObjectURL(blob);
    a.href = url; a.download = match ? match[1] : `document-${id}.xlsx`;
    document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    toast('Excel file downloaded for this document.');
  }

  async function uploadFiles(files) {
    if (!files.length) return;
    const results = $('#upload-results'); if (results) results.innerHTML = `<div class="notice">Uploading ${files.length} file${files.length===1?'':'s'} and processing. Keep this page open until it finishes.</div>`;
    const form = new FormData(); files.forEach(f => form.append('files', f));
    try {
      const data = await request('/api/documents/upload', { method: 'POST', body: form });
      if (results) results.innerHTML = data.map(d => `<div class="upload-result"><span>${esc(d.name || 'Document')}</span>${d.error ? `<span class="pill pill-red">${esc(d.error)}</span>` : `<span class="pill ${statusClass(d.status)}">${esc(statusLabel(d.status))}</span><button class="table-action" data-review="${d.id}">Review →</button>`}</div>`).join('');
      const failures = data.filter(d => d.error || d.status === 'failed').length;
      toast(failures ? `Upload finished with ${failures} issue${failures===1?'':'s'}.` : `${data.length} document${data.length===1?'':'s'} processed.` , failures > 0);
      state.pageNo = 1;
    } catch (error) { if (results) results.innerHTML = `<div class="form-error">${esc(error.message)}</div>`; toast(error.message, true); }
  }

  app.addEventListener('click', async event => {
    const target = event.target.closest('[data-action],[data-page],[data-review]'); if (!target) return;
    if (target.dataset.page) { event.preventDefault(); if (target.dataset.page === 'home' && !state.user) { state.page = 'home'; render(); return; } await goPage(target.dataset.page); return; }
    if (target.dataset.review) { await openReview(Number(target.dataset.review)); return; }
    const action = target.dataset.action;
    try {
      if (action === 'home') { if (state.user) await goPage('dashboard'); else { state.page = 'home'; render(); } }
      else if (action === 'auth-login') { state.page = 'auth'; state.authMode = 'login'; render(); }
      else if (action === 'auth-signup') { state.page = 'auth'; state.authMode = 'signup'; render(); }
      else if (action === 'toggle-auth') { state.authMode = state.authMode === 'signup' ? 'login' : 'signup'; render(); }
      else if (action === 'logout') { await request('/api/auth/logout', { method: 'POST' }); state.user = null; state.activeDoc = null; state.page = 'home'; render(); toast('You have signed out.'); }
      else if (action === 'choose-files') $('#file-input')?.click();
      else if (action === 'menu') { $('#sidebar')?.classList.add('open'); $('#mobile-overlay')?.classList.add('show'); }
      else if (action === 'close-menu') { $('#sidebar')?.classList.remove('open'); $('#mobile-overlay')?.classList.remove('show'); }
      else if (action === 'export-csv') await downloadExport('csv');
      else if (action === 'export-xlsx') await downloadExport('xlsx');
      else if (action === 'export-one') await downloadOne(Number(target.dataset.id));
      else if (action === 'custom-extract') { const id = Number(target.dataset.id); const input = $('#custom-field-names'); const requested = (input?.value || '').split(',').map(x => x.trim()).filter(Boolean); if (!requested.length) { toast('Enter at least one field name first.', true); return; } target.disabled = true; target.textContent = 'Extracting…'; try { const result = await request(`/api/documents/${id}/custom-extract`, json('POST', { fields: requested })); state.activeDoc = result; render(); toast('Custom fields extracted. Review the results before approval.'); } finally { target.disabled = false; } }
      else if (action === 'prev-page') { state.pageNo = Math.max(1, state.pageNo - 1); await loadDocs(); render(); }
      else if (action === 'next-page') { state.pageNo += 1; await loadDocs(); render(); }
      else if (['approve','reject','reprocess'].includes(action)) {
        const id = Number(target.dataset.id);
        const result = await request(`/api/documents/${id}/${action === 'reprocess' ? 'process' : action}`, { method: 'POST' });
        state.activeDoc = result; await openReview(id); toast(action === 'approve' ? 'Document approved and ready to export.' : action === 'reject' ? 'Document returned to review.' : 'Document reprocessed.');
      } else if (action === 'delete') {
        const id = Number(target.dataset.id); if (!confirm('Delete this document and its uploaded file? This cannot be undone.')) return;
        await request(`/api/documents/${id}`, { method: 'DELETE' }); state.activeDoc = null; state.page = 'documents'; await loadDocs(); render(); toast('Document deleted.');
      }
    } catch (error) { toast(error.message, true); }
  });

  app.addEventListener('submit', async event => {
    const form = event.target;
    if (form.id === 'auth-form') {
      event.preventDefault(); const email = new FormData(form).get('email').toString().trim(); const password = new FormData(form).get('password').toString();
      const errorNode = $('#auth-error'); const button = form.querySelector('button[type=submit]'); button.disabled = true; button.textContent = state.authMode === 'signup' ? 'Creating account…' : 'Signing in…'; if (errorNode) errorNode.innerHTML = '';
      try { await request(`/api/auth/${state.authMode === 'signup' ? 'register' : 'login'}`, json('POST', { email, password })); state.user = await request('/api/auth/me'); state.page = 'dashboard'; state.stats = null; state.docs = []; render(); await refreshPage(); toast(state.authMode === 'signup' ? 'Your workspace is ready.' : 'Signed in successfully.'); }
      catch (error) { if (errorNode) errorNode.innerHTML = `<div class="form-error">${esc(error.message)}</div>`; button.disabled = false; button.textContent = state.authMode === 'signup' ? 'Create account →' : 'Sign in →'; }
    } else if (form.id === 'review-form') {
      event.preventDefault(); const id = Number(form.dataset.id); const formData = new FormData(form); const corrections = {};
      for (const [key] of fields) { const raw = String(formData.get(key) ?? '').trim(); if (['subtotal','tax','total'].includes(key)) { corrections[key] = raw === '' ? null : Number(raw); if (raw !== '' && !Number.isFinite(corrections[key])) { toast(`${key} must be a number.`, true); return; } } else corrections[key] = raw === '' ? null : raw; }
      for (const [key, rawValue] of formData.entries()) { if (key.startsWith('custom:')) corrections[key] = String(rawValue).trim() || null; }
      const button = form.querySelector('button[type=submit]'); button.disabled = true; button.textContent = 'Saving…';
      try { await request(`/api/documents/${id}/extraction`, json('PATCH', { corrections })); await openReview(id); toast('Corrections saved. Original extraction remains unchanged.'); }
      catch (error) { toast(error.message, true); button.disabled = false; button.textContent = 'Save corrections'; }
    }
  });

  app.addEventListener('change', async event => {
    const target = event.target;
    if (target.id === 'file-input') await uploadFiles([...target.files]);
    if (target.id === 'status-filter') { state.status = target.value; state.pageNo = 1; try { await loadDocs(); render(); } catch (e) { toast(e.message, true); } }
    if (target.dataset.selectDoc) { const id = Number(target.dataset.selectDoc); target.checked ? state.selected.add(id) : state.selected.delete(id); }
    if (target.id === 'select-page') { const checks = [...app.querySelectorAll('[data-select-doc]')]; checks.forEach(c => { c.checked = target.checked; const id = Number(c.dataset.selectDoc); target.checked ? state.selected.add(id) : state.selected.delete(id); }); }
  });
  app.addEventListener('keydown', async event => {
    if (event.target.id === 'search-docs' && event.key === 'Enter') { state.query = event.target.value.trim(); state.pageNo = 1; try { await loadDocs(); render(); } catch (e) { toast(e.message, true); } }
  });
  app.addEventListener('dragover', event => { if (event.target.closest('#upload-zone')) { event.preventDefault(); $('#upload-zone')?.classList.add('dragover'); } });
  app.addEventListener('dragleave', event => { if (event.target.closest('#upload-zone')) $('#upload-zone')?.classList.remove('dragover'); });
  app.addEventListener('drop', async event => { if (event.target.closest('#upload-zone')) { event.preventDefault(); $('#upload-zone')?.classList.remove('dragover'); await uploadFiles([...event.dataTransfer.files]); } });

  (async function init() {
    try { state.user = await request('/api/auth/me'); state.page = 'dashboard'; }
    catch (_) { state.user = null; state.page = 'home'; }
    render(); if (state.user) await refreshPage();
  })();
})();
