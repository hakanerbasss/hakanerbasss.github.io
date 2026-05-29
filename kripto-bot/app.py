from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
import json, os, hashlib, datetime
from bot import (load_config, save_config, get_client, get_market_summary,
                 get_fear_greed, get_portfolio_summary, execute_buy, execute_sell,
                 load_trades, load_positions, get_usdt_balance, get_price)
from signal_engine import start_engine
from telegram_bot import start_telegram_bot
from autonomous_agent import (start_autonomous_agent, stop_autonomous_agent,
                               agent_status)
from edge_agent import start_edge_agent, stop_edge_agent, edge_agent_status
from indicator_agent import (start_indicator_agent, stop_indicator_agent,
                              indicator_agent_status)
from wyckoff_agent import (start_wyckoff_agent, stop_wyckoff_agent,
                            wyckoff_agent_status)
from breakout_agent import (start_breakout_agent, stop_breakout_agent,
                             breakout_agent_status)
from manager_agent import (start_ceo_agent, stop_ceo_agent, ceo_agent_status,
                            trigger_ceo_review, restart_ceo_agent)

app = Flask(__name__)  # deploy test
app.secret_key = 'kripto-bot-secret-2024'
app.permanent_session_lifetime = datetime.timedelta(days=30)

ADMIN_USER = 'admin'
ADMIN_PASS_HASH = hashlib.sha256('admin123'.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── Auth ─────────────────────────────────────────
@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        u = request.form.get('username')
        p = hashlib.sha256(request.form.get('password','').encode()).hexdigest()
        if u == ADMIN_USER and p == ADMIN_PASS_HASH:
            session.permanent = True
            session['logged_in'] = True
            return redirect(url_for('index'))
        error = 'Kullanıcı adı veya şifre hatalı'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── Ana Sayfa ────────────────────────────────────
@app.route('/')
@login_required
def index():
    cfg = load_config()
    return render_template('index.html', cfg=cfg)

# ── API: Dashboard ───────────────────────────────
@app.route('/api/dashboard')
@login_required
def api_dashboard():
    try:
        client       = get_client()
        market       = get_market_summary(client)
        fg           = get_fear_greed()
        portfolio    = get_portfolio_summary(client)
        usdt_balance = get_usdt_balance(client)

        # Açık pozisyonların anlık değeri
        positions  = load_positions()
        pos_value  = 0.0
        for sym, pos in positions.items():
            if pos.get('qty', 0) > 0:
                try:
                    pos_value += get_price(client, sym) * pos['qty']
                except Exception:
                    pass
        pos_value   = round(pos_value, 2)
        total_value = round(usdt_balance + pos_value, 2)

        return jsonify({
            'ok': True, 'market': market, 'fear_greed': fg,
            'portfolio': portfolio, 'usdt_balance': usdt_balance,
            'pos_value': pos_value, 'total_value': total_value,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── API: Trades ──────────────────────────────────
@app.route('/api/trades')
@login_required
def api_trades():
    trades = load_trades()
    limit = request.args.get('limit', 50, type=int)
    return jsonify(list(reversed(trades[-limit:])))

@app.route('/api/trades/telegram', methods=['POST'])
@login_required
def api_trades_telegram():
    """Son N işlemi Telegram'a gönder (varsayılan 30)."""
    n = request.json.get('n', 30) if request.is_json else 30
    trades = load_trades()
    recent = list(reversed(trades[-n:]))

    sells  = [t for t in recent if t.get('type') == 'sell']
    buys   = [t for t in recent if t.get('type') == 'buy']
    pnl_sum = sum(float(t.get('pnl_usdt', t.get('pnl', 0)) or 0) for t in sells)
    wins    = sum(1 for t in sells if float(t.get('pnl_usdt', t.get('pnl', 0)) or 0) > 0)
    losses  = len(sells) - wins

    lines = [
        f'📊 <b>Son {len(recent)} İşlem</b>',
        f'💰 Net PNL: <b>{"+" if pnl_sum >= 0 else ""}${pnl_sum:.2f}</b>',
        f'✅ Kazanan: {wins} | ❌ Kaybeden: {losses} | 🛒 Alış: {len(buys)}',
        '━━━━━━━━━━━━━━━━━━',
    ]
    for t in recent:
        tp   = t.get('type', '')
        sym  = t.get('symbol', '?')
        src  = t.get('source', '?')
        time = (t.get('time', ''))[5:]   # MM-DD HH:MM kısat
        pnl  = float(t.get('pnl_usdt', t.get('pnl', 0)) or 0)
        qty  = t.get('qty', 0)
        price = t.get('price', 0)
        if tp == 'buy':
            lines.append(f'🛒 {time} | <b>{sym}</b> [{src}] ${float(qty)*float(price):.1f}')
        else:
            sign = '+' if pnl >= 0 else ''
            col  = '' if pnl >= 0 else ''
            lines.append(f'{"🟢" if pnl>=0 else "🔴"} {time} | <b>{sym}</b> [{src}] <b>{sign}${pnl:.2f}</b>')

    from bot import send_telegram
    send_telegram('\n'.join(lines))
    return jsonify({'ok': True, 'sent': len(recent)})

@app.route('/trades/reset', methods=['POST'])
@login_required
def trades_reset():
    from bot import save_trades
    save_trades([])
    return jsonify({'ok': True})

@app.route('/positions/clear', methods=['POST'])
@login_required
def positions_clear():
    """Positions.json'ı doğrudan sıfırla — elle silinen pozisyonlar için."""
    from bot import save_positions
    save_positions({})
    return jsonify({'ok': True, 'msg': 'Tüm pozisyonlar temizlendi'})

# ── API: Smart Backtest ──────────────────────────
@app.route('/api/smart_backtest')
@login_required
def smart_backtest():
    try:
        symbol = request.args.get('symbol', '').upper()
        if not symbol:
            return jsonify({'ok': False, 'error': 'Sembol gerekli'})

        client = get_client()
        from binance.client import Client as BClient
        klines = client.get_klines(
            symbol=symbol,
            interval=BClient.KLINE_INTERVAL_1HOUR,
            limit=180 * 24
        )

        opens   = [float(k[1]) for k in klines]
        highs   = [float(k[2]) for k in klines]
        lows    = [float(k[3]) for k in klines]
        closes  = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]

        def calc_rsi(cls, period=14):
            if len(cls) < period + 1:
                return None
            deltas = [cls[i] - cls[i-1] for i in range(1, len(cls))]
            g = [max(d, 0) for d in deltas[-period:]]
            l = [max(-d, 0) for d in deltas[-period:]]
            ag, al = sum(g)/period, sum(l)/period
            return round(100 - 100/(1 + ag/al), 1) if al > 0 else 100.0

        def vol_ratio(vols, i, lb=20):
            if i < lb: return 0
            avg = sum(vols[i-lb:i]) / lb
            return vols[i] / avg if avg > 0 else 0

        def candle_pattern(i):
            """Yükseliş dönüş formasyonu — son 3 mum"""
            if i < 2:
                return 0
            from smart_strategy import detect_bullish_pattern
            candles = [
                {'o': opens[i-2], 'h': highs[i-2], 'l': lows[i-2], 'c': closes[i-2]},
                {'o': opens[i-1], 'h': highs[i-1], 'l': lows[i-1], 'c': closes[i-1]},
                {'o': opens[i],   'h': highs[i],   'l': lows[i],   'c': closes[i]},
            ]
            score, _ = detect_bullish_pattern(candles)
            return score

        EXIT_HOURS = [4, 8, 24, 48]
        WARMUP     = 20

        # 3 backtestlenebilir faktör: RSI + Volume + Formasyon
        def run(min_score, exit_h, rsi_exit=True):
            wins = total = 0
            net  = 0.0
            i    = WARMUP
            while i < len(closes) - exit_h:
                rsi = calc_rsi(closes[:i+1])
                vr  = vol_ratio(volumes, i)
                pat = candle_pattern(i)
                if rsi is None:
                    i += 1; continue

                rsi_s = 1 if 30 <= rsi <= 65 else 0
                vol_s = 1 if vr > 1.5 else 0
                score = rsi_s + vol_s + pat

                if score < min_score:
                    i += 1; continue

                buy_price = closes[i]
                exit_i    = i + exit_h

                if rsi_exit:
                    for j in range(i+1, min(i+exit_h+1, len(closes))):
                        r = calc_rsi(closes[:j+1])
                        if r is not None and r > 72:
                            exit_i = j; break

                exit_i     = min(exit_i, len(closes)-1)
                sell_price = closes[exit_i]
                pnl = (sell_price - buy_price) / buy_price * 100 - 0.2
                net += pnl; total += 1
                if pnl > 0: wins += 1
                i = exit_i + 1

            return {
                'trades': total,
                'wr':  round(wins/total*100, 1) if total else 0,
                'net': round(net, 2),
                'avg': round(net/total, 2) if total else 0,
            }

        LABELS = {
            0: 'Filtresiz',
            1: 'Herhangi 1 faktör',
            2: 'Herhangi 2 faktör',
            3: 'RSI + Volume + Formasyon',
        }
        results = {}
        for ms in [0, 1, 2, 3]:
            label = LABELS[ms]
            results[label] = {}
            for eh in EXIT_HOURS:
                results[label][f'{eh}s'] = run(ms, eh)
            results[label]['RSI Çıkış'] = run(ms, 48, rsi_exit=True)

        return jsonify({'ok': True, 'symbol': symbol, 'results': results,
                        'note': 'Backtest: Formasyon + RSI + Volume (3 faktör). Funding Rate canlıda ek filtre.'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── API: Stats (indikatör bazlı) ─────────────────
@app.route('/api/stats')
@login_required
def api_stats():
    trades = load_trades()
    trades_sorted = sorted(trades, key=lambda t: t.get('time', ''))

    def _normalize(source):
        s = (source or '').upper()
        if 'INDICATOR-UTBOT' in s:  return 'INDICATOR-UTBOT'
        if 'INDICATOR-SMART' in s:  return 'INDICATOR-SMART'
        if 'INDICATOR-SEANS' in s:  return 'INDICATOR-SEANS'
        if 'INDICATOR' in s:        return 'INDICATOR-UTBOT'  # eski kayıtlar UTBOT'a düşsün
        if 'BREAKOUT' in s:         return 'BREAKOUT'
        if 'WYCKOFF' in s:          return 'WYCKOFF'
        if 'EDGE' in s:             return 'EDGE'
        if 'OTONOM' in s:           return 'OTONOM'
        if 'UT' in s:               return 'UT BOT'
        if 'SEANS' in s:            return 'SEANS'
        if 'SMART' in s:            return 'SMART'
        if 'MANUEL' in s:           return 'MANUEL'
        return 'DİĞER'

    last_buy_source = {}  # symbol → normalized indicator
    by_ind = {}           # indicator → {wins, total, pnl}

    for t in trades_sorted:
        symbol = t.get('symbol', '')
        source = t.get('source', '')
        if t.get('type') == 'buy':
            last_buy_source[symbol] = _normalize(source)
        elif t.get('type') == 'sell':
            key = last_buy_source.get(symbol, _normalize(source))
            if key not in by_ind:
                by_ind[key] = {'wins': 0, 'total': 0, 'pnl': 0.0}
            pnl = t.get('pnl', 0) or 0
            by_ind[key]['total'] += 1
            by_ind[key]['pnl']   = round(by_ind[key]['pnl'] + pnl, 2)
            if pnl > 0:
                by_ind[key]['wins'] += 1

    result = {
        k: {
            'trades': v['total'],
            'wins':   v['wins'],
            'wr':     round(v['wins'] / v['total'] * 100, 1) if v['total'] else 0,
            'pnl':    v['pnl'],
            'avg':    round(v['pnl'] / v['total'], 2) if v['total'] else 0,
        }
        for k, v in by_ind.items()
    }
    return jsonify({'ok': True, 'by_indicator': result})

# ── Ayarlar ──────────────────────────────────────
@app.route('/settings', methods=['POST'])
@login_required
def settings():
    cfg = load_config()
    cfg['api_key']              = request.form.get('api_key', '')
    cfg['api_secret']           = request.form.get('api_secret', '')
    cfg['real_api_key']         = request.form.get('real_api_key', '')
    cfg['real_api_secret']      = request.form.get('real_api_secret', '')
    cfg['testnet']              = request.form.get('testnet') == 'on'
    cfg['webhook_secret']       = request.form.get('webhook_secret', 'secret123')
    cfg['check_interval']       = int(request.form.get('check_interval', 45))
    cfg['telegram_token']       = request.form.get('telegram_token', '')
    cfg['telegram_chat_id']     = request.form.get('telegram_chat_id', '')
    cfg['max_positions']        = int(request.form.get('max_positions', 6))
    if request.form.get('deepseek_api_key', '').strip():
        cfg['deepseek_api_key'] = request.form.get('deepseek_api_key', '').strip()
    old_ceo_interval             = cfg.get('ceo_interval_hours', 1)
    cfg['ceo_interval_hours']    = int(request.form.get('ceo_interval_hours', 1))
    cfg['report_interval_hours'] = int(request.form.get('report_interval_hours', 1))
    save_config(cfg)
    if old_ceo_interval != cfg['ceo_interval_hours'] and ceo_agent_status()['running']:
        restart_ceo_agent()
    return jsonify({'ok': True})

# ── Coin Yönetimi ────────────────────────────────
@app.route('/coin/add', methods=['POST'])
@login_required
def coin_add():
    cfg = load_config()
    coins = cfg.get('coins', [])
    data = request.get_json()
    symbol = data.get('symbol', '').upper()
    if not symbol:
        return jsonify({'ok': False, 'error': 'Sembol boş'})
    if any(c['symbol'] == symbol for c in coins):
        return jsonify({'ok': False, 'error': 'Zaten ekli'})
    coins.append({
        'symbol':              symbol,
        'usdt_amount':         float(data.get('usdt_amount', 10)),
        'period':              data.get('period', '1h'),
        'signal_source':       data.get('signal_source', 'utbot'),
        # UT Bot
        'ut_key':              float(data.get('ut_key', 2)),
        'ut_atr':              int(data.get('ut_atr', 7)),
        'ut_mode':             data.get('ut_mode', 'crossover'),
        # Kapanış sinyali satış
        'close_sell_pct':      float(data.get('close_sell_pct', 100)),
        # Kâr hedefi
        'take_profit_pct':     float(data.get('take_profit_pct', 0)),
        'take_profit_sell_pct':float(data.get('take_profit_sell_pct', 100)),
        # Stop loss
        'stop_loss_pct':       float(data.get('stop_loss_pct', 0)),
        'stop_loss_sell_pct':  float(data.get('stop_loss_sell_pct', 100)),
        'seans_strategy':      data.get('seans_strategy', 'both'),
        'seans_buy_hour':      int(data.get('seans_buy_hour', 20)),
        'seans_sell_hour':     int(data.get('seans_sell_hour', 13)),
        'smart_min_score':     int(data.get('smart_min_score', 3)),
        'auto_tp_sl':          bool(data.get('auto_tp_sl', False)),
        'sl_cooldown_hours':   float(data.get('sl_cooldown_hours', 4)),
        'btc_filter':          bool(data.get('btc_filter', False)),
        'min_tp_pct':          float(data.get('min_tp_pct', 0)),
        'active': True,
    })
    cfg['coins'] = coins
    save_config(cfg)
    return jsonify({'ok': True})

@app.route('/coin/remove', methods=['POST'])
@login_required
def coin_remove():
    cfg = load_config()
    data = request.get_json()
    symbol = data.get('symbol', '').upper()
    cfg['coins'] = [c for c in cfg.get('coins', []) if c['symbol'] != symbol]
    save_config(cfg)
    return jsonify({'ok': True})

@app.route('/coin/update', methods=['POST'])
@login_required
def coin_update():
    cfg = load_config()
    data = request.get_json()
    symbol = data.get('symbol', '').upper()
    for c in cfg.get('coins', []):
        if c['symbol'] == symbol:
            c['usdt_amount']          = float(data.get('usdt_amount', c['usdt_amount']))
            c['period']               = data.get('period', c['period'])
            c['signal_source']        = data.get('signal_source', c.get('signal_source','utbot'))
            c['ut_key']               = float(data.get('ut_key', c.get('ut_key', 2)))
            c['ut_atr']               = int(data.get('ut_atr', c.get('ut_atr', 7)))
            c['ut_mode']              = data.get('ut_mode', c.get('ut_mode', 'crossover'))
            c['close_sell_pct']       = float(data.get('close_sell_pct', c.get('close_sell_pct', 100)))
            c['take_profit_pct']      = float(data.get('take_profit_pct', c.get('take_profit_pct', 0)))
            c['take_profit_sell_pct'] = float(data.get('take_profit_sell_pct', c.get('take_profit_sell_pct', 100)))
            c['stop_loss_pct']        = float(data.get('stop_loss_pct', c.get('stop_loss_pct', 0)))
            c['stop_loss_sell_pct']   = float(data.get('stop_loss_sell_pct', c.get('stop_loss_sell_pct', 100)))
            c['seans_strategy']       = data.get('seans_strategy', c.get('seans_strategy', 'both'))
            c['seans_buy_hour']       = int(data.get('seans_buy_hour', c.get('seans_buy_hour', 20)))
            c['seans_sell_hour']      = int(data.get('seans_sell_hour', c.get('seans_sell_hour', 13)))
            c['smart_min_score']      = int(data.get('smart_min_score', c.get('smart_min_score', 3)))
            c['auto_tp_sl']           = bool(data.get('auto_tp_sl', c.get('auto_tp_sl', False)))
            c['sl_cooldown_hours']    = float(data.get('sl_cooldown_hours', c.get('sl_cooldown_hours', 4)))
            c['btc_filter']           = bool(data.get('btc_filter', c.get('btc_filter', False)))
            c['min_tp_pct']           = float(data.get('min_tp_pct', c.get('min_tp_pct', 0)))
            c['active']               = data.get('active', c['active'])
            break
    save_config(cfg)
    return jsonify({'ok': True})

@app.route('/coin/toggle', methods=['POST'])
@login_required
def coin_toggle():
    cfg = load_config()
    data = request.get_json()
    symbol = data.get('symbol', '').upper()
    for c in cfg.get('coins', []):
        if c['symbol'] == symbol:
            c['active'] = not c.get('active', True)
            break
    save_config(cfg)
    return jsonify({'ok': True})

# ── Webhook ──────────────────────────────────────
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data:
        return jsonify({'ok': False, 'error': 'Veri yok'}), 400
    cfg = load_config()
    if data.get('secret') != cfg.get('webhook_secret', 'secret123'):
        return jsonify({'ok': False, 'error': 'Geçersiz secret'}), 403
    symbol = data.get('symbol', '').upper()
    action = data.get('action', '').lower()
    if not symbol or action not in ['buy', 'sell']:
        return jsonify({'ok': False, 'error': 'Geçersiz veri'}), 400

    coin = next((c for c in cfg.get('coins', []) if c['symbol'] == symbol and c['active']), None)
    if not coin:
        return jsonify({'ok': False, 'error': 'Coin listede yok veya pasif'}), 400

    # Sinyal kaynağı webhook veya both ise işle
    source = coin.get('signal_source', 'utbot')
    if source not in ['webhook', 'both']:
        return jsonify({'ok': False, 'error': f'Bu coin webhook sinyali kabul etmiyor (kaynak: {source})'}), 400

    try:
        client = get_client()
        if action == 'buy':
            result = execute_buy(client, symbol, coin['usdt_amount'])
        else:
            result = execute_sell(client, symbol, coin.get('close_sell_pct', 100))
        return jsonify(result)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── Manuel İşlem ─────────────────────────────────
@app.route('/manual/buy', methods=['POST'])
@login_required
def manual_buy():
    data = request.get_json()
    client = get_client()
    result = execute_buy(client, data.get('symbol','').upper(), float(data.get('usdt_amount', 10)))
    return jsonify(result)

@app.route('/manual/sell', methods=['POST'])
@login_required
def manual_sell():
    data = request.get_json()
    client = get_client()
    result = execute_sell(client, data.get('symbol','').upper(), float(data.get('sell_pct', 100)))
    return jsonify(result)

@app.route('/manual/closeall', methods=['POST'])
@login_required
def close_all():
    from bot import load_positions
    client = get_client()
    positions = load_positions()
    results = []
    for symbol, pos in positions.items():
        if pos.get('qty', 0) > 0:
            result = execute_sell(client, symbol, 100, source='MANUEL KAPAT')
            results.append({'symbol': symbol, 'result': result})
    return jsonify({'ok': True, 'results': results})

# ── Grafik Verisi ────────────────────────────────
@app.route('/api/chart')
@login_required
def api_chart():
    try:
        symbol = request.args.get('symbol', 'BTCUSDT')
        interval = request.args.get('interval', '5m')
        client = get_client()
        from signal_engine import get_klines, calc_ut_bot, calc_rma
        closes, highs, lows, last_candle_time = get_klines(client, symbol, interval, limit=100)

        from bot import load_config
        cfg = load_config()
        coin = next((c for c in cfg.get('coins',[]) if c['symbol']==symbol), {})
        key_value = float(request.args.get('key_value', coin.get('ut_key', 2)))
        atr_period = int(request.args.get('atr_period', coin.get('ut_atr', 7)))

        trs = []
        for i in range(1, len(closes)):
            tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
            trs.append(tr)

        trails = []
        signals = []
        if len(trs) >= atr_period:
            atr = calc_rma(trs, atr_period)
            n_loss = key_value * atr
            trail = closes[0]
            prev_close = closes[0]
            for i in range(1, len(closes)):
                c = closes[i]
                prev_trail = trail
                if c > prev_trail:
                    trail = max(prev_trail, c - n_loss)
                else:
                    trail = min(prev_trail, c + n_loss)
                trails.append(round(trail, 8))
                if prev_close <= prev_trail and c > trail:
                    signals.append({'i': i, 'type': 'buy', 'price': c})
                elif prev_close >= prev_trail and c < trail:
                    signals.append({'i': i, 'type': 'sell', 'price': c})
                prev_close = c

        from binance.client import Client
        interval_map = {
            '5m': Client.KLINE_INTERVAL_5MINUTE,
            '15m': Client.KLINE_INTERVAL_15MINUTE,
            '1h': Client.KLINE_INTERVAL_1HOUR,
            '4h': Client.KLINE_INTERVAL_4HOUR,
            '1d': Client.KLINE_INTERVAL_1DAY,
        }
        kl = client.get_klines(symbol=symbol, interval=interval_map.get(interval, Client.KLINE_INTERVAL_5MINUTE), limit=100)
        kl = kl[:-1]
        candles = [{'t': int(k[0]), 'o': float(k[1]), 'h': float(k[2]), 'l': float(k[3]), 'c': float(k[4])} for k in kl]

        return jsonify({'ok': True, 'candles': candles, 'trails': trails, 'signals': signals})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── Coin Seans Analiz ───────────────────────────
@app.route('/api/seans_analiz')
@login_required
def seans_analiz():
    try:
        symbol = request.args.get('symbol', '').upper()
        if not symbol:
            return jsonify({'ok': False, 'error': 'Sembol gerekli'})

        client = get_client()
        from binance.client import Client as BClient
        klines = client.get_klines(symbol=symbol, interval=BClient.KLINE_INTERVAL_1HOUR, limit=180*24)

        import pytz, datetime
        TR_TZ = pytz.timezone('Europe/Istanbul')
        UTC_TZ = pytz.utc

        candles = []
        for k in klines:
            dt_utc = datetime.datetime.fromtimestamp(k[0]/1000, tz=UTC_TZ)
            dt_tr  = dt_utc.astimezone(TR_TZ)
            candles.append({
                'dt_tr':   dt_tr,
                'hour_tr': dt_tr.hour,
                'date_tr': dt_tr.strftime('%Y-%m-%d'),
                'open':    float(k[1]),
                'high':    float(k[2]),
                'low':     float(k[3]),
                'close':   float(k[4]),
            })

        days = {}
        for c in candles:
            d = c['date_tr']
            if d not in days: days[d] = []
            days[d].append(c)
        dates = sorted(days.keys())

        def day_chg(dc):
            if not dc: return None
            return (dc[-1]['close'] - dc[0]['open']) / dc[0]['open'] * 100

        def abd_chg(dc):
            h17 = [c for c in dc if c['hour_tr'] == 17]
            h18 = [c for c in dc if c['hour_tr'] == 18]
            if not h17 or not h18: return None
            return (h18[-1]['close'] - h17[0]['open']) / h17[0]['open'] * 100

        # Genel piyasa verisi — BTC proxy olarak kullan
        btc_klines = client.get_klines(
            symbol='BTCUSDT',
            interval=BClient.KLINE_INTERVAL_1HOUR,
            limit=180*24
        )
        btc_candles = []
        for k in btc_klines:
            dt_utc = datetime.datetime.fromtimestamp(k[0]/1000, tz=UTC_TZ)
            dt_tr  = dt_utc.astimezone(TR_TZ)
            btc_candles.append({
                'dt_tr':   dt_tr,
                'hour_tr': dt_tr.hour,
                'date_tr': dt_tr.strftime('%Y-%m-%d'),
                'open':    float(k[1]),
                'close':   float(k[4]),
            })
        btc_days = {}
        for c in btc_candles:
            d = c['date_tr']
            if d not in btc_days: btc_days[d] = []
            btc_days[d].append(c)

        def btc_day_chg(date_str):
            dc = btc_days.get(date_str, [])
            if not dc: return None
            return (dc[-1]['close'] - dc[0]['open']) / dc[0]['open'] * 100

        def btc_abd_chg(date_str):
            dc = btc_days.get(date_str, [])
            h17 = [c for c in dc if c['hour_tr'] == 17]
            h18 = [c for c in dc if c['hour_tr'] == 18]
            if not h17 or not h18: return None
            return (h18[-1]['close'] - h17[0]['open']) / h17[0]['open'] * 100

        def coin_today_chg(day_candles):
            # Coinin bugün 17:00 açılışından şu ana kadarki değişim
            h17 = [c for c in day_candles if c['hour_tr'] == 17]
            h20 = [c for c in day_candles if c['hour_tr'] == 20]
            if not h17 or not h20: return None
            return (h20[0]['open'] - h17[0]['open']) / h17[0]['open'] * 100

        def btc_today_chg(date_str):
            dc = btc_days.get(date_str, [])
            h17 = [c for c in dc if c['hour_tr'] == 17]
            h20 = [c for c in dc if c['hour_tr'] == 20]
            if not h17 or not h20: return None
            return (h20[0]['open'] - h17[0]['open']) / h17[0]['open'] * 100

        def run_backtest(buy_hour, sell_hour, btc_yesterday_fn, btc_today_fn, coin_today_fn):
            # btc_yesterday_fn: True/False — BTC dünkü gün koşulu
            # btc_today_fn: True/False — BTC bugünkü koşulu
            # coin_today_fn: True/False — Coin bugünkü koşulu
            total = wins = trades = 0
            for i, date in enumerate(dates):
                if i < 2: continue
                today_dc = days[date]
                prev_date = dates[i-1]

                # BTC dün
                btc_prev = btc_day_chg(prev_date)
                if btc_prev is None: continue
                if not btc_yesterday_fn(btc_prev): continue

                # BTC bugün (17:00-20:00)
                btc_tod = btc_today_chg(date)
                if btc_tod is None: continue
                if not btc_today_fn(btc_tod): continue

                # Coin bugün (17:00-20:00)
                coin_tod = coin_today_chg(today_dc)
                if coin_tod is None: continue
                if not coin_today_fn(coin_tod): continue

                if i+1 >= len(dates): continue
                bd = today_dc
                sd = days[dates[i+1]]
                bc = [c for c in bd if c['hour_tr'] == buy_hour]
                sc = [c for c in sd if c['hour_tr'] == sell_hour]
                if not bc or not sc: continue
                pct = (sc[0]['open'] - bc[0]['open']) / bc[0]['open'] * 100
                net = pct - 0.2
                total += net
                trades += 1
                if net > 0: wins += 1
            wr = round(wins/trades*100,1) if trades > 0 else 0
            avg = round(total/trades,2) if trades > 0 else 0
            return {'trades': trades, 'wins': wins, 'wr': wr, 'net': round(total,2), 'avg': avg}

        G = lambda x: x >= 0
        R = lambda x: x < 0

        # ── Yeni faktörler ────────────────────────────

        def asian_chg(dc):
            """Asya seansı 03:00-10:00 TR değişimi"""
            h3  = [c for c in dc if c['hour_tr'] == 3]
            h10 = [c for c in dc if c['hour_tr'] == 10]
            if not h3 or not h10: return None
            return (h10[-1]['close'] - h3[0]['open']) / h3[0]['open'] * 100

        def run_composite(buy_h, sell_h, min_score):
            """
            Composite skor: 5 faktör her biri 1 puan
              1. BTC dün >= 0
              2. BTC 17:00-20:00 >= 0
              3. Coin 17:00-20:00 >= 0
              4. Coin dün >= 0
              5. Asya seansı (önceki gün 03:00-10:00) >= 0
            """
            total = wins = trades = 0
            for i, date in enumerate(dates):
                if i < 2: continue
                today_dc  = days[date]
                prev_date = dates[i-1]

                bp = btc_day_chg(prev_date)
                bt = btc_today_chg(date)
                ct = coin_today_chg(today_dc)
                cp = day_chg(days.get(prev_date, []))
                as_ = asian_chg(days.get(prev_date, []))

                score = sum(1 for v in [bp, bt, ct, cp, as_] if v is not None and v >= 0)
                if score < min_score: continue

                if i + 1 >= len(dates): continue
                sd = days[dates[i+1]]
                bc = [c for c in today_dc if c['hour_tr'] == buy_h]
                sc = [c for c in sd       if c['hour_tr'] == sell_h]
                if not bc or not sc: continue
                net = (sc[0]['open'] - bc[0]['open']) / bc[0]['open'] * 100 - 0.2
                total += net; trades += 1
                if net > 0: wins += 1
            wr  = round(wins/trades*100, 1) if trades > 0 else 0
            avg = round(total/trades,    2) if trades > 0 else 0
            return {'trades': trades, 'wins': wins, 'wr': wr, 'net': round(total,2), 'avg': avg}

        def run_rel_strong(buy_h, sell_h):
            """Coin 17:00-20:00 hareketi BTC'den güçlü olduğunda al"""
            total = wins = trades = 0
            for i, date in enumerate(dates):
                if i < 1: continue
                today_dc = days[date]
                ct = coin_today_chg(today_dc)
                bt = btc_today_chg(date)
                if ct is None or bt is None: continue
                if ct - bt < 0: continue  # coin BTC'den zayıf → atla

                if i + 1 >= len(dates): continue
                sd = days[dates[i+1]]
                bc = [c for c in today_dc if c['hour_tr'] == buy_h]
                sc = [c for c in sd       if c['hour_tr'] == sell_h]
                if not bc or not sc: continue
                net = (sc[0]['open'] - bc[0]['open']) / bc[0]['open'] * 100 - 0.2
                total += net; trades += 1
                if net > 0: wins += 1
            wr  = round(wins/trades*100, 1) if trades > 0 else 0
            avg = round(total/trades,    2) if trades > 0 else 0
            return {'trades': trades, 'wins': wins, 'wr': wr, 'net': round(total,2), 'avg': avg}

        def run_dow(buy_h, sell_h):
            """Haftanın günlerine göre performans analizi"""
            DOW = ['Pzt','Sal','Çar','Per','Cum','Cmt','Paz']
            by_dow = {d: [0, 0, 0.0] for d in range(7)}  # [trades, wins, total]
            for i, date in enumerate(dates[:-1]):
                today_dc = days[date]
                dow = datetime.datetime.strptime(date, '%Y-%m-%d').weekday()
                sd  = days[dates[i+1]]
                bc  = [c for c in today_dc if c['hour_tr'] == buy_h]
                sc  = [c for c in sd       if c['hour_tr'] == sell_h]
                if not bc or not sc: continue
                net = (sc[0]['open'] - bc[0]['open']) / bc[0]['open'] * 100 - 0.2
                by_dow[dow][0] += 1
                by_dow[dow][2] += net
                if net > 0: by_dow[dow][1] += 1
            result = {}
            for d in range(7):
                t, w, tot = by_dow[d]
                result[DOW[d]] = {
                    'trades': t,
                    'wr':  round(w/t*100, 1) if t > 0 else 0,
                    'avg': round(tot/t,   2) if t > 0 else 0,
                    'net': round(tot,     2),
                }
            return result

        def run_backtest_coin_only(buy_hour, sell_hour, coin_prev_fn, coin_today_fn):
            total = wins = trades = 0
            for i, date in enumerate(dates):
                if i < 2: continue
                today_dc = days[date]
                prev_date = dates[i-1]
                coin_prev = day_chg(days.get(prev_date, []))
                if coin_prev is None: continue
                if not coin_prev_fn(coin_prev): continue
                coin_tod = coin_today_chg(today_dc)
                if coin_tod is None: continue
                if not coin_today_fn(coin_tod): continue
                if i+1 >= len(dates): continue
                bd = today_dc
                sd = days[dates[i+1]]
                bc = [c for c in bd if c['hour_tr'] == buy_hour]
                sc = [c for c in sd if c['hour_tr'] == sell_hour]
                if not bc or not sc: continue
                pct = (sc[0]['open'] - bc[0]['open']) / bc[0]['open'] * 100
                net = pct - 0.2
                total += net
                trades += 1
                if net > 0: wins += 1
            wr = round(wins/trades*100,1) if trades > 0 else 0
            avg = round(total/trades,2) if trades > 0 else 0
            return {'trades': trades, 'wins': wins, 'wr': wr, 'net': round(total,2), 'avg': avg}

        SELL_HOURS = [11, 12, 13, 19]

        def run_all(buy_h, sell_h):
            return {
                'coin_yy':       run_backtest_coin_only(buy_h, sell_h, G, G),
                'coin_ky':       run_backtest_coin_only(buy_h, sell_h, R, G),
                'coin_kk':       run_backtest_coin_only(buy_h, sell_h, R, R),
                'coin_yk':       run_backtest_coin_only(buy_h, sell_h, G, R),
                'btc_yy_coin_y': run_backtest(buy_h, sell_h, G, G, G),
                'btc_yy_coin_r': run_backtest(buy_h, sell_h, G, G, R),
                'btc_rr_coin_y': run_backtest(buy_h, sell_h, R, R, G),
                'btc_rr_coin_r': run_backtest(buy_h, sell_h, R, R, R),
                'btc_yr_coin_y': run_backtest(buy_h, sell_h, G, R, G),
                'btc_yr_coin_r': run_backtest(buy_h, sell_h, G, R, R),
                'btc_ry_coin_y': run_backtest(buy_h, sell_h, R, G, G),
                'btc_ry_coin_r': run_backtest(buy_h, sell_h, R, G, R),
                'composite_3':   run_composite(buy_h, sell_h, 3),
                'composite_4':   run_composite(buy_h, sell_h, 4),
                'composite_5':   run_composite(buy_h, sell_h, 5),
                'rel_strong':    run_rel_strong(buy_h, sell_h),
            }

        by_hour = {str(h): run_all(20, h) for h in SELL_HOURS}

        # Varsayılan (13:00) sonuçları geriye dönük uyumluluk için
        results = by_hour['13']

        # Her satış saati için en iyi strateji — skor = wr * log(trades+1)
        import math
        def _best_for_hour(hour_results):
            def _sc(k):
                v = hour_results[k]
                if v['trades'] == 0: return -999
                return v['wr'] * math.log(v['trades'] + 1)
            return max(hour_results, key=_sc)

        best_by_hour = {str(h): _best_for_hour(by_hour[str(h)]) for h in SELL_HOURS}

        # ── Oynaklık Analizi ─────────────────────────
        # 20:00 alım → ertesi 13:00 arası max düşüş ve max yükseliş
        drawdowns, gains = [], []
        for i, date in enumerate(dates[:-1]):
            today_dc = days[date]
            next_dc  = days[dates[i + 1]]
            buy_c    = [c for c in today_dc if c['hour_tr'] == 20]
            if not buy_c:
                continue
            buy_price = buy_c[0]['open']
            overnight = [c for c in today_dc if c['hour_tr'] >= 20] + \
                        [c for c in next_dc   if c['hour_tr'] <= 13]
            if len(overnight) < 2:
                continue
            min_low  = min(c['low']  for c in overnight)
            max_high = max(c['high'] for c in overnight)
            drawdowns.append((buy_price - min_low)  / buy_price * 100)
            gains.append(    (max_high - buy_price) / buy_price * 100)

        def _pct(lst, p):
            if not lst:
                return 0.0
            s = sorted(lst)
            return round(s[min(int(len(s) * p / 100), len(s) - 1)], 1)

        volatility = {
            'avg_drawdown':  round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else 0,
            'avg_gain':      round(sum(gains)     / len(gains),     2) if gains     else 0,
            # %70 işlemde bu seviyenin üzerinde kalıyor → güvenli SL
            'suggested_sl':  _pct(drawdowns, 70),
            # %60 işlemde bu seviyeye ulaşıyor → gerçekçi TP
            'suggested_tp':  _pct(gains, 60),
            'count': len(drawdowns),
        }

        dow_analysis = run_dow(20, 13)

        # ── Saat Matrisi: tüm alım × satım kombinasyonları ─
        BUY_HOURS  = [16, 17, 18, 19, 20, 21, 22, 23]
        SELL_HOURS_M = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]

        def run_timing(buy_h, sell_h):
            total = wins = trades = 0
            for i, date in enumerate(dates[:-1]):
                today_dc = days[date]
                next_dc  = days[dates[i+1]]
                bc = [c for c in today_dc if c['hour_tr'] == buy_h]
                sc = [c for c in next_dc  if c['hour_tr'] == sell_h]
                if not bc or not sc: continue
                net = (sc[0]['open'] - bc[0]['open']) / bc[0]['open'] * 100 - 0.2
                total += net; trades += 1
                if net > 0: wins += 1
            wr  = round(wins/trades*100, 1) if trades > 0 else 0
            avg = round(total/trades,    2) if trades > 0 else 0
            return {'wr': wr, 'avg': avg, 'trades': trades}

        timing_matrix = {
            str(bh): {str(sh): run_timing(bh, sh) for sh in SELL_HOURS_M}
            for bh in BUY_HOURS
        }

        # En iyi saat kombinasyonu (min 20 işlem)
        best_timing = max(
            ((bh, sh) for bh in BUY_HOURS for sh in SELL_HOURS_M
             if timing_matrix[str(bh)][str(sh)]['trades'] >= 20),
            key=lambda x: timing_matrix[str(x[0])][str(x[1])]['wr'],
            default=(20, 13)
        )

        return jsonify({
            'ok': True,
            'symbol': symbol,
            'results': results,
            'by_hour': by_hour,
            'best_strategy': best_by_hour,
            'volatility': volatility,
            'dow_analysis': dow_analysis,
            'timing_matrix': timing_matrix,
            'best_timing': {'buy': best_timing[0], 'sell': best_timing[1]},
            'timing_buy_hours': BUY_HOURS,
            'timing_sell_hours': SELL_HOURS_M,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── Ajan Karşılaştırma Tablosu ───────────────────
@app.route('/api/agent_comparison')
@login_required
def agent_comparison():
    """Tüm ajan ve indikatörlerin karlılık karşılaştırma tablosu."""
    trades = load_trades()
    trades_sorted = sorted(trades, key=lambda t: t.get('time', ''))

    AGENTS = [
        'INDICATOR-UTBOT', 'INDICATOR-SMART', 'INDICATOR-SEANS',
        'BREAKOUT', 'WYCKOFF', 'EDGE', 'OTONOM', 'UT BOT', 'SEANS', 'SMART', 'MANUEL', 'DİĞER',
    ]

    def _normalize(source):
        s = (source or '').upper()
        if 'INDICATOR-UTBOT' in s:  return 'INDICATOR-UTBOT'
        if 'INDICATOR-SMART' in s:  return 'INDICATOR-SMART'
        if 'INDICATOR-SEANS' in s:  return 'INDICATOR-SEANS'
        if 'INDICATOR' in s:        return 'INDICATOR-UTBOT'  # eski kayıtlar UTBOT'a düşsün
        if 'BREAKOUT' in s:         return 'BREAKOUT'
        if 'WYCKOFF' in s:          return 'WYCKOFF'
        if 'EDGE' in s:             return 'EDGE'
        if 'OTONOM' in s:           return 'OTONOM'
        if 'UT' in s:               return 'UT BOT'
        if 'SEANS' in s:            return 'SEANS'
        if 'SMART' in s:            return 'SMART'
        if 'MANUEL' in s:           return 'MANUEL'
        return 'DİĞER'

    stats = {a: {'wins': 0, 'losses': 0, 'total': 0, 'pnl': 0.0,
                 'best': 0.0, 'worst': 0.0} for a in AGENTS}
    last_buy_agent = {}

    for t in trades_sorted:
        sym    = t.get('symbol', '')
        source = t.get('source', '')
        if t.get('type') == 'buy':
            last_buy_agent[sym] = _normalize(source)
        elif t.get('type') == 'sell':
            agent = last_buy_agent.get(sym, _normalize(source))
            if agent not in stats:
                stats[agent] = {'wins': 0, 'losses': 0, 'total': 0,
                                'pnl': 0.0, 'best': 0.0, 'worst': 0.0}
            pnl = float(t.get('pnl', 0) or 0)
            s   = stats[agent]
            s['total'] += 1
            s['pnl']    = round(s['pnl'] + pnl, 2)
            if pnl > 0:
                s['wins']  += 1
                s['best']   = max(s['best'], pnl)
            else:
                s['losses'] += 1
                s['worst']  = min(s['worst'], pnl)

    table = []
    for agent in AGENTS:
        s = stats[agent]
        if s['total'] == 0:
            continue
        wr  = round(s['wins'] / s['total'] * 100, 1)
        avg = round(s['pnl'] / s['total'], 2)
        table.append({
            'agent':   agent,
            'total':   s['total'],
            'wins':    s['wins'],
            'losses':  s['losses'],
            'wr':      wr,
            'pnl':     s['pnl'],
            'avg_pnl': avg,
            'best':    round(s['best'], 2),
            'worst':   round(s['worst'], 2),
        })

    # En karlıyı belirle
    if table:
        best_agent = max(table, key=lambda x: x['pnl'])
        for row in table:
            row['is_best'] = (row['agent'] == best_agent['agent'])

    return jsonify({'ok': True, 'table': table})

# ── Indicator Agent API ───────────────────────────
@app.route('/indicator/start', methods=['POST'])
@login_required
def indicator_start():
    ok = start_indicator_agent()
    return jsonify({'ok': ok, 'msg': 'Indicator Agent başlatıldı' if ok else 'Zaten çalışıyor'})

@app.route('/indicator/stop', methods=['POST'])
@login_required
def indicator_stop():
    stop_indicator_agent()
    return jsonify({'ok': True})

@app.route('/indicator/status')
@login_required
def indicator_status_api():
    return jsonify(indicator_agent_status())

# ── Otonom Ajan API ──────────────────────────────
@app.route('/agent/start', methods=['POST'])
@login_required
def agent_start():
    ok = start_autonomous_agent()
    return jsonify({'ok': ok, 'msg': 'Ajan başlatıldı' if ok else 'Zaten çalışıyor'})

@app.route('/agent/stop', methods=['POST'])
@login_required
def agent_stop():
    stop_autonomous_agent()
    return jsonify({'ok': True})

@app.route('/agent/status')
@login_required
def agent_status_api():
    return jsonify(agent_status())

# ── Edge Agent API ────────────────────────────────
@app.route('/edge/start', methods=['POST'])
@login_required
def edge_start():
    ok = start_edge_agent()
    return jsonify({'ok': ok, 'msg': 'Edge Agent başlatıldı' if ok else 'Zaten çalışıyor'})

@app.route('/edge/stop', methods=['POST'])
@login_required
def edge_stop():
    stop_edge_agent()
    return jsonify({'ok': True})

@app.route('/edge/status')
@login_required
def edge_status_api():
    return jsonify(edge_agent_status())

# ── Ajan Aç/Kapat API ────────────────────────────
@app.route('/api/agent_toggle', methods=['POST'])
@login_required
def api_agent_toggle():
    data = request.get_json()
    agent   = data.get('agent', '')
    enabled = bool(data.get('enabled', True))

    KEY_MAP = {
        'edge':      'edge_enabled',
        'otonom':    'otonom_enabled',
        'indicator': 'indicator_enabled',
        'wyckoff':   'wyckoff_enabled',
        'breakout':  'breakout_enabled',
        'ceo':       'ceo_agent_enabled',
    }
    if agent not in KEY_MAP:
        return jsonify({'ok': False, 'error': 'Bilinmeyen ajan'})

    cfg = load_config()
    cfg[KEY_MAP[agent]] = enabled
    save_config(cfg)

    if agent == 'edge':
        if enabled: start_edge_agent()
        else: stop_edge_agent()
    elif agent == 'otonom':
        if enabled: start_autonomous_agent()
        else: stop_autonomous_agent()
    elif agent == 'indicator':
        if enabled: start_indicator_agent()
        else: stop_indicator_agent()
    elif agent == 'wyckoff':
        if enabled: start_wyckoff_agent()
        else: stop_wyckoff_agent()
    elif agent == 'breakout':
        if enabled: start_breakout_agent()
        else: stop_breakout_agent()
    elif agent == 'ceo':
        if enabled: start_ceo_agent()
        else: stop_ceo_agent()

    return jsonify({'ok': True, 'agent': agent, 'enabled': enabled})

# ── Bot Kontrolü API ──────────────────────────────
@app.route('/api/bot_control', methods=['POST'])
@login_required
def api_bot_control():
    data   = request.get_json()
    action = data.get('action', '')
    cfg    = load_config()

    if action == 'start':
        cfg['bot_paused'] = False
        save_config(cfg)
        return jsonify({'ok': True, 'msg': '▶️ Bot başlatıldı'})
    elif action == 'stop':
        cfg['bot_paused'] = True
        save_config(cfg)
        return jsonify({'ok': True, 'msg': '⏸ Bot duraklatıldı'})
    elif action == 'restart':
        import subprocess
        subprocess.Popen(['systemctl', 'restart', 'kripto-bot'])
        return jsonify({'ok': True, 'msg': '🔄 Bot yeniden başlatılıyor...'})
    return jsonify({'ok': False, 'error': 'Bilinmeyen eylem'})

# ── CEO Manuel Analiz API ─────────────────────────
@app.route('/api/ceo_analyze_now', methods=['POST'])
@login_required
def api_ceo_analyze_now():
    st = ceo_agent_status()
    if not st.get('enabled'):
        return jsonify({'ok': False, 'error': 'CEO kapalı. Önce açın.'})
    trigger_ceo_review()
    return jsonify({'ok': True, 'msg': '👔 CEO analizi başlatıldı'})

# ── Başlat ───────────────────────────────────────
if __name__ == '__main__':
    start_engine()            # UT Bot + Seans + Smart (manuel coinler)
    start_telegram_bot()
    start_autonomous_agent()  # Teknik analiz: RSI/MACD/BB/Trend (otonom)
    start_edge_agent()        # Piyasa mekaniği: Funding/OI/CVD/Sweep (otonom)
    start_indicator_agent()   # UT Bot tarayıcı: otomatik coin seçimi (otonom)
    start_wyckoff_agent()     # Wyckoff akümülasyon: dar bant + sahte pump + kırılış
    start_breakout_agent()    # Momentum kırılım: hacim spike + trailing stop (sabit TP yok)
    cfg = load_config()
    if cfg.get('ceo_agent_enabled', False):
        start_ceo_agent()     # CEO: ajan performans analizi + parametre optimizasyonu
    app.run(host='0.0.0.0', port=5000, debug=False)
