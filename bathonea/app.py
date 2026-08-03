import json
import os
import threading
import uuid
import datetime
from functools import wraps

from flask import Flask, render_template, request, session, jsonify, redirect, url_for, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import (get_db, init_db, now, get_setting, set_setting,
                 get_active_document, get_document_pages)
import ocr
import ai

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)

_config_path = os.path.join(BASE_DIR, 'config.json')
_cfg = {}
if os.path.exists(_config_path):
    with open(_config_path, 'r', encoding='utf-8') as f:
        _cfg = json.load(f)

app.secret_key = _cfg.get('secret_key') or os.environ.get('SECRET_KEY') or 'degistir-bunu'
app.permanent_session_lifetime = datetime.timedelta(days=30)
app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024  # 60MB (PDF/foto yükleme)
init_db()


# ── Auth ──────────────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get('admin_id'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'giris_gerekli'}), 401
            return redirect(url_for('admin_login_page'))
        return f(*a, **kw)
    return wrapped


# ── Genel sayfalar (herkese açık) ────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/sozlesme')
def contract_page():
    return render_template('contract.html')


@app.route('/sohbet')
def chat_page():
    return render_template('chat.html')


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ── Admin sayfaları ──────────────────────────────────────────────────────────
@app.route('/admin/login')
def admin_login_page():
    if session.get('admin_id'):
        return redirect(url_for('admin_page'))
    return render_template('admin_login.html')


@app.route('/admin')
@admin_required
def admin_page():
    return render_template('admin.html')


# ── Admin auth API ───────────────────────────────────────────────────────────
@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    d = request.get_json(force=True)
    conn = get_db()
    admin = conn.execute('SELECT * FROM admin_users WHERE username = ?',
                          (d.get('username', '').strip(),)).fetchone()
    conn.close()
    if not admin or not check_password_hash(admin['password_hash'], d.get('password', '')):
        return jsonify({'error': 'Kullanıcı adı veya şifre hatalı'}), 401
    session.permanent = True
    session.update(admin_id=admin['id'], admin_username=admin['username'])
    return jsonify({'ok': True})


@app.route('/api/admin/logout', methods=['POST'])
def api_admin_logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/admin/me')
def api_admin_me():
    if not session.get('admin_id'):
        return jsonify({'error': 'giris_gerekli'}), 401
    return jsonify({'username': session.get('admin_username')})


# ── Ayarlar (DeepSeek API key / model) ──────────────────────────────────────
@app.route('/api/admin/settings', methods=['GET'])
@admin_required
def api_get_settings():
    key = get_setting('deepseek_api_key', '')
    masked = ('•' * 8 + key[-4:]) if key else ''
    return jsonify({
        'deepseek_api_key_set': bool(key),
        'deepseek_api_key_masked': masked,
        'deepseek_model': get_setting('deepseek_model', 'deepseek-chat'),
    })


@app.route('/api/admin/settings', methods=['POST'])
@admin_required
def api_save_settings():
    d = request.get_json(force=True)
    if d.get('deepseek_api_key'):
        set_setting('deepseek_api_key', d['deepseek_api_key'].strip())
    if d.get('deepseek_model'):
        set_setting('deepseek_model', d['deepseek_model'].strip())
    return jsonify({'ok': True})


# ── Belge işleme (arka planda OCR) ──────────────────────────────────────────
def _process_pdf_document(doc_id, pdf_path):
    conn = get_db()
    try:
        out_dir = os.path.join(UPLOAD_DIR, f'doc_{doc_id}')
        page_paths = ocr.pdf_to_page_images(pdf_path, out_dir)
        for i, p in enumerate(page_paths, start=1):
            text = ocr.ocr_image_path(p)
            rel_path = os.path.relpath(p, UPLOAD_DIR)
            conn.execute(
                'INSERT INTO pages (document_id, page_number, image_path, text, created_at) '
                'VALUES (?, ?, ?, ?, ?)',
                (doc_id, i, rel_path, text, now())
            )
        conn.execute('UPDATE documents SET status = ? WHERE id = ?', ('ready', doc_id))
        conn.commit()
    except Exception as e:
        conn.execute('UPDATE documents SET status = ?, error = ? WHERE id = ?', ('error', str(e), doc_id))
        conn.commit()
    finally:
        conn.close()
        try:
            os.remove(pdf_path)
        except OSError:
            pass


@app.route('/api/admin/documents', methods=['GET'])
@admin_required
def api_list_documents():
    conn = get_db()
    docs = conn.execute(
        'SELECT d.*, (SELECT COUNT(*) FROM pages WHERE document_id = d.id) AS page_count '
        'FROM documents d ORDER BY d.id DESC'
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in docs])


@app.route('/api/admin/documents', methods=['POST'])
@admin_required
def api_upload_document():
    file = request.files.get('file')
    title = request.form.get('title', '').strip() or 'Toplu İş Sözleşmesi'
    if not file or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'PDF dosyası gerekli'}), 400

    conn = get_db()
    cur = conn.execute('INSERT INTO documents (title, is_active, status, created_at) VALUES (?, 0, ?, ?)',
                        (title, 'processing', now()))
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()

    tmp_path = os.path.join(UPLOAD_DIR, f'_upload_{doc_id}_{secure_filename(file.filename)}')
    file.save(tmp_path)

    threading.Thread(target=_process_pdf_document, args=(doc_id, tmp_path), daemon=True).start()
    return jsonify({'id': doc_id, 'status': 'processing'})


