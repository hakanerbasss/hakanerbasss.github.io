from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
import json, os, hashlib, datetime
from bot import (load_config, save_config, get_client, get_market_summary,
                 get_fear_greed, get_portfolio_summary, execute_buy, execute_sell,
                 load_trades, load_positions, get_usdt_balance)
from signal_engine import start_engine
from telegram_bot import start_telegram_bot

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
        client = get_client()
        market = get_market_summary(client)
        fg = get_fear_greed()
        portfolio = get_portfolio_summary(client)
        usdt_balance = get_usdt_balance(client)
        return jsonify({'ok': True, 'market': market, 'fear_greed': fg, 'portfolio': portfolio, 'usdt_balance': usdt_balance})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── API: Trades ──────────────────────────────────
@app.route('/api/trades')
@login_required
def api_trades():
    trades = load_trades()
    return jsonify(list(reversed(trades[-50:])))

# ── Ayarlar ──────────────────────────────────────
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
        # Kapanış sinyali satış
        'close_sell_pct':      float(data.get('close_sell_pct', 100)),
        # Kâr hedefi
        'take_profit_pct':     float(data.get('take_profit_pct', 0)),
        'take_profit_sell_pct':float(data.get('take_profit_sell_pct', 100)),
        # Stop loss
        'stop_loss_pct':       float(data.get('stop_loss_pct', 0)),
        'stop_loss_sell_pct':  float(data.get('stop_loss_sell_pct', 100)),
        'seans_strategy':      data.get('seans_strategy', 'both'),
        'seans_sell_hour':     int(data.get('seans_sell_hour', 13)),
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
            c['close_sell_pct']       = float(data.get('close_sell_pct', c.get('close_sell_pct', 100)))
            c['take_profit_pct']      = float(data.get('take_profit_pct', c.get('take_profit_pct', 0)))
            c['take_profit_sell_pct'] = float(data.get('take_profit_sell_pct', c.get('take_profit_sell_pct', 100)))
            c['stop_loss_pct']        = float(data.get('stop_loss_pct', c.get('stop_loss_pct', 0)))
            c['stop_loss_sell_pct']   = float(data.get('stop_loss_sell_pct', c.get('stop_loss_sell_pct', 100)))
            c['seans_strategy']       = data.get('seans_strategy', c.get('seans_strategy', 'both'))
            c['seans_sell_hour']      = int(data.get('seans_sell_hour', c.get('seans_sell_hour', 13)))
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
            }

        by_hour = {str(h): run_all(20, h) for h in SELL_HOURS}

        # Varsayılan (13:00) sonuçları geriye dönük uyumluluk için
        results = by_hour['13']

        # En iyi strateji: önce win rate, eşitse net %
        best_key = max(
            results,
            key=lambda k: (results[k]['wr'], results[k]['net'])
            if results[k]['trades'] >= 5 else (-1, -999)
        )

        return jsonify({
            'ok': True,
            'symbol': symbol,
            'results': results,
            'by_hour': by_hour,
            'best_strategy': best_key,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── Başlat ───────────────────────────────────────
if __name__ == '__main__':
    start_engine()
    start_telegram_bot()
    app.run(host='0.0.0.0', port=5000, debug=False)
