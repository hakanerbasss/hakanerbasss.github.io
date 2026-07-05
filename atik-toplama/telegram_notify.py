"""Telegram bildirim modülü — metin, fotoğraf, konum, ses."""
import json
import os
import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
_cfg_cache = None


def _cfg():
    global _cfg_cache
    if _cfg_cache is None:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                _cfg_cache = json.load(f)
        else:
            _cfg_cache = {}
    return _cfg_cache


def _token():
    return _cfg().get('telegram_bot_token') or os.environ.get('TELEGRAM_BOT_TOKEN', '')


def _default_chat(neighborhood_id=None):
    """Mahalleye özel chat id varsa onu, yoksa genel grubu döner."""
    cfg = _cfg()
    if neighborhood_id:
        nb_chats = cfg.get('neighborhood_telegram_chats', {})
        cid = nb_chats.get(str(neighborhood_id))
        if cid:
            return cid
    return cfg.get('telegram_chat_id') or os.environ.get('TELEGRAM_CHAT_ID', '')


def _post(endpoint, data=None, files=None, neighborhood_id=None):
    token = _token()
    chat_id = _default_chat(neighborhood_id)
    if not token or not chat_id:
        return False
    if data is None:
        data = {}
    data['chat_id'] = chat_id
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{token}/{endpoint}',
            data=data,
            files=files,
            timeout=30,
        )
        return r.ok
    except requests.RequestException:
        return False


def send_message(text, neighborhood_id=None, chat_id=None):
    token = _token()
    cid = chat_id or _default_chat(neighborhood_id)
    if not token or not cid:
        return False
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data={'chat_id': cid, 'text': text, 'parse_mode': 'HTML'},
            timeout=15,
        )
        return r.ok
    except requests.RequestException:
        return False


def send_location(lat, lon, neighborhood_id=None):
    return _post('sendLocation', {'latitude': lat, 'longitude': lon}, neighborhood_id=neighborhood_id)


def send_photo(photo_file, caption='', neighborhood_id=None):
    """photo_file: file-like object (Flask request.files)."""
    return _post(
        'sendPhoto',
        data={'caption': caption},
        files={'photo': ('photo.jpg', photo_file, 'image/jpeg')},
        neighborhood_id=neighborhood_id,
    )


def send_voice(voice_file, caption='', neighborhood_id=None):
    """voice_file: file-like object."""
    return _post(
        'sendVoice',
        data={'caption': caption},
        files={'voice': ('voice.ogg', voice_file, 'audio/ogg')},
        neighborhood_id=neighborhood_id,
    )


# ── Yüksek seviye bildirimler ────────────────────────────────────────────────

def notify_street_complete(street_name, user_display, neighborhood_name, shift_name,
                           photo_file=None, neighborhood_id=None):
    import datetime
    saat = datetime.datetime.now().strftime('%H:%M')
    caption = (
        f"🧹 <b>{street_name}</b> süpürüldü\n"
        f"👤 {user_display}\n"
        f"🏘 {neighborhood_name}\n"
        f"🕐 {saat}  |  {shift_name}"
    )
    if photo_file:
        return send_photo(photo_file, caption=caption, neighborhood_id=neighborhood_id)
    return send_message(caption, neighborhood_id=neighborhood_id)


def notify_new_notification(notif, user_display, neighborhood_name, neighborhood_id=None):
    from db import NOTIFICATION_TYPES
    icon, label, _ = NOTIFICATION_TYPES.get(notif['type'], ('📝', notif['type'], None))
    import datetime
    saat = datetime.datetime.now().strftime('%H:%M')
    text = (
        f"{icon} <b>Olumsuzluk Bildirimi</b>\n"
        f"🏘 {neighborhood_name}\n"
        f"📋 {label}\n"
    )
    if notif.get('note'):
        text += f"💬 {notif['note']}\n"
    text += f"👤 {user_display}  |  🕐 {saat}\n"
    text += f"📍 https://maps.google.com/?q={notif['lat']},{notif['lon']}"
    ok = send_message(text, neighborhood_id=neighborhood_id)
    if ok:
        send_location(notif['lat'], notif['lon'], neighborhood_id=neighborhood_id)
    return ok


def notify_resolved(notif, user_display, neighborhood_name, photo_file=None, neighborhood_id=None):
    from db import NOTIFICATION_TYPES
    icon, label, _ = NOTIFICATION_TYPES.get(notif['type'], ('📝', notif['type'], None))
    import datetime
    saat = datetime.datetime.now().strftime('%H:%M')
    caption = (
        f"✅ <b>Giderildi: {label}</b>\n"
        f"🏘 {neighborhood_name}\n"
        f"👤 {user_display}  |  🕐 {saat}"
    )
    if photo_file:
        return send_photo(photo_file, caption=caption, neighborhood_id=neighborhood_id)
    return send_message(caption, neighborhood_id=neighborhood_id)
