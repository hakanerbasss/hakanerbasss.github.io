import json
import os
from functools import wraps

from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from werkzeug.security import check_password_hash

from db import get_db, init_db, now, POINT_TYPES
from overpass import resolve_neighborhood, fetch_streets, NeighborhoodNotFound
from telegram_notify import notify_point, send_message

app = Flask(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
_cfg = {}
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        _cfg = json.load(f)

app.secret_key = _cfg.get('secret_key') or os.environ.get('SECRET_KEY') or 'gelistirme-anahtari-degistir'

init_db()


def login_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get('user_id'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'giris_gerekli'}), 401
            return redirect(url_for('login_page'))
        return f(*a, **kw)
    return wrapped


# ── Sayfalar ──────────────────────────────────────────────
@app.route('/login', methods=['GET'])
def login_page():
    if session.get('user_id'):
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/')
@login_required
def index():
    return render_template('index.html', point_types=POINT_TYPES, user=session.get('display_name'))


# ── Auth API ──────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(force=True)
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Kullanıcı adı veya şifre hatalı'}), 401
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['display_name'] = user['display_name']
    return jsonify({'ok': True, 'display_name': user['display_name']})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/me')
@login_required
def api_me():
    return jsonify({'username': session['username'], 'display_name': session['display_name']})


# ── Mahalle ───────────────────────────────────────────────
@app.route('/api/neighborhoods', methods=['GET'])
@login_required
def list_neighborhoods():
    conn = get_db()
    rows = conn.execute('SELECT id, name, center_lat, center_lon FROM neighborhoods ORDER BY name').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/neighborhoods', methods=['POST'])
@login_required
def create_neighborhood():
    data = request.get_json(force=True)
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({'error': 'Mahalle adı gerekli'}), 400

    conn = get_db()
    existing = conn.execute('SELECT id FROM neighborhoods WHERE name = ?', (query,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'id': existing['id'], 'name': query, 'existing': True})

    try:
        info = resolve_neighborhood(query)
    except NeighborhoodNotFound as e:
        conn.close()
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        conn.close()
        return jsonify({'error': f'OSM sorgusu başarısız: {e}'}), 502

    cur = conn.execute(
        'INSERT INTO neighborhoods (name, osm_id, center_lat, center_lon, created_at) VALUES (?, ?, ?, ?, ?)',
        (query, info.get('osm_id'), info['lat'], info['lon'], now())
    )
    neighborhood_id = cur.lastrowid

    streets = []
    if info.get('osm_id'):
        try:
            streets = fetch_streets(info['osm_id'])
        except Exception as e:
            streets = []
            app.logger.warning(f"Sokak verisi çekilemedi: {e}")

    for s in streets:
        conn.execute(
            'INSERT OR IGNORE INTO streets (neighborhood_id, osm_way_id, name, geometry) VALUES (?, ?, ?, ?)',
            (neighborhood_id, s['osm_way_id'], s['name'], json.dumps(s['coords']))
        )
    conn.commit()
    conn.close()
    return jsonify({'id': neighborhood_id, 'name': query, 'street_count': len(streets)})


@app.route('/api/neighborhoods/<int:nid>')
@login_required
def neighborhood_detail(nid):
    conn = get_db()
    nb = conn.execute('SELECT * FROM neighborhoods WHERE id = ?', (nid,)).fetchone()
    if not nb:
        conn.close()
        return jsonify({'error': 'bulunamadı'}), 404
    streets = conn.execute('SELECT * FROM streets WHERE neighborhood_id = ? ORDER BY name', (nid,)).fetchall()
    points = conn.execute('SELECT * FROM points WHERE neighborhood_id = ? ORDER BY created_at DESC', (nid,)).fetchall()
    conn.close()

    street_list = []
    for s in streets:
        d = dict(s)
        d['geometry'] = json.loads(d['geometry'])
        street_list.append(d)

    return jsonify({
        'neighborhood': dict(nb),
        'streets': street_list,
        'points': [dict(p) for p in points],
        'point_types': POINT_TYPES,
    })


# ── Sokaklar ──────────────────────────────────────────────
@app.route('/api/streets/<int:sid>/visit', methods=['POST'])
@login_required
def set_street_visited(sid):
    data = request.get_json(force=True)
    visited = bool(data.get('visited'))
    conn = get_db()
    if visited:
        conn.execute(
            'UPDATE streets SET visited = 1, visited_by = ?, visited_at = ? WHERE id = ?',
            (session['display_name'], now(), sid)
        )
    else:
        conn.execute('UPDATE streets SET visited = 0, visited_by = NULL, visited_at = NULL WHERE id = ?', (sid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ── Noktalar / Notlar ─────────────────────────────────────
@app.route('/api/points', methods=['POST'])
@login_required
def create_point():
    data = request.get_json(force=True)
    neighborhood_id = data.get('neighborhood_id')
    lat, lon = data.get('lat'), data.get('lon')
    ptype = data.get('type')
    note = (data.get('note') or '').strip()
    notify = bool(data.get('notify'))

    if not (neighborhood_id and lat is not None and lon is not None and ptype in POINT_TYPES):
        return jsonify({'error': 'Eksik veya geçersiz alan'}), 400

    conn = get_db()
    cur = conn.execute(
        'INSERT INTO points (neighborhood_id, lat, lon, type, note, created_by, created_at, notified) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (neighborhood_id, lat, lon, ptype, note, session['display_name'], now(), int(notify))
    )
    point_id = cur.lastrowid
    nb = conn.execute('SELECT name FROM neighborhoods WHERE id = ?', (neighborhood_id,)).fetchone()
    conn.commit()

    point = conn.execute('SELECT * FROM points WHERE id = ?', (point_id,)).fetchone()
    conn.close()

    if notify:
        notify_point(dict(point), nb['name'] if nb else '')

    return jsonify(dict(point))


@app.route('/api/points/<int:pid>/resolve', methods=['POST'])
@login_required
def resolve_point(pid):
    conn = get_db()
    conn.execute(
        'UPDATE points SET resolved = 1, resolved_by = ?, resolved_at = ? WHERE id = ?',
        (session['display_name'], now(), pid)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/points/<int:pid>', methods=['DELETE'])
@login_required
def delete_point(pid):
    conn = get_db()
    conn.execute('DELETE FROM points WHERE id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ── Bitirme ───────────────────────────────────────────────
@app.route('/api/neighborhoods/<int:nid>/finish', methods=['POST'])
@login_required
def finish_neighborhood(nid):
    conn = get_db()
    nb = conn.execute('SELECT * FROM neighborhoods WHERE id = ?', (nid,)).fetchone()
    total = conn.execute('SELECT COUNT(*) c FROM streets WHERE neighborhood_id = ?', (nid,)).fetchone()['c']
    visited = conn.execute('SELECT COUNT(*) c FROM streets WHERE neighborhood_id = ? AND visited = 1', (nid,)).fetchone()['c']
    open_points = conn.execute(
        'SELECT COUNT(*) c FROM points WHERE neighborhood_id = ? AND resolved = 0', (nid,)
    ).fetchone()['c']
    conn.close()

    remaining = total - visited
    text = (
        f"✅ {nb['name']} taraması tamamlandı — {session['display_name']}\n"
        f"Gezilen sokak: {visited}/{total}"
    )
    if remaining > 0:
        text += f"\n⚠️ Girilmeyen sokak sayısı: {remaining}"
    if open_points > 0:
        text += f"\n📍 Açık not/uyarı sayısı: {open_points}"
    send_message(text)

    return jsonify({'total': total, 'visited': visited, 'remaining': remaining, 'open_points': open_points})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5057)), debug=True)
