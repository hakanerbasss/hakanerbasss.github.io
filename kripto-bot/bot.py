import json, os, datetime, urllib.request, urllib.parse
from binance.client import Client

CONFIG_FILE = 'config.json'
TRADES_FILE = 'trades.json'
POSITIONS_FILE = 'positions.json'

# ── Config ──────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {'testnet': True, 'api_key': '', 'api_secret': '', 'coins': [], 'webhook_secret': 'secret123'}

def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ── Trades ──────────────────────────────────────
def load_trades():
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE) as f:
            return json.load(f)
    return []

def save_trades(trades):
    with open(TRADES_FILE, 'w') as f:
        json.dump(trades, f, indent=2)

# ── Positions ───────────────────────────────────
def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE) as f:
            return json.load(f)
    return {}

def save_positions(positions):
    with open(POSITIONS_FILE, 'w') as f:
        json.dump(positions, f, indent=2)

# ── Binance Client ──────────────────────────────
def get_client():
    cfg = load_config()
    is_testnet = cfg.get('testnet', True)
    if is_testnet:
        api_key    = cfg.get('api_key', '')
        api_secret = cfg.get('api_secret', '')
        client = Client(api_key, api_secret, testnet=True)
        client.API_URL = 'https://testnet.binance.vision/api'
    else:
        api_key    = cfg.get('real_api_key', '')
        api_secret = cfg.get('real_api_secret', '')
        client = Client(api_key, api_secret)
    return client

# ── Market Data ─────────────────────────────────
def get_market_summary(client):
    tickers = client.get_ticker()
    usdt_pairs = [t for t in tickers if t['symbol'].endswith('USDT')]
    total = len(usdt_pairs)
    red = [t for t in usdt_pairs if float(t['priceChangePercent']) < 0]
    green = [t for t in usdt_pairs if float(t['priceChangePercent']) >= 0]
    red_pct = round(len(red) / total * 100, 1) if total > 0 else 0

    top_gainers = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']), reverse=True)[:5]
    top_losers = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']))[:5]
    top50 = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)[:50]

    return {
        'total': total,
        'red': len(red),
        'green': len(green),
        'red_pct': red_pct,
        'green_pct': round(100 - red_pct, 1),
        'top_gainers': [{'symbol': t['symbol'], 'change': float(t['priceChangePercent']), 'price': float(t['lastPrice'])} for t in top_gainers],
        'top_losers': [{'symbol': t['symbol'], 'change': float(t['priceChangePercent']), 'price': float(t['lastPrice'])} for t in top_losers],
        'top50': [{'symbol': t['symbol'], 'price': float(t['lastPrice']), 'change': float(t['priceChangePercent']), 'volume': float(t['quoteVolume']), 'high': float(t['highPrice']), 'low': float(t['lowPrice'])} for t in top50],
    }

def get_fear_greed():
    try:
        import urllib.request
        url = 'https://api.alternative.me/fng/?limit=1'
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
            d = data['data'][0]
            return {'value': int(d['value']), 'label': d['value_classification']}
    except:
        return {'value': 0, 'label': 'N/A'}

def get_price(client, symbol):
    try:
        t = client.get_ticker(symbol=symbol)
        return float(t['lastPrice'])
    except:
        return 0.0

# ── Bakiye ───────────────────────────────────────
def get_usdt_balance(client):
    try:
        account = client.get_account()
        for b in account['balances']:
            if b['asset'] == 'USDT':
                return float(b['free'])
        return 0.0
    except:
        return 0.0

# ── Portfolio ────────────────────────────────────
def get_portfolio_summary(client):
    positions = load_positions()
    trades = load_trades()
    result = []
    total_invested = 0
    total_current = 0

    for symbol, pos in positions.items():
        if pos.get('qty', 0) <= 0:
            continue
        # Pozisyon değeri $1 altındaysa yok say
        current_price = get_price(client, symbol)
        if pos.get('qty', 0) * current_price < 1.0:
            continue
        current_price = get_price(client, symbol)
        invested = pos['avg_price'] * pos['qty']
        current_val = current_price * pos['qty']
        pnl = current_val - invested
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0
        total_invested += invested
        total_current += current_val
        result.append({
            'symbol': symbol,
            'qty': pos['qty'],
            'avg_price': pos['avg_price'],
            'current_price': current_price,
            'invested': round(invested, 2),
            'current_val': round(current_val, 2),
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
        })

    closed = [t for t in trades if t.get('type') == 'sell']
    wins = [t for t in closed if t.get('pnl', 0) > 0]
    success_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0

    return {
        'positions': result,
        'total_invested': round(total_invested, 2),
        'total_current': round(total_current, 2),
        'total_pnl': round(total_current - total_invested, 2),
        'total_pnl_pct': round((total_current - total_invested) / total_invested * 100, 1) if total_invested > 0 else 0,
        'success_rate': success_rate,
        'total_trades': len(closed),
        'win_trades': len(wins),
    }

