import os
import sqlite3
import re
from pathlib import Path
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / 'hiremind.db'
UPLOADS = BASE_DIR / 'uploads'

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def extract_text_from_file(path):
    path = Path(path)
    text = ''
    ext = path.suffix.lower().lstrip('.')
    if ext == 'pdf':
        try:
            import PyPDF2
            with open(path, 'rb') as fh:
                reader = PyPDF2.PdfReader(fh)
                for p in reader.pages:
                    page_text = p.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            print('PDF parse failed for', path, e)
            text = ''
    elif ext == 'docx':
        try:
            from docx import Document
            doc = Document(path)
            for para in doc.paragraphs:
                if para.text:
                    text += para.text + "\n"
        except Exception as e:
            print('DOCX parse failed for', path, e)
            text = ''
    else:
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                text = fh.read()
        except Exception as e:
            print('Text read failed for', path, e)
            text = ''
    return text


def reprocess_all():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('SELECT uid, resume, jd FROM candidates')
    rows = cur.fetchall()
    print('Found', len(rows), 'candidates to reprocess')
    for r in rows:
        uid = r['uid']
        resume = r['resume']
        jd = r['jd'] or ''
        file_path = UPLOADS / resume
        if not file_path.exists():
            print('Missing file for', uid, resume)
            continue
        text = extract_text_from_file(file_path)
        excerpt = (text or '')[:2000]
        jd_tokens = set(re.findall(r"\w+", jd.lower()))
        text_tokens = set(re.findall(r"\w+", text.lower()))
        overlap_tokens = jd_tokens & text_tokens
        overlap_percent = (len(overlap_tokens) / float(len(jd_tokens)) * 100.0) if jd_tokens else 0.0
        score = 0.0
        try:
            if jd.strip() and text.strip():
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.metrics.pairwise import cosine_similarity
                vectorizer = TfidfVectorizer().fit_transform([jd, text])
                score = float(cosine_similarity(vectorizer[0:1], vectorizer[1:2])[0][0]) * 100
        except Exception as e:
            print('TF-IDF failed for', uid, e)
            score = 0.0
        if (not score or score < 0.0001) and jd.strip() and text.strip():
            if jd_tokens:
                fallback = len(overlap_tokens) / float(len(jd_tokens)) * 100.0
            else:
                fallback = 0.0
            if fallback and fallback > score:
                score = fallback
        cur.execute('''UPDATE candidates SET excerpt=?, overlap=?, overlap_tokens=?, match_score=? WHERE uid=?''',
                    (excerpt, round(overlap_percent,2), ', '.join(sorted(list(overlap_tokens))), round(score,2), uid))
        print('Updated', uid, 'score=', round(score,2), 'overlap=', round(overlap_percent,2))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    reprocess_all()
