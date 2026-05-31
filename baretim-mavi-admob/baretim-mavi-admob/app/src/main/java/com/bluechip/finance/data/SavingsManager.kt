package com.bluechip.finance.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

// ── Kategoriler ───────────────────────────────────────────────────────
enum class SavingsCategory(val label: String, val emoji: String) {
    CRYPTO("Kripto",        "🪙"),
    METAL ("Degerli Metal", "🥇"),
    DOVIZ ("Doviz",         "💵")
}

// ── Bilinen coinler (CoinGecko ID -> label) ───────────────────────────
object KnownCoins {
    val list = listOf(
        "bitcoin"          to "BTC",
        "ethereum"         to "ETH",
        "solana"           to "SOL",
        "chainlink"        to "LINK",
        "celestia"         to "TIA",
        "render-token"     to "RENDER",
        "binancecoin"      to "BNB",
        "ripple"           to "XRP",
        "cardano"          to "ADA",
        "avalanche-2"      to "AVAX",
        "polkadot"         to "DOT",
        "matic-network"    to "MATIC",
        "uniswap"          to "UNI",
        "tron"             to "TRX",
        "litecoin"         to "LTC",
        "stellar"          to "XLM",
        "dogecoin"         to "DOGE",
        "shiba-inu"        to "SHIB",
        "cosmos"           to "ATOM",
        "near"             to "NEAR"
    )
    fun idOf(symbol: String) = list.firstOrNull { it.second.equals(symbol, ignoreCase = true) }?.first
    fun symbolOf(id: String) = list.firstOrNull { it.first == id }?.second ?: id.uppercase()
}

// ── Bilinen metaller ──────────────────────────────────────────────────
object KnownMetals {
    // CoinGecko ID -> label
    val list = listOf(
        "tether-gold"   to "Altın (gram)",
        "silver"        to "Gümüş (gram)"
    )
    fun idOf(label: String) = list.firstOrNull { it.second.equals(label, ignoreCase = true) }?.first
}

// ── Bilinen dovizler ──────────────────────────────────────────────────
object KnownCurrencies {
    // TCMB kodu -> label
    val list = listOf(
        "USD" to "Amerikan Dolari",
        "EUR" to "Euro",
        "GBP" to "Ingiliz Sterlini",
        "CHF" to "Isvicre Franci",
        "JPY" to "Japon Yeni",
        "SAR" to "Suudi Riyali",
        "AED" to "Birlesik Arap Emirlikleri Dirhemi",
        "CAD" to "Kanada Dolari",
        "AUD" to "Avustralya Dolari",
        "NOK" to "Norvec Kronu",
        "SEK" to "Isvec Kronu",
        "DKK" to "Danimarka Kronu",
        "KWD" to "Kuveyt Dinari",
        "RUB" to "Rus Rublesi"
    )
}

// ── Kayıt modeli ──────────────────────────────────────────────────────
data class SavingsRecord(
    val id:          String = UUID.randomUUID().toString(),
    val category:    SavingsCategory = SavingsCategory.CRYPTO,
    val assetId:     String = "",    // CoinGecko ID veya TCMB kodu
    val assetName:   String = "",    // Gosterim adi (BTC, Altin, USD...)
    val quantity:    Double = 0.0,   // Adet veya gram veya birim
    val buyPriceTry: Double = 0.0,   // Alim anindaki TL fiyati (birim basi)
    val buyDate:     Long   = System.currentTimeMillis(),
    val note:        String = ""
) {
    fun totalCostTry(): Double = quantity * buyPriceTry
}

// ── Fiyat cache modeli ────────────────────────────────────────────────
data class PriceCache(
    val prices:     Map<String, Double> = emptyMap(), // assetId -> TL fiyati
    val lastUpdate: Long = 0L
) {
    fun isStale(): Boolean = System.currentTimeMillis() - lastUpdate > 24 * 60 * 60 * 1000L
    fun priceOf(assetId: String): Double = prices[assetId] ?: 0.0
}

// ── SavingsManager ────────────────────────────────────────────────────
class SavingsManager(private val context: Context) {

    companion object {
        private const val PREFS       = "savings_prefs"
        private const val KEY_RECORDS = "savings_records"
        private const val KEY_PRICES  = "savings_prices"
        private const val KEY_UPDATE  = "savings_last_update"
    }