@app.route('/api/admin/documents/<int:doc_id>', methods=['GET'])
@admin_required
def api_get_document(doc_id):
    conn = get_db()
    doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
    conn.close()
    if not doc:
        return jsonify({'error': 'Belge bulunamadı'}), 404
    pages = get_document_pages(doc_id)
    return jsonify({'document': dict(doc), 'pages': pages})


@app.route('/api/admin/documents/<int:doc_id>/activate', methods=['POST'])
@admin_required
def api_activate_document(doc_id):
    conn = get_db()
    doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
    if not doc:
        conn.close()
        return jsonify({'error': 'Belge bulunamadı'}), 404
    if doc['status'] != 'ready':
        conn.close()
        return jsonify({'error': 'Belge henüz hazır değil'}), 400
    conn.execute('UPDATE documents SET is_active = 0')
    conn.execute('UPDATE documents SET is_active = 1 WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/admin/documents/<int:doc_id>', methods=['DELETE'])
@admin_required
def api_delete_document(doc_id):
    conn = get_db()
    conn.execute('DELETE FROM pages WHERE document_id = ?', (doc_id,))
    conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/admin/documents/<int:doc_id>/pages', methods=['POST'])
@admin_required
def api_add_page(doc_id):
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Görsel dosyası gerekli'}), 400
    conn = get_db()
    doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
    if not doc:
        conn.close()
        return jsonify({'error': 'Belge bulunamadı'}), 404
    max_row = conn.execute('SELECT MAX(page_number) AS m FROM pages WHERE document_id = ?', (doc_id,)).fetchone()
    next_num = (max_row['m'] or 0) + 1

    out_dir = os.path.join(UPLOAD_DIR, f'doc_{doc_id}')
    os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower() or '.jpg'
    dest = os.path.join(out_dir, f'page-{next_num}{ext}')
    file.save(dest)
    text = ocr.ocr_image_path(dest)
    rel_path = os.path.relpath(dest, UPLOAD_DIR)

    conn.execute('INSERT INTO pages (document_id, page_number, image_path, text, created_at) VALUES (?, ?, ?, ?, ?)',
                 (doc_id, next_num, rel_path, text, now()))
    conn.execute('UPDATE documents SET status = ? WHERE id = ? AND status = ?', ('ready', doc_id, 'processing'))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'page_number': next_num, 'text': text})


@app.route('/api/admin/pages/<int:page_id>', methods=['PUT'])
@admin_required
def api_edit_page(page_id):
    d = request.get_json(force=True)
    conn = get_db()
    conn.execute('UPDATE pages SET text = ? WHERE id = ?', (d.get('text', ''), page_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/admin/pages/<int:page_id>', methods=['DELETE'])
@admin_required
def api_delete_page(page_id):
    conn = get_db()
    conn.execute('DELETE FROM pages WHERE id = ?', (page_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ── Herkese açık: aktif belge okuma ──────────────────────────────────────────
@app.route('/api/document')
def api_public_document():
    doc = get_active_document()
    if not doc:
        return jsonify({'document': None, 'pages': []})
    pages = get_document_pages(doc['id'])
    return jsonify({'document': doc, 'pages': pages})


# ── Sohbet (AI, sadece aktif belgeye dayanarak) ─────────────────────────────
@app.route('/api/chat', methods=['POST'])
def api_chat():
    d = request.get_json(force=True)
    question = (d.get('question') or '').strip()
    session_id = (d.get('session_id') or '').strip() or str(uuid.uuid4())
    if not question:
        return jsonify({'error': 'Soru boş olamaz'}), 400

    doc = get_active_document()
    if not doc:
        return jsonify({'error': 'Henüz bir sözleşme belgesi yüklenmemiş.'}), 400

    pages = get_document_pages(doc['id'])
    context_text = ai.build_context(pages, question)
    api_key = get_setting('deepseek_api_key', '')
    model = get_setting('deepseek_model', 'deepseek-chat')

    conn = get_db()
    history_rows = conn.execute(
        'SELECT role, text FROM chat_messages WHERE session_id = ? ORDER BY id DESC LIMIT 6',
        (session_id,)
    ).fetchall()
    history = [dict(r) for r in reversed(history_rows)]

    try:
        answer = ai.ask(question, context_text, api_key, model, history)
    except ai.AIError as e:
        conn.close()
        return jsonify({'error': str(e)}), 502

    conn.execute('INSERT INTO chat_messages (session_id, role, text, created_at) VALUES (?, ?, ?, ?)',
                 (session_id, 'user', question, now()))
    conn.execute('INSERT INTO chat_messages (session_id, role, text, created_at) VALUES (?, ?, ?, ?)',
                 (session_id, 'assistant', answer, now()))
    conn.commit()
    conn.close()

    return jsonify({'answer': answer, 'session_id': session_id})


if __name__ == '__main__':
    app.run(debug=True, port=5001)
