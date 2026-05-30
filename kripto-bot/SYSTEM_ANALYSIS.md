# Kripto Bot — Sistem Analiz Belgesi
> Opus 4.8'e verilmek üzere hazırlanmıştır. Sistem hataları, riskler ve iyileştirme
> fırsatları için kapsamlı teknik analiz istenecektir.

---

## 1. Genel Bakış

Binance Spot üzerinde çalışan, birden fazla bağımsız ajan içeren otomatik kripto alım-satım botu.
Flask tabanlı web dashboard + Telegram bildirimleri. Testnet / gerçek hesap switch'i mevcut.

**Mevcut canlı performans (30 Mayıs 2026 itibarıyla):**
- Net PNL: -$1.03 (küçük toplam), bireysel ajan sonuçları aşağıda
- OTONOM: %100 kazanma, +$30.16 (3 işlem)
- EDGE: %25 kazanma, -$10.69 (4 işlem)
- BREAKOUT: %33.3 kazanma, -$22.04 (3 işlem, büyük unrealized kazanç var)
- INDICATOR-SMART: %100, +$3.93
- INDICATOR-UTBOT: %0, -$2.39

---

## 2. Dosya Yapısı

```
kripto-bot/
├── bot.py              (~553 satır)  — Ortak çekirdek: config/trades/positions I/O,
│                                        execute_buy, execute_sell, Binance client,
│                                        SL cooldown, dust cleanup, Telegram, ATR
├── app.py              (~1186 satır) — Flask web uygulaması, 36+ API endpoint
├── autonomous_agent.py (~768 satır)  — Otonom ajan (top-100 tarama)
├── edge_agent.py       (~927 satır)  — Edge ajan (funding/OI/sweep/CVD)
├── manager_agent.py    (~577 satır)  — CEO ajan (DeepSeek LLM)
├── breakout_agent.py   (~531 satır)  — Breakout ajan (momentum kırılım)
├── indicator_agent.py  (~452 satır)  — UT Bot indikatör ajanı
├── wyckoff_agent.py    (~487 satır)  — Wyckoff akümülasyon ajanı
├── telegram_bot.py     (~411 satır)  — Telegram polling + komut işleyici
├── signal_engine.py    (~373 satır)  — UT Bot sinyal hesaplama motoru
├── smart_strategy.py   (~101 satır)  — 4 faktörlü composite sinyal
├── seans_strategy.py   (~75 satır)   — Seans/saate göre alım-satım zamanlaması
├── trends_backtest.py  (~235 satır)  — Google Trends korelasyon analizi
└── templates/
    └── index.html      (~95KB)       — Tek sayfa web dashboard
```

