package com.bluechip.finance.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.URL

object SavingsPriceService {

    // 1 troy ons = 31.1035 gram
    private const val TROY_OZ_TO_GRAM = 31.1035

    // gold-api.com - XAU veya XAG icin USD/ons fiyati
    // Key gerektirmez, rate limit yok
    private fun fetchGoldApiUsdPerOz(symbol: String): Double {
        return try {
            val json = JSONObject(URL("https://api.gold-api.com/price/$symbol").readText())
            json.optDouble("price", 0.0)
        } catch (_: Exception) { 0.0 }
    }

    // TCMB XML'den doviz kuru parse et (sadece dovizler icin)
    private fun parseTcmbForex(xml: String, code: String): Double? {
        val match = Regex(
            "<Currency[^>]*CurrencyCode=\"$code\"[^>]*>.*?<ForexSelling>([0-9.]+)</ForexSelling>",
            RegexOption.DOT_MATCHES_ALL
        ).find(xml)
        return match?.groupValues?.get(1)?.toDoubleOrNull()
    }

    // Tum kayitlardaki asset fiyatlarini cek
    suspend fun fetchPrices(
        records: List<SavingsRecord>,
        fallbackUsdRate: Double = 32.5
    ): Map<String, Double> = withContext(Dispatchers.IO) {

        val prices = mutableMapOf<String, Double>()

        // 1. TCMB - USD kuru + dovizler
        var usdTry = fallbackUsdRate
        try {
            val tcmb = URL("https://www.tcmb.gov.tr/kurlar/today.xml").readText()
            parseTcmbForex(tcmb, "USD")?.let { usdTry = it }
            prices["USD"] = usdTry

            val dovizRecords = records.filter { it.category == SavingsCategory.DOVIZ }
            dovizRecords.map { it.assetId }.distinct().forEach { code ->
                parseTcmbForex(tcmb, code)?.let { prices[code] = it }
            }
        } catch (_: Exception) {
            prices["USD"] = usdTry
        }

        // 2. gold-api.com - Altin ve Gumus (USD/ons -> TL/gram)
        val hasGold   = records.any { it.category == SavingsCategory.METAL && it.assetId == "tether-gold" }
        val hasSilver = records.any { it.category == SavingsCategory.METAL && it.assetId == "silver" }

        if (hasGold) {
            val usdPerOz = fetchGoldApiUsdPerOz("XAU")
            if (usdPerOz > 0) prices["tether-gold"] = (usdPerOz / TROY_OZ_TO_GRAM) * usdTry
        }
        if (hasSilver) {
            val usdPerOz = fetchGoldApiUsdPerOz("XAG")
            if (usdPerOz > 0) prices["silver"] = (usdPerOz / TROY_OZ_TO_GRAM) * usdTry
        }

        // 3. CoinGecko - sadece CRYPTO
        val cryptoIds = records.filter { it.category == SavingsCategory.CRYPTO }.map { it.assetId }.distinct().filter { it.isNotBlank() }

        if (cryptoIds.isNotEmpty()) {
            try {
                val ids  = cryptoIds.joinToString(",")
                val url  = "https://api.coingecko.com/api/v3/simple/price?ids=$ids&vs_currencies=usd"
                val json = JSONObject(URL(url).readText())
                cryptoIds.forEach { id ->
                    val usd = json.optJSONObject(id)?.optDouble("usd", 0.0) ?: 0.0
                    if (usd > 0) prices[id] = usd * usdTry
                }
            } catch (_: Exception) { /* stale cache kullan */ }
        }

        prices
    }

    // Tek asset fiyat - coin/metal eklerken anlık fiyat goster
    suspend fun fetchSinglePrice(
        assetId: String,
        category: SavingsCategory,
        usdTry: Double
    ): Double = withContext(Dispatchers.IO) {
        try {
            when (category) {
                SavingsCategory.METAL -> {
                    val symbol = when (assetId) {
                        "tether-gold" -> "XAU"
                        "silver"      -> "XAG"
                        else          -> return@withContext 0.0
                    }
                    val usdPerOz = fetchGoldApiUsdPerOz(symbol)
                    if (usdPerOz <= 0) 0.0 else (usdPerOz / TROY_OZ_TO_GRAM) * usdTry
                }
                SavingsCategory.CRYPTO -> {
                    val url  = "https://api.coingecko.com/api/v3/simple/price?ids=$assetId&vs_currencies=usd"
                    val json = JSONObject(URL(url).readText())
                    val usd  = json.optJSONObject(assetId)?.optDouble("usd", 0.0) ?: 0.0
                    if (usd <= 0) 0.0 else usd * usdTry
                }
                SavingsCategory.DOVIZ -> {
                    val tcmb = URL("https://www.tcmb.gov.tr/kurlar/today.xml").readText()
                    parseTcmbForex(tcmb, assetId) ?: 0.0
                }
            }
        } catch (_: Exception) { 0.0 }
    }
}
