import json, threading, time, datetime, urllib.request, urllib.parse
from bot import (load_config, save_config, get_client, get_price,
                 load_positions, load_trades, send_telegram, get_usdt_balance)

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

    elif cmd == '/ajanlar':
        try:
            from autonomous_agent import agent_status
            from edge_agent import edge_agent_status
            from indicator_agent import indicator_agent_status
            from signal_engine import get_klines

            client = get_client()

            # BTC trend kontrolü
            try:
                closes, _, _, _ = get_klines(client, 'BTCUSDT', '1h', limit=25)
                btc_ok = closes[-1] > sum(closes[-20:]) / 20
                btc_icon = '🟢' if btc_ok else '🔴'
                btc_pct = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
                btc_line = f'{btc_icon} BTC: {"+" if btc_pct>=0 else ""}{btc_pct}% (SMA20 {"↑ üstünde" if btc_ok else "↓ altında"})'
            except Exception:
                btc_line = '⚪ BTC: veri alınamadı'

            # Bakiye
            try:
                bal = get_usdt_balance(client)
                bal_line = f'💰 Bakiye: ${bal:.2f}'
            except Exception:
                bal_line = '💰 Bakiye: alınamadı'

            # Otonom
            ot = agent_status()
            if ot.get('running'):
                regime = ot.get('last_regime', '?')
                r_icon = {'BULL': '🟢', 'SIDEWAYS': '🟡', 'BEAR': '🔴'}.get(regime, '⚪')
                otonom_line = f'🤖 Otonom: {r_icon} {regime} | Tarama: {ot.get("scan_count",0)}x'
            else:
                otonom_line = '🤖 Otonom: ⛔ Çalışmıyor'

            # Edge
            et = edge_agent_status()
            if et.get('running'):
                edge_line = f'⚡ Edge: 🟢 Aktif | Tarama: {et.get("scan_count",0)}x'
            else:
                edge_line = '⚡ Edge: ⛔ Çalışmıyor'

            # Indicator
            it = indicator_agent_status()
            if it.get('running'):
                btc_f = '🟢' if it.get('btc_ok', btc_ok) else '🔴'
                ind_line = f'📐 Indicator: 🟢 Aktif | BTC filtre: {btc_f} | Tarama: {it.get("scan_count",0)}x'
            else:
                ind_line = '📐 Indicator: ⛔ Çalışmıyor'

            # Açık pozisyonlar
            positions = load_positions()
            open_pos = [(s, p) for s, p in positions.items() if p.get('qty', 0) > 0]
            pos_line = f'📦 Açık pozisyon: {len(open_pos)}'

            # Alım koşulu özeti
            if ot.get('running') and ot.get('last_regime') == 'BEAR':
                neden = '⚠️ Alım yok: Otonom BEAR modda'
            elif not btc_ok:
                neden = '⚠️ Alım yok: BTC düşüşte (Indicator filtresi)'
            else:
                neden = '✅ Alım koşulları uygun'

            send_reply(chat_id,
                f'🔍 <b>Ajan Durumu</b>\n'
                f'━━━━━━━━━━━━━━\n'
                f'{bal_line}\n'
                f'{btc_line}\n'
                f'━━━━━━━━━━━━━━\n'
                f'{otonom_line}\n'
                f'{edge_line}\n'
                f'{ind_line}\n'
                f'━━━━━━━━━━━━━━\n'
                f'{pos_line}\n'
                f'{neden}\n'
                f'⏰ {datetime.datetime.now().strftime("%H:%M:%S")}'
            )
        except Exception as e:
            send_reply(chat_id, f'❌ Hata: {e}')

    elif cmd in ['/ceo ac', '/ceo_ac', '/ceoon']:
        cfg['ceo_agent_enabled'] = True
        api_key = cfg.get('deepseek_api_key', '')
        if not api_key:
            send_reply(chat_id, '⚠️ Önce DeepSeek API key gerekli!\nconfig.json\'a deepseek_api_key ekle.')
        else:
            save_config(cfg)
            from manager_agent import start_ceo_agent, _running as ceo_running
            if not ceo_running:
                start_ceo_agent()
            send_reply(chat_id, '👔 CEO Agent açıldı. İlk analiz başlıyor...')

    elif cmd in ['/ceo kapat', '/ceo_kapat', '/ceooff']:
        cfg['ceo_agent_enabled'] = False
        save_config(cfg)
        from manager_agent import stop_ceo_agent
        stop_ceo_agent()
        send_reply(chat_id, '👔 CEO Agent kapatıldı.')

    elif cmd.startswith('/ceo_ayar') or cmd.startswith('/ceo ayar'):
        parts = cmd.split()
        valid = {'1h': 1, '2h': 2, '4h': 4, '6h': 6, '12h': 12}
        val   = parts[-1] if parts else ''
        if val not in valid:
            send_reply(chat_id, f'Kullanım: /ceo_ayar 1h|2h|4h|6h|12h\nŞu an: {cfg.get("ceo_interval_hours", 1)}h')
        else:
            cfg['ceo_interval_hours'] = valid[val]
            save_config(cfg)
            send_reply(chat_id, f'✅ CEO analiz aralığı: her {val}')

    elif cmd in ['/ceo analiz', '/ceo_analiz', '/ceoanaliz']:
        from manager_agent import trigger_ceo_review, ceo_agent_status
        st = ceo_agent_status()
        if not st.get('enabled'):
            send_reply(chat_id, '⚠️ CEO kapalı. /ceo ac ile aç.')
        else:
            send_reply(chat_id, '👔 Manuel analiz başlatıldı...')
            trigger_ceo_review()

    elif cmd == '/ceo':
        from manager_agent import ceo_agent_status
        st = ceo_agent_status()
        icon = '🟢' if st.get('running') else '🔴'
        send_reply(chat_id,
            f'👔 <b>CEO Agent</b>\n'
            f'{icon} Durum: {"Aktif" if st.get("running") else "Kapalı"}\n'
            f'🔍 Analiz sayısı: {st.get("review_count", 0)}\n'
            f'⏱ Son analiz: {st.get("last_review", "Henüz yok")}\n'
            f'⏰ Aralık: her {st.get("interval_hours", 6)} saat\n\n'
            f'Komutlar:\n'
            f'/ceo ac — başlat\n'
            f'/ceo kapat — durdur\n'
            f'/ceo analiz — hemen analiz et'
        )

    elif cmd == '/rapor':
        try:
            from autonomous_agent import trigger_otonom_report
            from edge_agent import trigger_edge_report
            from indicator_agent import trigger_indicator_report
            from wyckoff_agent import trigger_wyckoff_report
            send_reply(chat_id, '📋 Raporlar hazırlanıyor...')
            for fn in [trigger_otonom_report, trigger_edge_report,
                       trigger_indicator_report, trigger_wyckoff_report]:
                try:
                    fn()
                except Exception:
                    pass
        except Exception as e:
            send_reply(chat_id, f'❌ {e}')

    elif cmd.startswith('/rapor_ayar'):
        parts = cmd.split()
        valid = {'1h': 1, '4h': 4, '12h': 12, '1d': 24}
        if len(parts) < 2 or parts[1] not in valid:
            send_reply(chat_id,
                f'Kullanım: /rapor_ayar 1h|4h|12h|1d\n'
                f'Şu an: {cfg.get("report_interval_hours", 1)}h')
        else:
            hours = valid[parts[1]]
            cfg['report_interval_hours'] = hours
            save_config(cfg)
            send_reply(chat_id, f'✅ Rapor aralığı: her {parts[1]} — bir sonraki raporda geçerli')

    elif cmd in ('/edgeon', '/edgeoff', '/otonomон', '/otonomoff',
                 '/indicatoron', '/indicatoroff', '/wyckoffon', '/wyckoffoff',
                 '/otonomon'):
        TOGGLE = {
            '/edgeon':       ('edge_enabled',      True),
            '/edgeoff':      ('edge_enabled',      False),
            '/otonomon':     ('otonom_enabled',    True),
            '/otonomoff':    ('otonom_enabled',    False),
            '/indicatoron':  ('indicator_enabled', True),
            '/indicatoroff': ('indicator_enabled', False),
            '/wyckoffon':    ('wyckoff_enabled',   True),
            '/wyckoffoff':   ('wyckoff_enabled',   False),
        }
        key, enabled = TOGGLE[cmd]
        name = key.replace('_enabled', '')
        cfg  = load_config()
        cfg[key] = enabled
        save_config(cfg)
        icon = '🟢' if enabled else '🔴'
        send_reply(chat_id, f'{icon} <b>{name}</b> ajanı {"açıldı" if enabled else "kapatıldı"}')

    elif cmd in ['/start', '/yardim']:
        send_reply(chat_id, '''🤖 <b>Kripto Bot Komutları</b>

/durum — Genel durum özeti
/pozisyonlar — Açık pozisyonlar
/ajanlar — Ajan durumları
/edgeon /edgeoff /otonomon /otonomoff /indicatoron /indicatoroff /wyckoffon /wyckoffoff
/rapor — Tüm ajanlardan anında rapor
/rapor_ayar 1h|4h|12h|1d — Rapor sıklığı
/ceo — CEO Agent durumu
/ceo ac | /ceo kapat | /ceo analiz
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