# ── Execute Order ────────────────────────────────
def get_symbol_filters(client, symbol):
    info = client.get_symbol_info(symbol)
    step = 0.001
    min_notional = 5.0  # varsayılan $5
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            step = float(f['stepSize'])
        if f['filterType'] == 'NOTIONAL':
            min_notional = float(f['minNotional'])
        if f['filterType'] == 'MIN_NOTIONAL':
            min_notional = float(f['minNotional'])
    return step, min_notional

def get_step_size(client, symbol):
    step, _ = get_symbol_filters(client, symbol)
    return step

def round_step(qty, step):
    import math
    precision = int(round(-math.log10(step)))
    return round(math.floor(qty / step) * step, precision)

def execute_buy(client, symbol, usdt_amount, source='MANUEL', period='—'):
    try:
        price = get_price(client, symbol)
        if price <= 0:
            return {'ok': False, 'error': 'Fiyat alınamadı'}
        # Bakiye kontrolü
        balance = get_usdt_balance(client)
        if balance < usdt_amount:
            return {'ok': False, 'error': f'Yetersiz bakiye: ${round(balance,2)} USDT'}

        step = get_step_size(client, symbol)
        qty = round_step(usdt_amount / price, step)
        if qty <= 0:
            return {'ok': False, 'error': f'Miktar çok küçük (step: {step})'}
        order = client.order_market_buy(symbol=symbol, quantity=qty)
        positions = load_positions()
        pos = positions.get(symbol, {'qty': 0, 'avg_price': 0})
        total_qty = pos['qty'] + qty
        avg = ((pos['qty'] * pos['avg_price']) + (qty * price)) / total_qty
        positions[symbol] = {'qty': total_qty, 'avg_price': avg}
        save_positions(positions)
        trades = load_trades()
        trades.append({
            'type': 'buy', 'symbol': symbol, 'qty': qty,
            'price': price, 'usdt': usdt_amount,
            'source': source,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        save_trades(trades)
        send_telegram(f'✅ <b>ALIM</b> [{source}]\nCoin: {symbol}\nFiyat: ${price}\nMiktar: {qty}\nTutar: ${usdt_amount}\nPeriyot: {period}')
        return {'ok': True, 'qty': qty, 'price': price}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def execute_sell(client, symbol, sell_pct, source='MANUEL', period='—'):
    try:
        positions = load_positions()
        pos = positions.get(symbol)
        if not pos or pos.get('qty', 0) <= 0:
            return {'ok': False, 'error': 'Açık pozisyon yok'}
        step, min_notional = get_symbol_filters(client, symbol)
        price = get_price(client, symbol)
        total_qty = pos['qty']
        total_value = total_qty * price

        # İstenen satış miktarı
        sell_qty = round_step(total_qty * (sell_pct / 100), step)
        sell_value = sell_qty * price

        # Satış tutarı min tutarın altındaysa min tutara yükselt
        if sell_value < min_notional:
            sell_qty = round_step(min_notional / price * 1.01, step)
            sell_value = sell_qty * price
            print(f'[Bot] {symbol} satış tutarı min altında, {min_notional}$ seviyesine yükseltildi')

        # Satış sonrası kalan min tutarın altında kalıyorsa tamamını sat
        remaining_value = (total_qty - sell_qty) * price
        if remaining_value < min_notional or sell_qty > total_qty:
            sell_qty = round_step(total_qty, step)
            print(f'[Bot] {symbol} kalan bakiye min altında kalacak, tamamı satılıyor')

        qty = sell_qty
        if qty <= 0:
            return {'ok': False, 'error': 'Satılacak miktar hesaplanamadı'}

        order = client.order_market_sell(symbol=symbol, quantity=qty)
        pnl = (price - pos['avg_price']) * qty
        pos['qty'] = round(pos['qty'] - qty, 6)
        if pos['qty'] <= 0:
            del positions[symbol]
        else:
            positions[symbol] = pos
        save_positions(positions)
        trades = load_trades()
        trades.append({
            'type': 'sell', 'symbol': symbol, 'qty': qty,
            'price': price, 'pnl': round(pnl, 2),
            'source': source,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        save_trades(trades)
        send_telegram(f'✅ <b>SATIM</b> [{source}]\nCoin: {symbol}\nFiyat: ${price}\nMiktar: {qty}\nKâr/Zarar: ${pnl}\nPeriyot: {period}')
        return {'ok': True, 'qty': qty, 'price': price, 'pnl': round(pnl, 2)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}



def send_telegram(msg):
    try:
        cfg = load_config()
        token   = cfg.get('telegram_token', '')
        chat_id = cfg.get('telegram_chat_id', '')
        if not token or not chat_id:
            return
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        data = urllib.parse.urlencode({
            'chat_id': chat_id,
            'text': msg,
            'parse_mode': 'HTML'
        }).encode()
        urllib.request.urlopen(url, data, timeout=5)
    except Exception as e:
        print('Telegram hata:', e)
