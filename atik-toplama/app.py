import json
import os
import datetime
from functools import wraps

from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db, init_db, now, today, ROLES, SUPERVISOR_ROLES, NOTIFICATION_TYPES
from overpass import (resolve_neighborhood, fetch_streets, NeighborhoodNotFound,
                      search_districts, search_neighborhoods)
import telegram_notify as tg

# ── App kurulum ─────────────────────────────────────────────────────────────
app = Flask(__name__)

_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
_cfg = {}
if os.path.exists(_config_path):
    with open(_config_path, 'r', encoding='utf-8') as f:
        _cfg = json.load(f)

app.secret_key = _cfg.get('secret_key') or os.environ.get('SECRET_KEY') or 'degistir-bunu'
app.permanent_session_lifetime = datetime.timedelta(days=30)
init_db()


# ── Auth yardımcıları ───────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get('user_id'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'giris_gerekli'}), 401
            return redirect(url_for('login_page'))
        return f(*a, **kw)
    return wrapped


def supervisor_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if session.get('role') not in SUPERVISOR_ROLES:
            return jsonify({'error': 'yetki_yok'}), 403
        return f(*a, **kw)
    return login_required(wrapped)


def _me():
    return {
        'id': session['user_id'],
        'username': session['username'],
        'display_name': session['display_name'],
        'role': session['role'],
        'district_id': session.get('district_id'),
    }


