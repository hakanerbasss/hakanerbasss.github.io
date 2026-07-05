"""Komut satırı yönetim aracı.

Kullanım:
  python manage.py initdb
  python manage.py adddistrict "Avcılar"
  python manage.py addneighborhood <district_id> "Gümüşpala Mahallesi"
  python manage.py adduser <username> <sifre> "<Görünen Ad>" <rol> <district_id> [telegram_chat_id]
  python manage.py assignnb <user_id> <neighborhood_id> [is_primary=1]
  python manage.py listusers
  python manage.py passwd <username> <yeni_sifre>
  python manage.py roles
"""
import sys
from werkzeug.security import generate_password_hash
from db import get_db, init_db, now, ROLES


def cmd_initdb(args):
    init_db()
    print("Veritabanı başlatıldı.")


def cmd_roles(args):
    for k, v in ROLES.items():
        print(f"  {k:20s} → {v}")


def cmd_adddistrict(args):
    if not args:
        print("Kullanım: adddistrict <ad>"); return
    name = args[0]
    conn = get_db()
    try:
        cur = conn.execute('INSERT INTO districts (name, created_at) VALUES (?, ?)', (name, now()))
        did = cur.lastrowid
        for s_name, display, start, end in [
            ('sabah', 'Sabah (06:00–15:00)', 6, 15),
            ('aksam', 'Akşam (15:00–00:00)', 15, 24),
            ('gece',  'Gece (00:00–06:00)',  0, 6),
        ]:
            conn.execute('INSERT OR IGNORE INTO shifts (district_id, name, display_name, start_hour, end_hour) '
                         'VALUES (?, ?, ?, ?, ?)', (did, s_name, display, start, end))
        conn.commit()
        print(f"İlçe eklendi: #{did} {name}")
    except Exception as e:
        print(f"Hata: {e}")
    finally:
        conn.close()


def cmd_addneighborhood(args):
    if len(args) < 2:
        print("Kullanım: addneighborhood <district_id> <ad>"); return
    did, name = int(args[0]), args[1]
    conn = get_db()
    try:
        cur = conn.execute('INSERT INTO neighborhoods (district_id, name, created_at) VALUES (?, ?, ?)',
                           (did, name, now()))
        print(f"Mahalle eklendi: #{cur.lastrowid} {name}")
        conn.commit()
    except Exception as e:
        print(f"Hata: {e}")
    finally:
        conn.close()


def cmd_adduser(args):
    if len(args) < 5:
        print("Kullanım: adduser <username> <sifre> \"<Ad>\" <rol> <district_id> [telegram_chat_id]")
        print("Roller:"); cmd_roles([])
        return
    username, password, display_name, role = args[0], args[1], args[2], args[3]
    district_id = int(args[4])
    telegram_chat_id = args[5] if len(args) > 5 else None
    if role not in ROLES:
        print(f"Geçersiz rol: {role}. Geçerli roller:"); cmd_roles([]); return
    conn = get_db()
    try:
        cur = conn.execute(
            'INSERT INTO users (username, password_hash, display_name, role, district_id, telegram_chat_id, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (username, generate_password_hash(password), display_name, role, district_id, telegram_chat_id, now())
        )
        conn.commit()
        print(f"Kullanıcı eklendi: #{cur.lastrowid} {username} ({display_name}) [{role}]")
    except Exception as e:
        print(f"Hata: {e}")
    finally:
        conn.close()


def cmd_assignnb(args):
    if len(args) < 2:
        print("Kullanım: assignnb <user_id> <neighborhood_id> [is_primary=1]"); return
    uid, nid = int(args[0]), int(args[1])
    is_primary = int(args[2]) if len(args) > 2 else 1
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO user_neighborhoods (user_id, neighborhood_id, is_primary) VALUES (?, ?, ?)',
                 (uid, nid, is_primary))
    conn.commit()
    conn.close()
    print(f"Kullanıcı #{uid} → Mahalle #{nid} atandı (birincil={is_primary})")


def cmd_listusers(args):
    conn = get_db()
    for r in conn.execute('SELECT id, username, display_name, role, district_id FROM users ORDER BY id'):
        nbs = conn.execute('SELECT n.name FROM neighborhoods n JOIN user_neighborhoods un ON un.neighborhood_id=n.id WHERE un.user_id=?', (r['id'],)).fetchall()
        nb_names = ', '.join(x['name'] for x in nbs) or '—'
        print(f"#{r['id']:3d}  {r['username']:15s}  {r['display_name']:20s}  {r['role']:20s}  d={r['district_id']}  [{nb_names}]")
    conn.close()


def cmd_passwd(args):
    if len(args) < 2:
        print("Kullanım: passwd <username> <yeni_sifre>"); return
    conn = get_db()
    cur = conn.execute('UPDATE users SET password_hash = ? WHERE username = ?',
                       (generate_password_hash(args[1]), args[0]))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        print(f"Kullanıcı bulunamadı: {args[0]}")
    else:
        print(f"Şifre güncellendi: {args[0]}")


COMMANDS = {
    'initdb': cmd_initdb,
    'adddistrict': cmd_adddistrict,
    'addneighborhood': cmd_addneighborhood,
    'adduser': cmd_adduser,
    'assignnb': cmd_assignnb,
    'listusers': cmd_listusers,
    'passwd': cmd_passwd,
    'roles': cmd_roles,
}

if __name__ == '__main__':
    init_db()
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
