# Backend routes updated by Ruffina
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, send_file
from werkzeug.utils import secure_filename
import os
import sqlite3
import hashlib
import csv
import logging
import re

BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'hiremind.db')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# Basic logging for debugging similarity issues
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)


def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_conn()
    conn.execute('''
    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT UNIQUE,
        name TEXT,
        skills TEXT,
        match_score REAL,
        resume TEXT
    )
    ''')
    conn.commit()
    conn.close()


init_db()
 

def ensure_columns():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(candidates)")
    existing = [r['name'] for r in cur.fetchall()]
    if 'jd' not in existing:
        cur.execute("ALTER TABLE candidates ADD COLUMN jd TEXT DEFAULT ''")
    if 'excerpt' not in existing:
        cur.execute("ALTER TABLE candidates ADD COLUMN excerpt TEXT DEFAULT ''")
    if 'overlap' not in existing:
        cur.execute("ALTER TABLE candidates ADD COLUMN overlap REAL DEFAULT 0.0")
    if 'overlap_tokens' not in existing:
        cur.execute("ALTER TABLE candidates ADD COLUMN overlap_tokens TEXT DEFAULT ''")
    conn.commit()
    conn.close()


ensure_columns()


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_resume():
    # Expecting fields: resume (file), job_description (text)
    file = request.files.get('resume')
    jd = request.form.get('job_description', '')

    if not file or file.filename == '':
        return 'No file uploaded', 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    # Save file first, then read its contents for parsing
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file.save(save_path)

    # Extract text depending on file type. We support PDFs and plain text for the prototype.
    text = ''
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext == 'pdf':
        try:
            # lazy import heavy deps
            import PyPDF2
            with open(save_path, 'rb') as fh:
                reader = PyPDF2.PdfReader(fh)
                for p in reader.pages:
                    page_text = p.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception:
            # fallback to empty text if PDF extraction fails
            text = ''
    elif ext in ('docx',):
        try:
            # parse .docx files
            from docx import Document
            doc = Document(save_path)
            for para in doc.paragraphs:
                if para.text:
                    text += para.text + "\n"
        except Exception:
            app.logger.exception('DOCX parsing failed')
            text = ''
    else:
        try:
            with open(save_path, 'r', encoding='utf-8', errors='ignore') as fh:
                text = fh.read()
        except Exception:
            text = ''

    # Basic Skill Extraction (prototype - extend with NLP later)
    skills = ['python', 'flask', 'django', 'sql', 'postgres', 'mongodb', 'ai', 'ml', 'communication', 'react', 'node']
    extracted_skills = [s for s in skills if s in text.lower()]

    # Similarity Score (AI Matching Simulation)
    score = 0.0
    try:
        # Lazy-import scikit-learn to avoid heavy startup time when the server first launches
        app.logger.info(f"Upload debug: file={filename} jd_len={len(jd or '')} text_len={len(text or '')}")
        if jd.strip() and text.strip():
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            vectorizer = TfidfVectorizer().fit_transform([jd, text])
            try:
                score = float(cosine_similarity(vectorizer[0:1], vectorizer[1:2])[0][0]) * 100
                app.logger.info(f"TF-IDF score={score}")
            except Exception:
                # In rare cases cosine_similarity can fail if vectors are empty
                app.logger.exception('cosine_similarity failed')
                score = 0.0
    except Exception:
        # Log the exception so we can see import or vectorization problems
        app.logger.exception('Error computing TF-IDF similarity')
        score = 0.0

    # Fallback: if TF-IDF gave 0 but both texts exist, try a simple token-overlap heuristic
    try:
        if (not score or score < 0.0001) and jd.strip() and text.strip():
            jd_tokens = set(re.findall(r"\w+", jd.lower()))
            text_tokens = set(re.findall(r"\w+", text.lower()))
            if jd_tokens:
                overlap = len(jd_tokens & text_tokens) / float(len(jd_tokens)) * 100.0
            else:
                overlap = 0.0
            if overlap and overlap > score:
                app.logger.info(f"Fallback token-overlap score={overlap}")
                score = overlap
    except Exception:
        app.logger.exception('Fallback scoring failed')

    uid = hashlib.sha256(open(save_path, 'rb').read()).hexdigest()
    excerpt = (text or '')[:2000]

    # Token overlap diagnostics
    try:
        jd_tokens = set(re.findall(r"\w+", (jd or '').lower()))
        text_tokens = set(re.findall(r"\w+", (text or '').lower()))
        overlap_tokens = jd_tokens & text_tokens
        overlap_percent = (len(overlap_tokens) / float(len(jd_tokens)) * 100.0) if jd_tokens else 0.0
    except Exception:
        app.logger.exception('Error computing token overlap')
        overlap_tokens = set()
        overlap_percent = 0.0
    candidate = {
        'uid': uid,
        'name': os.path.splitext(filename)[0],
        'skills': ', '.join(extracted_skills) if extracted_skills else '—',
        'match_score': round(score, 2),
        'resume': filename,
        'jd': jd,
        'excerpt': excerpt,
        'overlap': round(overlap_percent, 2),
        'overlap_tokens': ', '.join(sorted(list(overlap_tokens)))
    }

    # Save or update into SQLite
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('SELECT id FROM candidates WHERE uid = ?', (uid,))
    row = cur.fetchone()
    if row:
        cur.execute('''UPDATE candidates SET name=?, skills=?, match_score=?, resume=?, jd=?, excerpt=?, overlap=?, overlap_tokens=? WHERE uid=?''',
                    (candidate['name'], candidate['skills'], candidate['match_score'], candidate['resume'], candidate['jd'], candidate['excerpt'], candidate['overlap'], candidate['overlap_tokens'], uid))
    else:
        cur.execute('''INSERT INTO candidates (uid, name, skills, match_score, resume, jd, excerpt, overlap, overlap_tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (uid, candidate['name'], candidate['skills'], candidate['match_score'], candidate['resume'], candidate['jd'], candidate['excerpt'], candidate['overlap'], candidate['overlap_tokens']))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('SELECT uid, name, skills, match_score, resume FROM candidates ORDER BY match_score DESC')
    rows = cur.fetchall()
    candidates = [dict(r) for r in rows]
    conn.close()
    return render_template('dashboard.html', candidates=candidates)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # Serve uploaded resumes during development
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/chat/<name>')
def chat(name):
    # Simple in-browser chat prototype (no sockets)
    return render_template('chat.html', candidate=name)


@app.route('/candidate/<uid>')
def candidate_detail(uid):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('SELECT uid, name, skills, match_score, resume, jd, excerpt, overlap, overlap_tokens FROM candidates WHERE uid = ?', (uid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return 'Candidate not found', 404
    c = dict(row)
    return render_template('candidate.html', c=c)


@app.route('/delete/<uid>', methods=['POST'])
def delete_candidate(uid):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM candidates WHERE uid = ?', (uid,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/export')
def export_csv():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('SELECT uid, name, skills, match_score, resume, jd, excerpt, overlap, overlap_tokens FROM candidates ORDER BY match_score DESC')
    rows = cur.fetchall()
    conn.close()

    csv_path = os.path.join(BASE_DIR, 'candidates_export.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['uid', 'name', 'skills', 'match_score', 'resume', 'jd', 'excerpt', 'overlap', 'overlap_tokens'])
        for r in rows:
            writer.writerow([r['uid'], r['name'], r['skills'], r['match_score'], r['resume'], r['jd'], r['excerpt'], r['overlap'], r['overlap_tokens']])

    return send_file(csv_path, as_attachment=True)


if __name__ == '__main__':
    print("Starting HireMind Flask server...")
    app.run(debug=True)
