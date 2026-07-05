"""Kullanıcı yönetimi için komut satırı aracı.

Kullanım:
    python manage.py adduser <kullanici_adi> <sifre> "<Görünen Ad>" [telegram_chat_id]
    python manage.py listusers
    python manage.py passwd <kullanici_adi> <yeni_sifre>
"""
import sys
from werkzeug.security import generate_password_hash
from db import get_db, init_db, now


def adduser(args):
    if len(args) < 3:
        print("Kullanım: python manage.py adduser <kullanici_adi> <sifre> \"<Görünen Ad>\" [telegram_chat_id]")
        sys.exit(1)
    username, password, display_name = args[0], args[1], args[2]
    telegram_chat_id = args[3] if len(args) > 3 else None
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO users (username, password_hash, display_name, telegram_chat_id, created_at) '
            'VALUES (?, ?, ?, ?, ?)',
            (username, generate_password_hash(password), display_name, telegram_chat_id, now())
        )
        conn.commit()
        print(f"Kullanıcı eklendi: {username} ({display_name})")
    except Exception as e:
        print(f"Hata: {e}")
        sys.exit(1)
    finally:
        conn.close()


def passwd(args):
    if len(args) < 2:
        print("Kullanım: python manage.py passwd <kullanici_adi> <yeni_sifre>")
        sys.exit(1)
    username, password = args[0], args[1]
    conn = get_db()
    cur = conn.execute(
        'UPDATE users SET password_hash = ? WHERE username = ?',
        (generate_password_hash(password), username)
    )
    conn.commit()
    if cur.rowcount == 0:
        print(f"Kullanıcı bulunamadı: {username}")
        sys.exit(1)
    print(f"Şifre güncellendi: {username}")
    conn.close()


def listusers(args):
    conn = get_db()
    rows = conn.execute('SELECT id, username, display_name, telegram_chat_id FROM users').fetchall()
    for r in rows:
        print(f"#{r['id']}  {r['username']:15s}  {r['display_name']:20s}  telegram_chat_id={r['telegram_chat_id']}")
    conn.close()


COMMANDS = {'adduser': adduser, 'passwd': passwd, 'listusers': listusers}

if __name__ == '__main__':
    init_db()
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