    private val prefs get() = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    // ── Kayıt CRUD ────────────────────────────────────────────────────

    fun loadAll(): List<SavingsRecord> {
        val json = prefs.getString(KEY_RECORDS, "[]") ?: "[]"
        return try {
            val arr = JSONArray(json)
            (0 until arr.length()).map { parseRecord(arr.getJSONObject(it)) }
        } catch (_: Exception) { emptyList() }
    }

    fun save(records: List<SavingsRecord>) {
        val arr = JSONArray()
        records.forEach { arr.put(toJson(it)) }
        prefs.edit().putString(KEY_RECORDS, arr.toString()).apply()
    }

    fun add(record: SavingsRecord) {
        val list = loadAll().toMutableList()
        list.add(record)
        save(list)
    }

    fun update(record: SavingsRecord) {
        val list = loadAll().map { if (it.id == record.id) record else it }
        save(list)
    }

    fun delete(id: String) {
        val list = loadAll().filter { it.id != id }
        save(list)
    }

    fun loadByCategory(cat: SavingsCategory) = loadAll().filter { it.category == cat }

    // ── Fiyat cache ───────────────────────────────────────────────────

    fun loadPriceCache(): PriceCache {
        val lastUpdate = prefs.getLong(KEY_UPDATE, 0L)
        val json       = prefs.getString(KEY_PRICES, "{}") ?: "{}"
        return try {
            val obj = JSONObject(json)
            val map = mutableMapOf<String, Double>()
            obj.keys().forEach { k -> map[k] = obj.getDouble(k) }
            PriceCache(map, lastUpdate)
        } catch (_: Exception) { PriceCache() }
    }

    fun savePriceCache(prices: Map<String, Double>) {
        val obj = JSONObject()
        prices.forEach { (k, v) -> obj.put(k, v) }
        prefs.edit()
            .putString(KEY_PRICES, obj.toString())
            .putLong(KEY_UPDATE, System.currentTimeMillis())
            .apply()
    }

    // ── Kar/zarar hesaplama ───────────────────────────────────────────

    fun currentValueTry(record: SavingsRecord, cache: PriceCache): Double {
        val price = cache.priceOf(record.assetId)
        if (price <= 0) return record.totalCostTry()
        return record.quantity * price
    }

    fun profitTry(record: SavingsRecord, cache: PriceCache): Double {
        return currentValueTry(record, cache) - record.totalCostTry()
    }

    fun profitPct(record: SavingsRecord, cache: PriceCache): Double {
        val cost = record.totalCostTry()
        if (cost <= 0) return 0.0
        return (profitTry(record, cache) / cost) * 100.0
    }

    fun totalValueTry(records: List<SavingsRecord>, cache: PriceCache): Double =
        records.sumOf { currentValueTry(it, cache) }

    fun totalCostTry(records: List<SavingsRecord>): Double =
        records.sumOf { it.totalCostTry() }

    fun totalProfitTry(records: List<SavingsRecord>, cache: PriceCache): Double =
        totalValueTry(records, cache) - totalCostTry(records)

    // ── JSON serialize/deserialize ────────────────────────────────────

    private fun toJson(r: SavingsRecord) = JSONObject().apply {
        put("id",          r.id)
        put("category",    r.category.name)
        put("assetId",     r.assetId)
        put("assetName",   r.assetName)
        put("quantity",    r.quantity)
        put("buyPriceTry", r.buyPriceTry)
        put("buyDate",     r.buyDate)
        put("note",        r.note)
    }

    private fun parseRecord(o: JSONObject) = SavingsRecord(
        id          = o.optString("id",        UUID.randomUUID().toString()),
        category    = try { SavingsCategory.valueOf(o.getString("category")) }
                      catch (_: Exception) { SavingsCategory.CRYPTO },
        assetId     = o.optString("assetId",     ""),
        assetName   = o.optString("assetName",   ""),
        quantity    = o.optDouble("quantity",    0.0),
        buyPriceTry = o.optDouble("buyPriceTry", 0.0),
        buyDate     = o.optLong("buyDate",       System.currentTimeMillis()),
        note        = o.optString("note",        "")
    )
}
