from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
import json, os, hashlib, datetime
from bot import (load_config, save_config, get_client, get_market_summary,
                 get_fear_greed, get_portfolio_summary, execute_buy, execute_sell,
                 load_trades, load_positions, get_usdt_balance)
from signal_engine import start_engine
from telegram_bot import start_telegram_bot
from autonomous_agent import (start_autonomous_agent, stop_autonomous_agent,
                               agent_status)

app = Flask(__name__)
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

# ── Auth ──────────────────────────────────────────────────
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

# ── Ana Sayfa ────────────────────────────────────────────
@app.route('/')
@login_required
def index():
    cfg = load_config()
    return render_template('index.html', cfg=cfg)

# ── API: Dashboard ───────────────────────────────────────
@app.route('/api/dashboard')
@login_required
def api_dashboard():
    try:
        client = get_client()
        market = get_market_summary(client)
        fg = get_fear_greed()
        portfolio = get_portfolio_summary(client)
        usdt_balance = get_usdt_balance(client)
        return jsonify({'ok': True, 'market': market, 'fear_greed': fg, 'portfolio': portfolio, 'usdt_balance': usdt_balance})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── API: Trades ──────────────────────────────────────────
@app.route('/api/trades')
@login_required
def api_trades():
    trades = load_trades()
    return jsonify(list(reversed(trades[-50:])))

@app.route('/trades/reset', methods=['POST'])
@login_required
def trades_reset():
    from bot import save_trades
    save_trades([])
    return jsonify({'ok': True})

# ── API: Stats ──────────────────────────────────────────────
@app.route('/api/stats')
@login_required
def api_stats():
    trades = load_trades()
    trades_sorted = sorted(trades, key=lambda t: t.get('time', ''))

    def _normalize(source):
        s = (source or '').upper()
        if 'UT' in s:      return 'UT BOT'
        if 'SEANS' in s:   return 'SEANS'
        if 'SMART' in s:   return 'SMART'
        if 'OTONOM' in s:  return 'OTONOM'
        if 'MANUEL' in s:  return 'MANUEL'
        return 'DİĞER'

    last_buy_source = {}
    by_ind = {}

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

# ── Ayarlar ────────────────────────────────────────────────
@app.route('/settings', methods=['POST'])
@login_required
def settings():
    cfg = load_config()
    cfg['api_key']          = request.form.get('api_key', '')
    cfg['api_secret']       = request.form.get('api_secret', '')
    cfg['real_api_key']     = request.form.get('real_api_key', '')
    cfg['real_api_secret']  = request.form.get('real_api_secret', '')
    cfg['testnet']          = request.form.get('testnet') == 'on'
    cfg['webhook_secret']   = request.form.get('webhook_secret', 'secret123')
    cfg['check_interval']   = int(request.form.get('check_interval', 45))
    cfg['telegram_token']   = request.form.get('telegram_token', '')
    cfg['telegram_chat_id'] = request.form.get('telegram_chat_id', '')
    save_config(cfg)
    return jsonify({'ok': True})

# ── Coin Yönetimi ────────────────────────────────────────────
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
        'ut_key':              float(data.get('ut_key', 2)),
        'ut_atr':              int(data.get('ut_atr', 7)),
        'ut_mode':             data.get('ut_mode', 'crossover'),
        'close_sell_pct':      float(data.get('close_sell_pct', 100)),
        'take_profit_pct':     float(data.get('take_profit_pct', 0)),
        'take_profit_sell_pct':float(data.get('take_profit_sell_pct', 100)),
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

# ── Webhook ────────────────────────────────────────────────
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

# ── Manuel İşlem ─────────────────────────────────────────────
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

# ── Grafik ───────────────────────────────────────────────────
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
        trails = []; signals = []
        if len(trs) >= atr_period:
            atr = calc_rma(trs, atr_period)
            n_loss = key_value * atr
            trail = closes[0]; prev_close = closes[0]
            for i in range(1, len(closes)):
                c = closes[i]; prev_trail = trail
                if c > prev_trail: trail = max(prev_trail, c - n_loss)
                else: trail = min(prev_trail, c + n_loss)
                trails.append(round(trail, 8))
                if prev_close <= prev_trail and c > trail: signals.append({'i': i, 'type': 'buy', 'price': c})
                elif prev_close >= prev_trail and c < trail: signals.append({'i': i, 'type': 'sell', 'price': c})
                prev_close = c
        from binance.client import Client
        interval_map = {'5m': Client.KLINE_INTERVAL_5MINUTE, '15m': Client.KLINE_INTERVAL_15MINUTE,
                        '1h': Client.KLINE_INTERVAL_1HOUR, '4h': Client.KLINE_INTERVAL_4HOUR, '1d': Client.KLINE_INTERVAL_1DAY}
        kl = client.get_klines(symbol=symbol, interval=interval_map.get(interval, Client.KLINE_INTERVAL_5MINUTE), limit=100)
        kl = kl[:-1]
        candles = [{'t': int(k[0]), 'o': float(k[1]), 'h': float(k[2]), 'l': float(k[3]), 'c': float(k[4])} for k in kl]
        return jsonify({'ok': True, 'candles': candles, 'trails': trails, 'signals': signals})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── Otonom Ajan API ────────────────────────────────────────
@app.route('/agent/start', methods=['POST'])
def agent_start():
    ok = start_autonomous_agent()
    return jsonify({'ok': ok, 'msg': 'Ajan başlatıldı' if ok else 'Zaten çalışıyor'})

@app.route('/agent/stop', methods=['POST'])
def agent_stop():
    stop_autonomous_agent()
    return jsonify({'ok': True})

@app.route('/agent/status')
def agent_status_api():
    return jsonify(agent_status())

# ── Başlat ─────────────────────────────────────────────────
if __name__ == '__main__':
    start_engine()
    start_telegram_bot()
    start_autonomous_agent()
    app.run(host='0.0.0.0', port=5000, debug=False)