**Çalışma zamanı veri dosyaları (Git'te yok, sunucuda kalır):**
```
config.json        — API keys, coin listesi, global ayarlar
positions.json     — Açık pozisyonlar
trades.json        — Tüm işlem geçmişi
agent_state.json   — Otonom ajan: blacklist, dinamik ağırlıklar, signal stats
edge_state.json    — Edge ajan: funding ağırlıkları, OI scan cache
breakout_state.json — Breakout ajan state
indicator_state.json — İndikatör ajan scan stats
ceo_state.json     — CEO ajan: son analiz zamanı, enabled agents, position_mult
tg_offset.json     — Telegram polling offset
```

---

## 3. Çekirdek Mekanizmalar (bot.py)

### 3.1 Thread Güvenliği

```python
_TRADE_LOCK = threading.Lock()
```

Tüm ajanlar (5 adet) bu tek global kilidi kullanır. `execute_buy` içindeki kritik bölge
(`positions.json` okuma → emir → yazma) bu kilit altında çalışır. Ancak kilit dışı
kalan bazı okumalar var (bakiye kontrolü, SL cooldown — aşağıda detay).

### 3.2 execute_buy Akışı

```
1. get_price()                           → fiyat al
2. load_config() → SL cooldown kontrolü → coin ayarı > global ayar > 3s default
3. ATR hesapla → TP/SL yüzdesi belirle
   - coin_cfg.auto_tp_sl=True → ATR*1.5 / ATR*3.0 (clamp: SL 1-5%, TP 2-10%)
   - coin_cfg yok (otonom) → ATR*1.5 / ATR*3.0 (clamp: SL 1.5-5%, TP 3-6%)
   - manuel/sabit → config'deki değerler
4. get_usdt_balance() → bakiye kontrolü   ← KİLİT DIŞINDA
5. _TRADE_LOCK alınır
6. load_positions() → pozisyon kontrolü
   - pos_value >= MIN_NOTIONAL → "zaten açık" hatası
   - 0 < pos_value < MIN_NOTIONAL → toz, sıfırla, devam et
7. open_count >= max_positions → "limit dolu" hatası
8. get_symbol_filters() → step, min_notional  ← API çağrısı kilit içinde
9. round_step(amount/price, step) → qty hesapla
10. client.order_market_buy() → Binance emri
11. positions.json güncelle, save
12. KİLİT BIRAKILIR
13. trades.json'a kaydet, Telegram gönder
```

**Kritik Gözlem:** Adım 4 (bakiye kontrolü) kilit DIŞINDA. İki ajan aynı anda
bakiye okuyabilir, ikisi de "yeterli" görür, ikisi de emir açabilir → bakiye eksiye düşebilir.
Adım 8 (get_symbol_filters) kilit İÇİNDE — her alımda Binance'e ekstra API çağrısı.

### 3.3 execute_sell Akışı

```python
# NOT: execute_sell'de _TRADE_LOCK YOK!
positions = load_positions()
...
client.order_market_sell(...)
save_positions(positions)
save_trades(trades)
```

**Kritik Gözlem:** `execute_sell` kilit kullanmıyor. Eş zamanlı iki satış emri
(örn. TP ve SL aynı anda tetiklenirse) aynı pozisyona çift satış yapabilir.

### 3.4 SL Cooldown Mekanizması

```python
def _is_sl_source(source: str) -> bool:
    s = source.upper()
    return 'STOP' in s or s.endswith(' SL') or ' SL ' in s

def _check_sl_cooldown(symbol, cooldown_hours=3):
    # trades.json'ı tersine tarar, son SL satışını bulur
    # elapsed >= cooldown_hours ise True döner (alım yapılabilir)
```

Öncelik: `coin_cfg.sl_cooldown_hours` > `cfg.sl_cooldown_hours` (global) > 3 saat default.
Ayarlar sayfasından değiştirilebilir. 0 = kapalı.

**Son düzeltilen bug:** Önceki kodda yalnızca `'STOP'` kelimesi aranıyordu; `'EDGE SL'`,
`'INDICATOR-X SL'` source'ları tespit edilmiyordu → cooldown hiç devreye girmiyordu.

### 3.5 Toz Pozisyon Temizliği

```python
def cleanup_dust_positions(client):
    # Her coin için: qty * current_price < MIN_NOTIONAL → sil
```

- Saatlik raporda otomatik çalışır (`autonomous_agent._send_report` başında)
- `/toztemizle` Telegram komutu ve web butonu da tetikler
- MIN_NOTIONAL = Binance'in gerçek eşiği (genellikle $5), $2 sabit değil

### 3.6 Pozisyon Boyutlama

İki farklı fonksiyon var — hangi ajan hangisini kullandığı tutarsız:

```python
# bot.py — yeni, genel
def position_size_by_score(equity, score, mult=1.0, lo_pct=0.01, hi_pct=0.03, min_usd=10.0):
    # skor 5→%1, 7.5→%2, 10→%3 (equity bazlı)

# autonomous_agent.py — eski, sadece otonom kullanıyor
def _position_size(balance, score, atr_pct, is_real, max_positions):
    # Kelly Criterion: risk/trade * balance / sl_tahmin
    # real modda %1, testnet'te %2 risk/işlem
    # max: balance*%5 (real) veya balance*%10 (testnet)
    # max per_slot: balance/max_positions * %30
```

Otonom ajan `_position_size` kullanıyor (kendi içinde tanımlı).
Breakout ajan `position_size_by_score` kullanıyor.
Edge ve Indicator ajanları `coin_cfg['usdt_amount']` sabit değer kullanıyor.

---

## 4. Ajanlar

### 4.1 Otonom Ajan (autonomous_agent.py)

**Strateji:** Top-100 USDT/hacim tarama, çoklu indikatör skorlama.

**Thread'ler:**
- `_monitor_loop`: Her 3 saniyede SL/TP/trailing kontrolü
- `_scan_loop`: Her 90 saniyede top-100 tarama
- `_hourly_loop`: Saatlik rapor (+ toz temizliği)
- `_daily_loop`: Günlük PNL özeti

**Sinyal Skoru (0-10):**
```
Trend (1h):     EMA20/50/100 pozisyon + ADX    → max 2.5 puan
Momentum:       RSI(1h+15m) + StochRSI + MACD  → max 3.0 puan
Hacim:          volume_ratio / 3.0, capped 1.0 → max 1.5 puan
Bollinger:      BB alt bandına yakınlık          → max 1.0 puan
Formasyon:      Bullish engulfing + hammer + VWAP→ max 1.5 puan
Piyasa rejimi:  BTC'ye göre BULL/SIDEWAYS/BEAR  → max 0.5 puan
```

**Alım eşiği:** Skor >= 6.2 (BULL) / 5.8 (SIDEWAYS) / alım yok (BEAR)

**Çıkış:**
- Trailing stop: TP'nin %40'ında aktif, peak'ten `sl*0.70` düştüğünde çıkar
- TP: `change >= tp_pct`
- SL: `change <= -sl_pct`
- Momentum çıkışı: RSI>70 + MACD olumsuz → erken çıkış

**State (agent_state.json):**
- `blacklist`: Son SL'den itibaren 8s veya TP'den 2s beklenen semboller
- `weights`: Dinamik ağırlıklar (başarılı sinyal türüne göre artırılır)
- `signal_stats`: Sinyal türü başarı takibi

### 4.2 Edge Ajan (edge_agent.py)

**Strateji:** Geleneksel indikatör YOK. Piyasa mekaniği:

```
Funding Rate:   < -0.05% → shortlar sıkışıyor → long sinyali
OI + Fiyat:     OI artarken fiyat sabit → birikim var
Stop Sweep:     Önemli düşük seviyenin altına inip geri toparlama
CVD:            Fiyat yukarı ama gerçek satış ağırlığı → sahte hareket
Haberler:       CryptoPanic API (bearish/bullish skorlama)
Seans:          Asia / London / NY açılışlarına göre ağırlık
BTC Trend:      BTC yükselen trende → tüm sinyallere bonus
Yapısal Güç:    15m EMA/RSI kompozit
```

**Alım eşiği:** Toplam skor >= 4.5 (MIN_SCORE)

**TP/SL:** EDGE ATR bazlı veya sabit % (coin config'den)

**Çıkış (edge kendi izliyor):**
- ATR-tabanlı TP: `price >= tp_price`
- ATR-tabanlı SL: `price <= sl_price` → `source='EDGE SL'`
- Trailing: `source='EDGE TRAIL'`
- Funding exit: funding pozitife döndüğünde
- Zaman aşımı: 12 saat

**State (edge_state.json):**
- `funding_weights`: Hangi funding seviyesinin başarılı olduğu
- `scan_count`, `win_count`, `loss_count`

### 4.3 Breakout Ajan (breakout_agent.py)

**Strateji:** Tüm spot USDT çiftlerini tara, momentum kırılım yakala.

**Alım kriteri:**
```python
MIN_PRICE_CHG_2H = 4.0   # son 2s fiyat >= %4 hareket
MIN_VOL_SPIKE    = 2.0   # son 2s hacim >= saatlik ort. 2x
MIN_VOL_24H      = 500_000  # $500K likidite filtresi
MAX_BREAKOUT_POS = 3     # aynı anda max 3 breakout pozisyon
```

**Çıkış — Kademeli Trailing (TP yok):**
```
Hard stop:    -%5       → anında çık
+%3'te aktif: peak-%3  (küçük kârı kilitle)
+%10-25:      peak-%8  (orta)
+%25+:        peak-%15 (büyük trendi sür)
```

**Güçlü yön:** HEIUSDT +141%, ALLOUSDT +113% gibi büyük hareketleri yakalar.
**Zayıf yön:** Sahte kırılımlarda (pump-dump) tam -%5 yiyebilir.

### 4.4 İndikatör Ajan (indicator_agent.py)

**İki mod:**
- `UTBOT`: UT Bot sinyali (SuperTrend + ATR bazlı)
- `SMART`: 4 faktörlü composite (trend + momentum + hacim + pattern)

**Pozisyon yönetimi:**
```
TP hit → sat
SL hit → sat + _add_bl(sym, 6)  # 6s blacklist
Trail: TP'nin %50'sinde aktif, peak'ten -%3 düşünce çık
Smart sell: check_smart_sell() → 'sell' sinyali → çık
Timeout: 36 saat
```

**Config:** Her coin için manual `ut_key`, `ut_atr`, `ut_mode`, `signal_source`

### 4.5 CEO Ajan (manager_agent.py)

**Rol:** Risk yöneticisi (bireysel pozisyona dokunmaz).

**DeepSeek function calling:**
```python
TOOLS = [
    set_agent_enabled(agent, enabled),   # batan ajanı kapat
    set_position_mult(value),             # 0.3-1.5, bear'de küçült
]
```

**Her N saatte bir:**
1. Son N saatin işlemlerini + piyasa rejimini DeepSeek'e gönderir
2. Model tool call yaparak ajanları enable/disable eder veya pozisyon boyutunu değiştirir
3. Telegram'a CEO analiz özeti gönderir

**Bağımlılık:** DeepSeek API key zorunlu. Key yoksa çalışmaz ama hata vermez.

### 4.6 Wyckoff Ajan (wyckoff_agent.py)

**Strateji:** Wyckoff akümülasyon yapısı — daralan bant + fake pump sonrası giriş.
MAX_POS = 3. 4 saatlik tarama aralığı.

---

## 5. Config Yapısı

### 5.1 Global config.json

```json
{
  "testnet": true,
  "api_key": "...",
  "api_secret": "...",
  "real_api_key": "...",
  "real_api_secret": "...",
  "telegram_token": "...",
  "telegram_chat_id": "...",
  "webhook_secret": "secret123",
  "check_interval": 45,
  "max_positions": 6,
  "sl_cooldown_hours": 3,
  "report_interval_hours": 1,
  "deepseek_api_key": "...",
  "ceo_interval_hours": 1,
  "ceo_agent_enabled": true,
  "coins": [...]
}
```

### 5.2 Coin config (coins[] içinde her eleman)

```json
{
  "symbol": "BTCUSDT",
  "usdt_amount": 50,
  "period": "1h",
  "signal_source": "UTBOT",
  "ut_key": 1,
  "ut_atr": 1,
  "ut_mode": "close",
  "take_profit_pct": 3.0,
  "stop_loss_pct": 1.5,
  "auto_tp_sl": false,
  "min_tp_pct": 0,
  "sl_cooldown_hours": 4,
  "btc_filter": true,
  "seans_strategy": "disabled",
  "smart_min_score": 6.0,
  "enabled": true,
  "agent": "INDICATOR"
}
```

---

## 6. TP/SL İzleme Mimarisi

**Önemli:** Her ajan kendi pozisyonlarını kendi thread'inde izliyor. Merkezi bir izleme yok.

```
Otonom:    _monitor_loop (3s) → _exit_decision() → execute_sell
Edge:      _monitor_loop (5s) → ATR/funding check → execute_sell
Indicator: _monitor_loop (90s) → TP/SL/trail/smart check → execute_sell
Breakout:  _monitor_loop (5s) → trail/hard_stop check → execute_sell
Wyckoff:   kendi loop'u
```

**execute_sell'de kilit YOK.** İki ajan aynı pozisyona aynı anda
`execute_sell` çağırırsa çift satış riski var.

Ayrıca Otonom ajan yalnızca `agent='OTONOM'` olan pozisyonları izliyor.
Edge ajan yalnızca `agent='EDGE'` olanları. Ancak `positions.json` paylaşılıyor —
bir ajan başka ajanın açtığı pozisyonu yanlışlıkla kapatabilir mi?

---

## 7. Veri Akışı ve Race Condition Analizi

### Bilinen Güvenli Noktalar
- `execute_buy` → `_TRADE_LOCK` içinde çalışıyor ✓
- Çift alım aynı coinde: MIN_NOTIONAL kontrolü ✓
- Slot sayımı: tozlar sayılmıyor ✓

### Şüpheli / Riskli Noktalar

1. **execute_sell kilitlenmemiş:**
   - Otonom _monitor + Edge _monitor aynı anda farklı pozisyonlara satış yapabilir
   - Otonom TP + Edge trailing aynı pozisyon için (eğer ikisi de aynı coini takip ediyorsa)

2. **Bakiye kontrolü kilit dışında (execute_buy satır ~420):**
   ```python
   balance = get_usdt_balance(client)   # LOCK DIŞI
   if balance < usdt_amount: return error
   # ... başka kod...
   with _TRADE_LOCK:                    # LOCK İÇİ
       order = client.order_market_buy(...)
   ```
   İki ajan aynı anda bakiye okur, ikisi de "yeterli" görür, ikisi de alım yapar.

3. **trades.json kilitsiz yazılıyor:**
   `execute_buy` ve `execute_sell` sonunda `save_trades()` çağrılıyor,
   bu kilit DIŞINDA. Eş zamanlı iki işlem trades.json'ı bozabilir.

4. **Ajanın kendi pozisyonunu tanıması:**
   ```python
   if pos.get('agent') != 'OTONOM': continue   # Otonom sadece kendininkini izliyor
   ```
   Bu koruma sağlar ama şu soruyu doğurur: Eğer `agent` field'ı eksikse (eski pozisyon,
   manuel alım) kimse izlemiyor. O pozisyonda SL yenilirse kimse satmayacak.

5. **positions.json'daki `open_time` eksikliği:**
   `execute_buy` pozisyonu kaydederken `open_time` alanı YOK.
   Otonom ajan `_exit_decision` içinde `pos.get('open_time', ...)` kullanıyor
   ama bu alan hiç set edilmiyor → timeout çıkışı çalışmıyor olabilir.

---

## 8. API İstekleri ve Rate Limit

Her `execute_buy` çağrısı şu API çağrılarını yapıyor:
```
1. get_price()             → GET /api/v3/ticker/24hr (tek sembol)
2. load_config()           → dosya okuma (no API)
3. _calc_atr_pct()         → GET /api/v3/klines (1h, limit=12)
4. get_usdt_balance()      → GET /api/v3/account (ağır endpoint)
5. get_symbol_filters()    → GET /api/v3/exchangeInfo (sembol başına)
6. order_market_buy()      → POST /api/v3/order
```

Tarama döngülerinde:
- Otonom: Her 90s'de top-100 için `_klines(1h)` + `_klines(15m)` = 200 klines isteği
- Edge: Her 60s'de birden fazla futures endpoint (funding, OI, klines)
- Breakout: Her 600s'de tüm spot çiftleri

`get_symbol_filters()` her alımda `exchangeInfo` çekiyor — cache yok, her seferinde API isteği.

---

## 9. Hata Yönetimi Genel Durumu

Çoğu yerde bare `except: pass` veya `except Exception: return fallback` var:

```python
def get_fear_greed():
    try: ...
    except: return {'value': 0, 'label': 'N/A'}   # sessiz hata

def _calc_atr_pct(...):
    try: ...
    except: return None   # None döner, caller None kontrolü yapar mı?

def get_price(...):
    try: ...
    except: return 0.0    # 0.0 dönerse execute_buy "fiyat alınamadı" yakalamaz mı?
```

`execute_buy` içinde `get_price` 0.0 dönerse → "Fiyat alınamadı" hatası döner ✓
Ama `_calc_atr_pct` None dönerse ve caller kontrol etmezse → NoneType hatası olabilir.

---

## 10. Son Değişiklikler (bu session'da yapılan düzeltmeler)

### 10.1 SL Cooldown Bug Düzeltmesi
**Problem:** `_check_sl_cooldown` yalnızca `'STOP'` arıyordu. `'EDGE SL'` tespiti
yapılmıyordu → IOUSDT'de 2 dakika arayla iki kez SL yenildi.

**Düzeltme:** `_is_sl_source()` fonksiyonu eklendi:
```python
def _is_sl_source(source: str) -> bool:
    s = source.upper()
    return 'STOP' in s or s.endswith(' SL') or ' SL ' in s
```
OTONOM SL satışları artık `source='OTONOM SL'` ile kaydediliyor.
Cooldown default 4s → 3s. Global cooldown Ayarlar sayfasına eklendi.

### 10.2 Toz Pozisyon Temizliği Yeniden Yazıldı
**Problem:** `$2` sabit eşik kullanılıyordu; `execute_buy` toz pozisyonu sıfırlamazsa
avg_price bozuluyordu.

**Düzeltme:** `cleanup_dust_positions(client)` fonksiyonu Binance MIN_NOTIONAL kullanıyor.
`execute_buy` içinde toz tespit edilince pozisyon sıfırlanarak yeni avg hesaplanıyor.
Saatlik raporda otomatik çalışıyor.

---

## 11. Aktif Açık Pozisyonlar (30 Mayıs 2026)

| Sembol    | Değer    | Alış     | Güncel  | K/Z      | % | Ajan |
|-----------|----------|----------|---------|----------|---|------|
| HEIUSDT   | $263.06  | $0.127   | $0.170  | +$67.31  | +34.39% | BREAKOUT |
| BNBUSDT   | $144.70  | $644.08  | $666.83 | +$4.94   | +3.53%  | INDICATOR-UTBOT |
| DOGEUSDT  | $141.04  | $0.101   | $0.101  | +$1.11   | +0.8%   | INDICATOR-UTBOT |
| ALLOUSDT  | $113.35  | $0.257   | $0.259  | +$1.05   | +0.94%  | OTONOM |

---

## 12. Analiz İçin Soru Listesi

Sistem Opus 4.8'e aşağıdaki konularda analiz ettirilecektir:

1. **Güvenlik / Race Condition:**
   - `execute_sell`'e kilit eklenmeli mi? Eklenmezse hangi senaryolarda çift satış olur?
   - `trades.json` kilitsiz yazımı gerçek bir risk mi?
   - Bakiye kontrolünün kilit dışında olması ne kadar kritik?

2. **Pozisyon Boyutlama Tutarsızlığı:**
   - 3 farklı boyutlama mantığı var (Kelly/equity bazlı/sabit). Standartlaştırılmalı mı?

3. **`open_time` eksikliği:**
   - Zaman aşımı çıkışları çalışıyor mu? `execute_buy`'a `open_time` eklenmeli mi?

4. **`get_symbol_filters` cache'lenmeli mi?**
   - Her alımda `exchangeInfo` API çağrısı — performans/rate-limit riski var mı?

5. **Ajan izolasyonu:**
   - `agent` field'ı olmayan pozisyonlar sahipsiz mi? Bu nasıl ele alınmalı?

6. **ATR'nin `None` döndürmesi:**
   - Caller'lar düzgün kontrol yapıyor mu?

7. **Breakout ajanı:**
   - %4 pump sonrası alım → pump-dump riski nasıl azaltılır?
   - NOMUSDT'de -$15.11 → ardından yeniden alım paterni nasıl engellenir?

8. **Edge ajanı:**
   - Futures API'dan (fapi.binance.com) spot hesap için funding çekiyor — spot'ta
     funding arbitrajı anlamlı mı?
   - CryptoPanic API key olmadan haber skoru 0 → bu sinyali tamamen etkisiz kılıyor mu?

9. **CEO Ajanı:**
   - `set_position_mult` global etkili ama bazı ajanlar bunu okumayabilir — bu fonksiyon
     tüm ajanlara ulaşıyor mu?

10. **Genel:**
    - Hangi ajan kapatılmalı veya revize edilmeli?
    - Kritik eksik neler var?
