# HireMind - Prototype

A compact local prototype of HireMind: an AI-assisted recruiter assistant for quick resume matching and candidate tracking.

What this prototype does (current features)
- Upload resumes (PDF, plain text, DOCX) and paste a job description.
- Extracts text from PDF/DOCX and does simple skill detection.
- Computes a TF-IDF similarity score between the job description and the resume.
- Persists candidates in a local SQLite database (`hiremind.db`).
- Deduplicates uploads using a content hash (same file content won't create duplicate candidates).
- Dashboard with ranked candidate cards, View Resume, Details, Delete and Export (CSV).
- Minimal in-browser chat page (demo only).

Quick start (PowerShell)

```powershell
cd 'C:\Users\Ruffina\Desktop\chat app\HireMind'
python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

Important files and routes
- `app.py` — main Flask app and endpoints.
- `hiremind.db` — SQLite database (created automatically).
- `uploads/` — saved uploaded resumes.
- `templates/` — HTML templates (`index.html`, `dashboard.html`, `chat.html`, `candidate.html`).

Key HTTP endpoints
- GET `/` — upload form.
- POST `/upload` — upload resume + job description.
- GET `/dashboard` — ranked candidates.
- GET `/candidate/<uid>` — candidate details.
- POST `/delete/<uid>` — delete a candidate (does not remove resume file by default).
- GET `/export` — downloads a CSV of candidates.
- GET `/uploads/<filename>` — serves saved resume files (dev only).

Notes & behavior
- File deduplication: candidates are identified by a SHA-256 hash of the resume file contents. Uploading the same file will update the existing candidate instead of creating duplicates.
- Persistence: candidates are stored in `hiremind.db` so they survive restarts.
- Parsing: PDFs are handled with `PyPDF2`; DOCX is handled with `python-docx`. Plain text files are read directly.
- Security: this is a local development prototype. Do not expose the Flask dev server to the public. For production, use a proper WSGI server and secure file handling.

Troubleshooting
- If you see cached CSS or layout changes not appearing, do a hard refresh (Ctrl+F5) in the browser.
- If uploads don't appear on the dashboard, check the server terminal for errors and ensure `uploads/` contains the saved file.




