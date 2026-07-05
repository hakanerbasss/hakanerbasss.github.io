import json
import os
import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _bot_token():
    return load_config().get('telegram_bot_token') or os.environ.get('TELEGRAM_BOT_TOKEN')


def _default_chat_id():
    return load_config().get('telegram_chat_id') or os.environ.get('TELEGRAM_CHAT_ID')


def send_message(text, chat_id=None):
    token = _bot_token()
    chat_id = chat_id or _default_chat_id()
    if not token or not chat_id:
        return False
    try:
        requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data={'chat_id': chat_id, 'text': text},
            timeout=10,
        )
        return True
    except requests.RequestException:
        return False


def send_location(lat, lon, chat_id=None):
    token = _bot_token()
    chat_id = chat_id or _default_chat_id()
    if not token or not chat_id:
        return False
    try:
        requests.post(
            f'https://api.telegram.org/bot{token}/sendLocation',
            data={'chat_id': chat_id, 'latitude': lat, 'longitude': lon},
            timeout=10,
        )
        return True
    except requests.RequestException:
        return False


def notify_point(point, neighborhood_name, chat_id=None):
    """Yeni eklenen bir nokta/not için metin + konum bildirimi gönderir."""
    from db import POINT_TYPES
    label = POINT_TYPES.get(point['type'], point['type'])
    lines = [
        f"📍 {neighborhood_name}",
        label,
    ]
    if point.get('note'):
        lines.append(f"Not: {point['note']}")
    if point.get('created_by'):
        lines.append(f"Ekleyen: {point['created_by']}")
    lines.append(f"https://www.google.com/maps?q={point['lat']},{point['lon']}")
    ok = send_message('\n'.join(lines), chat_id=chat_id)
    if ok:
        send_location(point['lat'], point['lon'], chat_id=chat_id)
    return ok