def _user_neighborhoods(user_id, role=None):
    conn = get_db()
    if role and role not in SUPERVISOR_ROLES:
        # Saha personeli: kişiye özel veya ekip geneli (assigned_user_id IS NULL, team_type eşleşen) atamalardaki mahalleler
        rows = conn.execute(
            'SELECT DISTINCT n.* FROM neighborhoods n '
            'JOIN route_assignments a ON a.neighborhood_id = n.id '
            'WHERE (a.work_date IS NULL OR a.work_date = ?) '
            'AND a.team_type = ? '
            'AND (a.assigned_user_id = ? OR a.assigned_user_id IS NULL) '
            'ORDER BY n.name',
            (today(), role, user_id)
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT n.* FROM neighborhoods n '
            'JOIN user_neighborhoods un ON un.neighborhood_id = n.id '
            'WHERE un.user_id = ? ORDER BY un.is_primary DESC, n.name',
            (user_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Sayfa route'ları ────────────────────────────────────────────────────────
@app.route('/login')
def login_page():
    if session.get('user_id'):
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/')
@login_required
def index():
    return render_template('app.html',
                           roles=ROLES,
                           notification_types=NOTIFICATION_TYPES)


# ── Auth API ─────────────────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def api_login():
    d = request.get_json(force=True)
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ?',
                        (d.get('username', '').strip(),)).fetchone()
    conn.close()
    if not user or not check_password_hash(user['password_hash'], d.get('password', '')):
        return jsonify({'error': 'Kullanıcı adı veya şifre hatalı'}), 401
    session.permanent = True
    session.update(user_id=user['id'], username=user['username'],
                   display_name=user['display_name'], role=user['role'],
                   district_id=user['district_id'])
    nbs = _user_neighborhoods(user['id'])
    return jsonify({'ok': True, 'user': dict(user), 'neighborhoods': nbs})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/me')
@login_required
def api_me():
    nbs = _user_neighborhoods(session['user_id'], role=session.get('role'))
    return jsonify({'user': _me(), 'neighborhoods': nbs})


# ── İlçe & Mahalle ──────────────────────────────────────────────────────────
@app.route('/api/districts', methods=['GET'])
@login_required
def list_districts():
    conn = get_db()
    rows = conn.execute('SELECT * FROM districts ORDER BY name').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/districts', methods=['POST'])
@supervisor_required
def create_district():
    d = request.get_json(force=True)
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Ad gerekli'}), 400
    conn = get_db()
    try:
        cur = conn.execute('INSERT INTO districts (name, created_at) VALUES (?, ?)', (name, now()))
        district_id = cur.lastrowid
        # Varsayılan vardiyaları ekle
        for s_name, display, start, end in [
            ('sabah', 'Sabah (06:00–15:00)', 6, 15),
            ('aksam', 'Akşam (15:00–00:00)', 15, 24),
            ('gece',  'Gece (00:00–06:00)',  0, 6),
        ]:
            conn.execute('INSERT OR IGNORE INTO shifts (district_id, name, display_name, start_hour, end_hour) '
                         'VALUES (?, ?, ?, ?, ?)', (district_id, s_name, display, start, end))
        conn.commit()
        conn.close()
        return jsonify({'id': district_id, 'name': name})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


@app.route('/api/districts/<int:did>/neighborhoods', methods=['GET'])
@login_required
def list_neighborhoods(did):
    conn = get_db()
    rows = conn.execute('SELECT * FROM neighborhoods WHERE district_id = ? ORDER BY name',
                        (did,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/neighborhoods', methods=['POST'])
@supervisor_required
def create_neighborhood():
    d = request.get_json(force=True)
    query = (d.get('query') or '').strip()
    district_id = d.get('district_id')
    if not query or not district_id:
        return jsonify({'error': 'Eksik alan'}), 400

    conn = get_db()
    existing = conn.execute(
        'SELECT id FROM neighborhoods WHERE district_id = ? AND name = ?',
        (district_id, query)
    ).fetchone()
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
        return jsonify({'error': f'OSM hatası: {e}'}), 502

    cur = conn.execute(
        'INSERT INTO neighborhoods (district_id, name, osm_id, center_lat, center_lon, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (district_id, query, info.get('osm_id'), info['lat'], info['lon'], now())
    )
    nb_id = cur.lastrowid

    # Oluşturan kullanıcıyı otomatik olarak bu mahalleye ata
    conn.execute(
        'INSERT OR IGNORE INTO user_neighborhoods (user_id, neighborhood_id, is_primary) VALUES (?, ?, ?)',
        (session['user_id'], nb_id, 1)
    )

    streets = []
    if info.get('osm_id'):
        try:
            streets = fetch_streets(info['osm_id'])
        except Exception as e:
            app.logger.warning(f'Sokak çekme hatası: {e}')

    for s in streets:
        conn.execute(
            'INSERT OR IGNORE INTO streets (neighborhood_id, osm_way_id, name, geometry, created_at) '
            'VALUES (?, ?, ?, ?, ?)',
            (nb_id, s['osm_way_id'], s['name'], json.dumps(s['coords']), now())
        )
    conn.commit()
    conn.close()
    return jsonify({'id': nb_id, 'name': query, 'street_count': len(streets)})


@app.route('/api/neighborhoods/<int:nid>/streets', methods=['GET'])
@login_required
def neighborhood_streets(nid):
    conn = get_db()
    rows = conn.execute('SELECT id, name, geometry FROM streets WHERE neighborhood_id = ? ORDER BY name',
                        (nid,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({'id': r['id'], 'name': r['name'], 'geometry': json.loads(r['geometry'])})
    return jsonify(result)


# ── Kullanıcı yönetimi (supervisor) ─────────────────────────────────────────
@app.route('/api/users', methods=['GET'])
@supervisor_required
def list_users():
    district_id = session.get('district_id')
    conn = get_db()
    if session['role'] == 'santiye_amiri':
        rows = conn.execute(
            'SELECT id, username, display_name, role, district_id, default_shift_id, is_active '
            'FROM users ORDER BY display_name'
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT id, username, display_name, role, district_id, default_shift_id, is_active '
            'FROM users WHERE district_id = ? ORDER BY display_name',
            (district_id,)
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/users', methods=['POST'])
@supervisor_required
def create_user():
    d = request.get_json(force=True)
    username = (d.get('username') or '').strip()
    password = (d.get('password') or '').strip()
    display_name = (d.get('display_name') or '').strip()
    role = d.get('role', '')
    district_id = d.get('district_id') or session.get('district_id')
    default_shift_id = d.get('default_shift_id') or None
    neighborhood_id = d.get('neighborhood_id') or None

    if not (username and password and display_name and role):
        return jsonify({'error': 'Kullanıcı adı, şifre, ad ve rol zorunludur'}), 400
    if role not in ROLES:
        return jsonify({'error': 'Geçersiz rol'}), 400

    conn = get_db()
    try:
        ph = generate_password_hash(password)
        cur = conn.execute(
            'INSERT INTO users (username, password_hash, display_name, role, district_id, '
            'default_shift_id, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)',
            (username, ph, display_name, role, district_id, default_shift_id, now())
        )
        uid = cur.lastrowid
        if neighborhood_id:
            conn.execute(
                'INSERT OR IGNORE INTO user_neighborhoods (user_id, neighborhood_id, is_primary) VALUES (?, ?, 1)',
                (uid, neighborhood_id)
            )
        conn.commit()
        conn.close()
        return jsonify({'id': uid, 'display_name': display_name, 'username': username})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


@app.route('/api/users/<int:uid>', methods=['PUT'])
@supervisor_required
def update_user(uid):
    d = request.get_json(force=True)
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Kullanıcı bulunamadı'}), 404

    display_name = (d.get('display_name') or user['display_name']).strip()
    role = d.get('role') or user['role']
    default_shift_id = d.get('default_shift_id') or None
    is_active = int(d.get('is_active', 1))
    password = (d.get('password') or '').strip()

    if role not in ROLES:
        conn.close()
        return jsonify({'error': 'Geçersiz rol'}), 400

    if password:
        ph = generate_password_hash(password)
        conn.execute(
            'UPDATE users SET display_name=?, role=?, default_shift_id=?, is_active=?, password_hash=? WHERE id=?',
            (display_name, role, default_shift_id, is_active, ph, uid)
        )
    else:
        conn.execute(
            'UPDATE users SET display_name=?, role=?, default_shift_id=?, is_active=? WHERE id=?',
            (display_name, role, default_shift_id, is_active, uid)
        )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/users/<int:uid>/neighborhoods', methods=['GET'])
@supervisor_required
def user_neighborhood_list(uid):
    conn = get_db()
    rows = conn.execute(
        'SELECT n.id, n.name, un.is_primary FROM neighborhoods n '
        'JOIN user_neighborhoods un ON un.neighborhood_id = n.id '
        'WHERE un.user_id = ?', (uid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/users/<int:uid>/neighborhoods', methods=['POST'])
@supervisor_required
def assign_user_neighborhood(uid):
    d = request.get_json(force=True)
    nid = d.get('neighborhood_id')
    is_primary = int(d.get('is_primary', 1))
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO user_neighborhoods (user_id, neighborhood_id, is_primary) VALUES (?, ?, ?)',
                 (uid, nid, is_primary))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ── Vardiyalar ───────────────────────────────────────────────────────────────
@app.route('/api/shifts', methods=['GET'])
@login_required
def list_shifts():
    district_id = request.args.get('district_id') or session.get('district_id')
    if not district_id:
        return jsonify([])
    conn = get_db()
    rows = conn.execute('SELECT * FROM shifts WHERE district_id = ? ORDER BY start_hour',
                        (district_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def _current_shift(district_id):
    """Şu anki saate göre aktif vardiyayı döner."""
    hour = datetime.datetime.now().hour
    conn = get_db()
    shifts = conn.execute('SELECT * FROM shifts WHERE district_id = ? ORDER BY start_hour',
                          (district_id,)).fetchall()
    conn.close()
    for s in shifts:
        start, end = s['start_hour'], s['end_hour']
        if end > start:  # normal aralık (ör. 6-15)
            if start <= hour < end:
                return dict(s)
        else:            # gece yarısını kesen aralık (ör. 15-6)
            if hour >= start or hour < end:
                return dict(s)
    return None


# ── Güzergah Atamaları ───────────────────────────────────────────────────────
@app.route('/api/assignments', methods=['GET'])
@login_required
def list_assignments():
    nid = request.args.get('neighborhood_id')
    date = request.args.get('date') or today()
    team_type = request.args.get('team_type')
    conn = get_db()
    q = 'SELECT ra.*, u.display_name as assigned_user_name FROM route_assignments ra ' \
        'LEFT JOIN users u ON u.id = ra.assigned_user_id ' \
        'WHERE ra.neighborhood_id = ? AND (ra.work_date IS NULL OR ra.work_date = ?)'
    params = [nid, date]
    if team_type:
        q += ' AND ra.team_type = ?'
        params.append(team_type)
    rows = conn.execute(q, params).fetchall()
    result = []
    for row in rows:
        r = dict(row)
        streets = conn.execute(
            'SELECT s.id, s.name FROM assignment_streets as_t JOIN streets s ON s.id = as_t.street_id '
            'WHERE as_t.assignment_id = ?', (r['id'],)
        ).fetchall()
        r['streets'] = [dict(s) for s in streets]
        result.append(r)
    conn.close()
    return jsonify(result)


@app.route('/api/assignments', methods=['POST'])
@supervisor_required
def create_assignment():
    d = request.get_json(force=True)
    nid = d.get('neighborhood_id')
    team_type = d.get('team_type')
    shift_id = d.get('shift_id')
    permanent = d.get('permanent', False)
    work_date = None if permanent else (d.get('work_date') or today())
    street_ids = d.get('street_ids', [])
    assigned_user_id = d.get('assigned_user_id')

    if not (nid and team_type and street_ids):
        return jsonify({'error': 'Eksik alan'}), 400

    conn = get_db()
    cur = conn.execute(
        'INSERT INTO route_assignments (neighborhood_id, team_type, shift_id, work_date, assigned_user_id, assigned_by, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (nid, team_type, shift_id, work_date, assigned_user_id, session['user_id'], now())
    )
    aid = cur.lastrowid
    for sid in street_ids:
        conn.execute('INSERT OR IGNORE INTO assignment_streets (assignment_id, street_id) VALUES (?, ?)', (aid, sid))
    conn.commit()
    conn.close()
    return jsonify({'id': aid, 'street_count': len(street_ids)})


@app.route('/api/assignments/<int:aid>', methods=['DELETE'])
@supervisor_required
def delete_assignment(aid):
    conn = get_db()
    conn.execute('DELETE FROM route_assignments WHERE id = ?', (aid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ── Süpürgeci: bugünkü görevim ───────────────────────────────────────────────
@app.route('/api/my/streets', methods=['GET'])
@login_required
def my_streets():
    """Süpürgecinin bugün için atanmış sokaklarını ve tamamlama durumlarını döner."""
    work_date = request.args.get('date') or today()
    uid = session['user_id']
    role = session['role']
    nid = request.args.get('neighborhood_id')

    conn = get_db()
    # Bu kullanıcıya veya ekip türüne atanmış atamalar (kalıcı + bugünkü)
    assignments = conn.execute(
        'SELECT id FROM route_assignments WHERE neighborhood_id = ? '
        'AND (work_date IS NULL OR work_date = ?) '
        'AND team_type = ? AND (assigned_user_id = ? OR assigned_user_id IS NULL)',
        (nid, work_date, role, uid)
    ).fetchall()

    if not assignments:
        conn.close()
        return jsonify({'streets': [], 'completed_ids': []})

    aid_list = [r['id'] for r in assignments]
    placeholders = ','.join('?' * len(aid_list))

    streets_rows = conn.execute(
        f'SELECT DISTINCT s.id, s.name, s.geometry FROM streets s '
        f'JOIN assignment_streets ast ON ast.street_id = s.id '
        f'WHERE ast.assignment_id IN ({placeholders})',
        aid_list
    ).fetchall()

    completed_rows = conn.execute(
        f'SELECT DISTINCT street_id FROM street_completions '
        f'WHERE user_id = ? AND work_date = ? AND neighborhood_id = ?',
        (uid, work_date, nid)
    ).fetchall()
    completed_ids = {r['street_id'] for r in completed_rows}

    streets = []
    for r in streets_rows:
        streets.append({
            'id': r['id'],
            'name': r['name'],
            'geometry': json.loads(r['geometry']),
            'completed': r['id'] in completed_ids,
        })
    conn.close()
    return jsonify({'streets': streets, 'completed_ids': list(completed_ids)})


# ── Sokak tamamlama (fotoğrafla) ─────────────────────────────────────────────
@app.route('/api/streets/<int:sid>/complete', methods=['POST'])
@login_required
def complete_street(sid):
    photo = request.files.get('photo')
    work_date = request.form.get('work_date') or today()
    assignment_id = request.form.get('assignment_id')
    note = request.form.get('note', '').strip()
    nid = int(request.form.get('neighborhood_id', 0))

    conn = get_db()
    # Zaten tamamlanmış mı?
    existing = conn.execute(
        'SELECT id FROM street_completions WHERE street_id = ? AND user_id = ? AND work_date = ?',
        (sid, session['user_id'], work_date)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'ok': True, 'already': True})

    # Telegram'a fotoğraf gönder
    photo_sent = False
    if photo:
        street_row = conn.execute(
            'SELECT s.name, s.geometry, n.name as nb_name FROM streets s '
            'JOIN neighborhoods n ON n.id = s.neighborhood_id WHERE s.id = ?', (sid,)
        ).fetchone()
        if street_row:
            shift = None
            if session.get('district_id'):
                shift = _current_shift(session['district_id'])
            shift_name = shift['display_name'] if shift else 'Bilinmeyen Vardiya'
            # Sokak orta noktasını hesapla
            street_lat = street_lon = None
            try:
                geom = json.loads(street_row['geometry'])
                if geom:
                    mid = geom[len(geom) // 2]
                    street_lat, street_lon = mid[0], mid[1]
            except Exception:
                pass
            photo_sent = tg.notify_street_complete(
                street_name=street_row['name'],
                user_display=session['display_name'],
                neighborhood_name=street_row['nb_name'],
                shift_name=shift_name,
                photo_file=photo.stream,
                neighborhood_id=nid,
                lat=street_lat,
                lon=street_lon,
            )

    conn.execute(
        'INSERT INTO street_completions (street_id, assignment_id, user_id, neighborhood_id, work_date, completed_at, photo_sent, note) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (sid, assignment_id, session['user_id'], nid, work_date, now(), int(photo_sent), note)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'photo_sent': photo_sent})


# ── Çavuş: mahalle ilerleme durumu ──────────────────────────────────────────
@app.route('/api/neighborhoods/<int:nid>/progress', methods=['GET'])
@login_required
def neighborhood_progress(nid):
    work_date = request.args.get('date') or today()
    team_type = request.args.get('team_type')

    conn = get_db()
    # Bu mahalleye atanmış sokaklar (kalıcı + bugün)
    q = ('SELECT DISTINCT s.id, s.name, s.geometry FROM streets s '
         'JOIN assignment_streets ast ON ast.street_id = s.id '
         'JOIN route_assignments ra ON ra.id = ast.assignment_id '
         'WHERE ra.neighborhood_id = ? AND (ra.work_date IS NULL OR ra.work_date = ?)')
    params = [nid, work_date]
    if team_type:
        q += ' AND ra.team_type = ?'
        params.append(team_type)
    assigned = conn.execute(q, params).fetchall()

    # Tamamlanmış sokaklar + kimin tamamladığı
    completed = conn.execute(
        'SELECT sc.street_id, u.display_name, sc.completed_at, sc.photo_sent '
        'FROM street_completions sc JOIN users u ON u.id = sc.user_id '
        'WHERE sc.neighborhood_id = ? AND sc.work_date = ?',
        (nid, work_date)
    ).fetchall()
    completed_map = {r['street_id']: dict(r) for r in completed}

    streets = []
    for r in assigned:
        s = {'id': r['id'], 'name': r['name'], 'geometry': json.loads(r['geometry'])}
        c = completed_map.get(r['id'])
        s['completed'] = bool(c)
        if c:
            s['completed_by'] = c['display_name']
            s['completed_at'] = c['completed_at']
            s['photo_sent'] = bool(c['photo_sent'])
        streets.append(s)
    conn.close()
    return jsonify({
        'total': len(streets),
        'completed': sum(1 for s in streets if s['completed']),
        'streets': streets,
    })


# ── Bildirim Havuzu ──────────────────────────────────────────────────────────
@app.route('/api/notifications', methods=['GET'])
@login_required
def list_notifications():
    nid = request.args.get('neighborhood_id')
    status = request.args.get('status', 'open')
    conn = get_db()
    rows = conn.execute(
        'SELECT n.*, u.display_name as creator_name, s.name as street_name '
        'FROM notifications n '
        'JOIN users u ON u.id = n.created_by '
        'LEFT JOIN streets s ON s.id = n.street_id '
        'WHERE n.neighborhood_id = ? AND n.status = ? ORDER BY n.created_at DESC',
        (nid, status)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/notifications', methods=['POST'])
@login_required
def create_notification():
    d = request.get_json(force=True)
    nid = d.get('neighborhood_id')
    lat, lon = d.get('lat'), d.get('lon')
    ntype = d.get('type')
    note = (d.get('note') or '').strip()
    street_id = d.get('street_id')

    if not (nid and ntype in NOTIFICATION_TYPES):
        return jsonify({'error': 'Eksik veya geçersiz alan'}), 400

    conn = get_db()
    street_name = None

    # Sokak ID verilmişse: koordinatı geometriden al, adı doğrudan biliyoruz
    if street_id:
        srow = conn.execute('SELECT name, geometry FROM streets WHERE id = ?', (street_id,)).fetchone()
        if srow:
            street_name = srow['name']
            if lat is None or lon is None:
                try:
                    geom = json.loads(srow['geometry'])
                    if geom:
                        mid = geom[len(geom) // 2]
                        lat, lon = mid[0], mid[1]
                except Exception:
                    pass

    # Koordinat hâlâ yoksa: GPS zorunlu
    if lat is None or lon is None:
        conn.close()
        return jsonify({'error': 'Konum koordinatı gerekli'}), 400

    # Sokak ID yoksa en yakın sokağı bul (GPS bildirimleri için)
    if not street_id:
        try:
            streets = conn.execute('SELECT id, name, geometry FROM streets WHERE neighborhood_id = ?', (nid,)).fetchall()
            best = float('inf')
            for s in streets:
                geom = json.loads(s['geometry'])
                for pt in geom:
                    dist = (pt[0] - lat) ** 2 + (pt[1] - lon) ** 2
                    if dist < best:
                        best = dist
                        street_name = s['name']
                        street_id = s['id']
        except Exception:
            pass

    _, _, target_team = NOTIFICATION_TYPES[ntype]

    cur = conn.execute(
        'INSERT INTO notifications (neighborhood_id, street_id, lat, lon, type, note, created_by, created_at, target_team) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (nid, street_id, lat, lon, ntype, note, session['user_id'], now(), target_team)
    )
    notif_id = cur.lastrowid
    nb = conn.execute('SELECT name FROM neighborhoods WHERE id = ?', (nid,)).fetchone()
    conn.commit()

    notif = conn.execute(
        'SELECT n.*, s.name as street_name FROM notifications n '
        'LEFT JOIN streets s ON s.id = n.street_id WHERE n.id = ?', (notif_id,)
    ).fetchone()
    conn.close()

    tg.notify_new_notification(dict(notif), session['display_name'],
                               nb['name'] if nb else '',
                               street_name=street_name,
                               neighborhood_id=nid)

    return jsonify(dict(notif))


@app.route('/api/notifications/<int:nid>/accept', methods=['POST'])
@login_required
def accept_notification(nid):
    conn = get_db()
    conn.execute(
        'UPDATE notifications SET status = ?, accepted_by = ?, accepted_at = ? WHERE id = ? AND status = ?',
        ('accepted', session['user_id'], now(), nid, 'open')
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/notifications/<int:nid>/resolve', methods=['POST'])
@login_required
def resolve_notification(nid):
    import threading, io
    photo_file = request.files.get('photo')
    photo_data = photo_file.read() if photo_file else None
    note = request.form.get('note', '').strip()

    conn = get_db()
    notif = conn.execute(
        'SELECT n.*, nb.name as nb_name, nb.id as nb_id, s.name as street_name '
        'FROM notifications n '
        'JOIN neighborhoods nb ON nb.id = n.neighborhood_id '
        'LEFT JOIN streets s ON s.id = n.street_id '
        'WHERE n.id = ?', (nid,)
    ).fetchone()
    if not notif:
        conn.close()
        return jsonify({'error': 'bulunamadı'}), 404

    # DB'yi hemen güncelle — istemciyi Telegram'ı bekletme
    conn.execute(
        'UPDATE notifications SET status = ?, resolved_by = ?, resolved_at = ? WHERE id = ?',
        ('resolved', session['user_id'], now(), nid)
    )
    conn.commit()
    conn.close()

    # Telegram arka planda gönder
    notif_dict = dict(notif)
    user_display = session['display_name']
    nb_name, nb_id = notif['nb_name'], notif['nb_id']
    street_name = notif['street_name']

    def _send_tg():
        photo_stream = io.BytesIO(photo_data) if photo_data else None
        tg.notify_resolved(notif_dict, user_display, nb_name,
                           photo_file=photo_stream, neighborhood_id=nb_id,
                           street_name=street_name, note=note)

    threading.Thread(target=_send_tg, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/api/notifications/<int:nid>/comments', methods=['GET'])
@login_required
def get_notification_comments(nid):
    conn = get_db()
    rows = conn.execute(
        'SELECT nc.id, nc.text, nc.created_at, u.display_name as user_name '
        'FROM notification_comments nc '
        'JOIN users u ON u.id = nc.user_id '
        'WHERE nc.notification_id = ? ORDER BY nc.created_at',
        (nid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/notifications/<int:nid>/comments', methods=['POST'])
@login_required
def add_notification_comment(nid):
    d = request.get_json(force=True)
    text = (d.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'Yorum metni gerekli'}), 400
    conn = get_db()
    cur = conn.execute(
        'INSERT INTO notification_comments (notification_id, user_id, text, created_at) VALUES (?, ?, ?, ?)',
        (nid, session['user_id'], text, now())
    )
    cid = cur.lastrowid
    row = conn.execute(
        'SELECT nc.id, nc.text, nc.created_at, u.display_name as user_name '
        'FROM notification_comments nc JOIN users u ON u.id = nc.user_id WHERE nc.id = ?', (cid,)
    ).fetchone()
    conn.commit()
    conn.close()
    return jsonify(dict(row))


@app.route('/api/notifications/<int:nid>/cancel', methods=['POST'])
@supervisor_required
def cancel_notification(nid):
    conn = get_db()
    conn.execute(
        'UPDATE notifications SET status = ?, cancelled_by = ?, cancelled_at = ? WHERE id = ?',
        ('cancelled', session['user_id'], now(), nid)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ── OSM İl/İlçe/Mahalle arama ───────────────────────────────────────────────

_TR_PROVINCES = [
    'Adana', 'Adıyaman', 'Afyonkarahisar', 'Ağrı', 'Aksaray', 'Amasya',
    'Ankara', 'Antalya', 'Ardahan', 'Artvin', 'Aydın', 'Balıkesir',
    'Bartın', 'Batman', 'Bayburt', 'Bilecik', 'Bingöl', 'Bitlis', 'Bolu',
    'Burdur', 'Bursa', 'Çanakkale', 'Çankırı', 'Çorum', 'Denizli',
    'Diyarbakır', 'Düzce', 'Edirne', 'Elazığ', 'Erzincan', 'Erzurum',
    'Eskişehir', 'Gaziantep', 'Giresun', 'Gümüşhane', 'Hakkari', 'Hatay',
    'Iğdır', 'Isparta', 'İstanbul', 'İzmir', 'Kahramanmaraş', 'Karabük',
    'Karaman', 'Kars', 'Kastamonu', 'Kayseri', 'Kilis', 'Kırıkkale',
    'Kırklareli', 'Kırşehir', 'Kocaeli', 'Konya', 'Kütahya', 'Malatya',
    'Manisa', 'Mardin', 'Mersin', 'Muğla', 'Muş', 'Nevşehir', 'Niğde',
    'Ordu', 'Osmaniye', 'Rize', 'Sakarya', 'Samsun', 'Siirt', 'Sinop',
    'Sivas', 'Şanlıurfa', 'Şırnak', 'Tekirdağ', 'Tokat', 'Trabzon',
    'Tunceli', 'Uşak', 'Van', 'Yalova', 'Yozgat', 'Zonguldak',
]


@app.route('/api/osm/provinces')
@login_required
def osm_provinces():
    return jsonify(_TR_PROVINCES)


@app.route('/api/osm/districts')
@login_required
def osm_districts():
    province = request.args.get('province', '').strip()
    if not province:
        return jsonify({'error': 'İl adı gerekli'}), 400
    try:
        districts = search_districts(province)
        return jsonify(districts)
    except NeighborhoodNotFound as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': f'OSM hatası: {e}'}), 502


@app.route('/api/osm/neighborhoods')
@login_required
def osm_neighborhoods_list():
    province = request.args.get('province', '').strip()
    district = request.args.get('district', '').strip()
    if not province or not district:
        return jsonify({'error': 'İl ve ilçe adı gerekli'}), 400
    try:
        nbs = search_neighborhoods(district, province)
        return jsonify(nbs)
    except NeighborhoodNotFound as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': f'OSM hatası: {e}'}), 502


# ── Sokak detay (tüm roller) ─────────────────────────────────────────────────
@app.route('/api/streets/<int:sid>/details')
@login_required
def street_details(sid):
    work_date = request.args.get('date') or today()
    nid = request.args.get('neighborhood_id', type=int)

    conn = get_db()
    street = conn.execute(
        'SELECT s.*, n.id as nb_id, n.name as nb_name FROM streets s '
        'JOIN neighborhoods n ON n.id = s.neighborhood_id WHERE s.id = ?', (sid,)
    ).fetchone()
    if not street:
        conn.close()
        return jsonify({'error': 'Sokak bulunamadı'}), 404

    nb_id = nid or street['nb_id']

    assignments = conn.execute(
        'SELECT ra.team_type, sh.display_name as shift_name, '
        'u.display_name as user_name, ra.work_date '
        'FROM route_assignments ra '
        'JOIN assignment_streets ast ON ast.assignment_id = ra.id '
        'LEFT JOIN shifts sh ON sh.id = ra.shift_id '
        'LEFT JOIN users u ON u.id = ra.assigned_user_id '
        'WHERE ast.street_id = ? AND ra.neighborhood_id = ? '
        'AND (ra.work_date IS NULL OR ra.work_date = ?)',
        (sid, nb_id, work_date)
    ).fetchall()

    completions = conn.execute(
        'SELECT sc.completed_at, sc.photo_sent, sc.note, '
        'u.display_name as user_name, u.role '
        'FROM street_completions sc '
        'JOIN users u ON u.id = sc.user_id '
        'WHERE sc.street_id = ? AND sc.work_date = ?',
        (sid, work_date)
    ).fetchall()

    notifications = conn.execute(
        'SELECT n.id, n.type, n.note, n.lat, n.lon, n.street_id, n.created_at, '
        'u.display_name as creator_name '
        'FROM notifications n JOIN users u ON u.id = n.created_by '
        'WHERE n.street_id = ? AND n.status = ? ORDER BY n.created_at DESC LIMIT 10',
        (sid, 'open')
    ).fetchall()

    supervisors = conn.execute(
        'SELECT u.display_name, u.role FROM users u '
        'JOIN user_neighborhoods un ON un.user_id = u.id '
        'WHERE un.neighborhood_id = ? AND u.role IN (?,?) ORDER BY u.role',
        (nb_id, 'cavus', 'onbasi')
    ).fetchall()

    conn.close()
    return jsonify({
        'street_name': street['name'],
        'assignments': [dict(r) for r in assignments],
        'completions': [dict(r) for r in completions],
        'notifications': [dict(r) for r in notifications],
        'supervisors': [dict(r) for r in supervisors],
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5057)), debug=False)
