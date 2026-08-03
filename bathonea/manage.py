"""Komut satırı yönetim aracı.

Kullanım:
  python manage.py initdb
  python manage.py addadmin <username> <sifre>
  python manage.py passwd <username> <yeni_sifre>
  python manage.py listadmins
"""
import sys
from werkzeug.security import generate_password_hash
from db import get_db, init_db, now


def cmd_initdb(args):
    init_db()
    print("Veritabanı başlatıldı.")


def cmd_addadmin(args):
    if len(args) < 2:
        print("Kullanım: addadmin <username> <sifre>"); return
    username, password = args[0], args[1]
    conn = get_db()
    try:
        cur = conn.execute('INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)',
                            (username, generate_password_hash(password), now()))
        conn.commit()
        print(f"Admin eklendi: #{cur.lastrowid} {username}")
    except Exception as e:
        print(f"Hata: {e}")
    finally:
        conn.close()


def cmd_passwd(args):
    if len(args) < 2:
        print("Kullanım: passwd <username> <yeni_sifre>"); return
    conn = get_db()
    cur = conn.execute('UPDATE admin_users SET password_hash = ? WHERE username = ?',
                        (generate_password_hash(args[1]), args[0]))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        print(f"Admin bulunamadı: {args[0]}")
    else:
        print(f"Şifre güncellendi: {args[0]}")


def cmd_listadmins(args):
    conn = get_db()
    for r in conn.execute('SELECT id, username FROM admin_users ORDER BY id'):
        print(f"#{r['id']:3d}  {r['username']}")
    conn.close()


COMMANDS = {
    'initdb': cmd_initdb,
    'addadmin': cmd_addadmin,
    'passwd': cmd_passwd,
    'listadmins': cmd_listadmins,
}

if __name__ == '__main__':
    init_db()
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
