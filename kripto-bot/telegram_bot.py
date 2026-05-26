import json, threading, time, datetime, urllib.request, urllib.parse
from bot import (load_config, save_config, get_client, get_price,
                 load_positions, load_trades, send_telegram)

OFFSET_FILE = 'tg_offset.json'

def load_offset():
    try:
        with open(OFFSET_FILE) as f:
            return json.load(f).get('offset', 0)
    except:
        return 0

def save_offset(offset):
    with open(OFFSET_FILE, 'w') as f:
        json.dump({'offset': offset}, f)

def tg_request(method, params=None):
    cfg = load_config()
    token = cfg.get('telegram_token', '')
    if not token:
        return None
    url = f'https://api.telegram.org/bot{token}/{method}'
    try:
        if params:
            data = urllib.parse.urlencode(params).encode()
            req = urllib.request.Request(url, data=data)
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f'[TG] Hata: {e}')
        return None

def get_updates(offset):
    result = tg_request('getUpdates', {'offset': offset, 'timeout': 30, 'limit': 10})
    if result and result.get('ok'):
        return result.get('result', [])
    return []

def send_reply(chat_id, msg):
    tg_request('sendMessage', {
        'chat_id': chat_id,
        'text': msg,
        'parse_mode': 'HTML'
    })

def handle_command(cmd, chat_id):
    cfg = load_config()
    allowed_chat = str(cfg.get('telegram_chat_id', ''))

    if str(chat_id) != allowed_chat:
        send_reply(chat_id, '⛔ Yetkisiz erişim')
        return

    cmd = cmd.strip().lower()

    if cmd == '/durum':
        try:
            client = get_client()
            positions = load_positions()
            trades = load_trades()
            closed = [t for t in trades if t.get('type') == 'sell']
            wins = [t for t in closed if t.get('pnl', 0) > 0]
            success = round(len(wins)/len(closed)*100, 1) if closed else 0

            pos_lines = ''
            total_pnl = 0
            for sym, pos in positions.items():
                if pos.get('qty', 0) <= 0:
                    continue
                price = get_price(client, sym)
                val = pos['qty'] * price
                if val < 1:
                    continue
                pnl = (price - pos['avg_price']) * pos['qty']
                total_pnl += pnl
                pos_lines += f'\n  {sym}: ${round(val,2)} ({"+"+str(round(pnl,2)) if pnl>=0 else str(round(pnl,2))}$)'

            coins = cfg.get('coins', [])
            active = sum(1 for c in coins if c.get('active'))

            msg = f'''📊 <b>Bot Durumu</b>
🟢 Çalışıyor
💰 Açık Pozisyonlar:{pos_lines if pos_lines else " Yok"}
📈 Toplam K/Z: {"+"+str(round(total_pnl,2)) if total_pnl>=0 else str(round(total_pnl,2))}$
🎯 Başarı: %{success} ({len(wins)}/{len(closed)})
🔧 Aktif Coin: {active}/{len(coins)}
⏰ {datetime.datetime.now().strftime("%H:%M:%S")}'''
            send_reply(chat_id, msg)

        except Exception as e:
            send_reply(chat_id, f'❌ Hata: {e}')

    elif cmd == '/durdur':
        cfg['bot_paused'] = True
        save_config(cfg)
        send_reply(chat_id, '⏸ Bot duraklatıldı — sinyaller işlenmeyecek')

    elif cmd == '/baslat':
        cfg['bot_paused'] = False
        save_config(cfg)
        send_reply(chat_id, '▶️ Bot başlatıldı')

    elif cmd == '/restart':
        send_reply(chat_id, '🔄 Bot yeniden başlatılıyor...')
        import subprocess
        subprocess.Popen(['systemctl', 'restart', 'kripto-bot'])

    elif cmd == '/pozisyonlar':
        try:
            client = get_client()
            positions = load_positions()
            if not positions:
                send_reply(chat_id, '📭 Açık pozisyon yok')
                return
            lines = []
            for sym, pos in positions.items():
                if pos.get('qty', 0) <= 0:
                    continue
                price = get_price(client, sym)
                val = pos['qty'] * price
                if val < 1:
                    continue
                pnl = (price - pos['avg_price']) * pos['qty']
                pnl_pct = (price - pos['avg_price']) / pos['avg_price'] * 100
                lines.append(f'<b>{sym}</b>: ${round(val,2)} | {"+"+str(round(pnl_pct,1)) if pnl_pct>=0 else str(round(pnl_pct,1))}%')
            send_reply(chat_id, '📈 <b>Açık Pozisyonlar</b>\n' + '\n'.join(lines) if lines else '📭 Pozisyon yok')
        except Exception as e:
            send_reply(chat_id, f'❌ {e}')

    elif cmd in ['/start', '/yardim']:
        send_reply(chat_id, '''🤖 <b>Kripto Bot Komutları</b>

/durum — Genel durum özeti
/pozisyonlar — Açık pozisyonlar
/baslat — Botu başlat
/durdur — Botu duraklat
/restart — Botu yeniden başlat
/yardim — Bu mesaj''')
    else:
        send_reply(chat_id, f'❓ Bilinmeyen komut: {cmd}\n/yardim yazarak komutları görebilirsin')

def run_telegram_bot():
    print('[TG Bot] Başladı')
    offset = load_offset()
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update['update_id'] + 1
                save_offset(offset)
                msg = update.get('message', {})
                text = msg.get('text', '')
                chat_id = msg.get('chat', {}).get('id')
                if text and text.startswith('/') and chat_id:
                    print(f'[TG Bot] Komut: {text} from {chat_id}')
                    handle_command(text, chat_id)
        except Exception as e:
            print(f'[TG Bot] Genel hata: {e}')
            time.sleep(5)

def start_telegram_bot():
    t = threading.Thread(target=run_telegram_bot, daemon=True)
    t.start()
    return t
