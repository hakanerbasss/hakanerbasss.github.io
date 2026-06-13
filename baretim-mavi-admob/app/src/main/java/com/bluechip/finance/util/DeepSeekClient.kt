package com.bluechip.finance.util

import android.content.Context
import com.bluechip.finance.data.OvertimeManager
import com.bluechip.finance.data.OvertimeRecord
import com.bluechip.finance.data.OvertimeTrackType
import com.bluechip.finance.data.Payment
import com.bluechip.finance.data.PaymentCategory
import com.bluechip.finance.data.PaymentManager
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.data.KnownCoins
import com.bluechip.finance.data.KnownCurrencies
import com.bluechip.finance.data.KnownMetals
import com.bluechip.finance.data.SavingsCategory
import com.bluechip.finance.data.SavingsManager
import com.bluechip.finance.data.SavingsRecord
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Locale

data class ChatMessage(val role: String, val content: String)

object DeepSeekClient {

    private const val API_URL = "https://api.deepseek.com/chat/completions"
    private const val MODEL   = "deepseek-chat"

    fun buildSystemPrompt(context: Context): String {
        val profile       = ProfileManager(context).load()
        val payments      = PaymentManager.getPayments(context).filter { it.isActive }
        val totalPayments = payments.sumOf { it.amount }
        val overtimeAll   = OvertimeManager.loadAll(context)
        val overtimeMonth = OvertimeManager.thisMonthRecords(context)
        val sm            = SavingsManager(context)
        val savings       = sm.loadAll()
        val priceCache    = sm.loadPriceCache()

        return buildString {
            appendLine("Sen 'Baretim' adli Turkce konusan bir finansal asistansin.")
            appendLine("Asagida kullanicinin TUM uygulama verileri verilmistir.")
            appendLine("Her zaman Turkce yaz. Kisa ve net cevaplar ver.")
            appendLine()

            // PROFIL
            appendLine("=== PROFIL ===")
            if (profile.name.isNotEmpty()) appendLine("Ad: ${profile.name}")
            if (profile.grossSalary > 0)   appendLine("Brut Maas: ${profile.grossSalary.toLong()} TL")
            if (profile.netSalary > 0)     appendLine("Net Maas: ${profile.netSalary.toLong()} TL")
            if (profile.salaryDay > 0)     appendLine("Maas Gunu: Ayin ${profile.salaryDay}. gunu")
            if (profile.advanceAmount > 0) appendLine("Avans: ${profile.advanceAmount.toLong()} TL (Ayin ${profile.advanceDay}.)")
            val totalIncome = profile.totalIncome()
            if (totalIncome > profile.netSalary && totalIncome > 0)
                appendLine("Toplam Gelir (yan gelirler dahil): ${totalIncome.toLong()} TL")

            // YAN GELİRLER
            if (profile.sideIncomes.isNotEmpty()) {
                appendLine()
                appendLine("=== YAN GELIRLER ===")
                profile.sideIncomes.forEach { si ->
                    appendLine("- ${si.label} (${si.category.label}): ~${si.effectiveAmount().toLong()} TL/ay")
                }
            }

            // ODEME TAKİBİ
            if (payments.isNotEmpty()) {
                appendLine()
                appendLine("=== AYLIK SABIT ODEMELER ===")
                payments.forEach { p ->
                    appendLine("- ${p.name} (${p.category.label}): ${p.amount.toLong()} TL")
                }
                appendLine("Toplam: ${totalPayments.toLong()} TL/ay")
                if (profile.netSalary > 0) {
                    val left = profile.netSalary - totalPayments
                    appendLine("Sabit odemeler sonrasi kalan: ${left.toLong()} TL")
                }
            }

            // FAZLA MESAİ
            if (overtimeAll.isNotEmpty()) {
                appendLine()
                appendLine("=== FAZLA MESAI ===")
                appendLine("Toplam kayit sayisi: ${overtimeAll.size}")
                val totalNet  = overtimeAll.sumOf { it.netAmount }
                val totalBrut = overtimeAll.sumOf { it.brutAmount }
                appendLine("Tum zamanlar toplam (net): ${totalNet.toLong()} TL")
                appendLine("Tum zamanlar toplam (brut): ${totalBrut.toLong()} TL")
                if (overtimeMonth.isNotEmpty()) {
                    val monthNet = overtimeMonth.sumOf { it.netAmount }
                    appendLine("Bu ay mesai (${overtimeMonth.size} kayit): ${monthNet.toLong()} TL net")
                    overtimeMonth.forEach { r ->
                        val tarih = java.text.SimpleDateFormat("dd.MM.yyyy", java.util.Locale.getDefault())
                            .format(java.util.Date(r.dateMillis))
                        appendLine("  $tarih — ${r.hours}s — ${r.netAmount.toLong()} TL net (${r.type.name})")
                    }
                }
            }

            // BİRİKİMLER
            if (savings.isNotEmpty()) {
                appendLine()
                appendLine("=== BIRIKIMLER ===")
                val hasPrices = !priceCache.isStale()
                var totalCost    = 0.0
                var totalCurrent = 0.0
                savings.groupBy { it.category }.forEach { (cat, records) ->
                    appendLine("${cat.emoji} ${cat.label}:")
                    records.forEach { s ->
                        val cost    = s.totalCostTry()
                        val curPrice = priceCache.priceOf(s.assetId)
                        val curVal  = if (curPrice > 0) s.quantity * curPrice else 0.0
                        totalCost    += cost
                        totalCurrent += curVal
                        val line = buildString {
                            append("  - ${s.assetName}: ${s.quantity} adet")
                            append(", alis: ${cost.toLong()} TL")
                            if (curVal > 0) {
                                val pnl = curVal - cost
                                val pct = if (cost > 0) pnl / cost * 100 else 0.0
                                append(", guncel deger: ${curVal.toLong()} TL")
                                append(", K/Z: ${if (pnl >= 0) "+" else ""}${pnl.toLong()} TL (${if (pct >= 0) "+" else ""}${"%.1f".format(pct)}%)")
                            }
                        }
                        appendLine(line)
                    }
                }
                appendLine("Toplam alis maliyeti: ${totalCost.toLong()} TL")
                if (totalCurrent > 0) {
                    val totalPnl = totalCurrent - totalCost
                    appendLine("Toplam guncel deger: ${totalCurrent.toLong()} TL")
                    appendLine("Toplam kar/zarar: ${if (totalPnl >= 0) "+" else ""}${totalPnl.toLong()} TL")
                }
                if (!hasPrices) appendLine("(Fiyat verisi eski veya yok — guncelleme icin Birikimler ekranini acin)")
            }

            appendLine()
            appendLine("Kullanicinin finansal sorularini cevapla, tasarruf onerileri ver, harcama analizi yap.")
            appendLine("Turkiye calisma mevzuatini da biliyorsun: kidem, ihbar, yillik izin, fazla mesai, SGK vs.")
        }
    }

    private fun toolDefinitions(): JSONArray {
        fun param(type: String, desc: String, enumVals: List<String>? = null) = JSONObject().apply {
            put("type", type); put("description", desc)
            if (enumVals != null) put("enum", JSONArray(enumVals))
        }
        fun tool(name: String, desc: String, props: JSONObject, required: List<String>) =
            JSONObject().apply {
                put("type", "function")
                put("function", JSONObject().apply {
                    put("name", name); put("description", desc)
                    put("parameters", JSONObject().apply {
                        put("type", "object"); put("properties", props)
                        put("required", JSONArray(required))
                    })
                })
            }

        return JSONArray().apply {
            put(tool("add_overtime",
                "Fazla mesai kaydı ekle. Kullanıcı mesai yaptığını söylediğinde çağır.",
                JSONObject().apply {
                    put("hours",  param("number", "Mesai saati (örn: 2, 1.5)"))
                    put("type",   param("string", "Mesai türü", listOf("PCT25","PCT50","PCT75","PCT100","PCT125","PCT200")))
                    put("date",   param("string", "Tarih YYYY-MM-DD formatında, bugünse today yaz"))
                    put("note",   param("string", "Opsiyonel not"))
                }, listOf("hours", "type")))

            put(tool("update_payment",
                "Mevcut ödemenin tutarını güncelle. Kullanıcı kira/fatura tutarının değiştiğini söylediğinde.",
                JSONObject().apply {
                    put("payment_name", param("string", "Ödeme adının bir kısmı (kira, elektrik, internet vb.)"))
                    put("new_amount",   param("number", "Yeni tutar TL"))
                }, listOf("payment_name", "new_amount")))

            put(tool("add_payment",
                "Yeni sabit ödeme/fatura ekle.",
                JSONObject().apply {
                    put("name",     param("string", "Ödeme adı"))
                    put("amount",   param("number", "Aylık tutar TL"))
                    put("category", param("string", "Kategori", listOf("KIRA","FATURA","KREDI","ABONELIK","SIGORTA","DIGER")))
                    put("due_day",  param("integer", "Ayın kaçında ödeniyor (1-31)"))
                }, listOf("name", "amount", "category")))

            put(tool("add_savings",
                "Birikime/portföye varlık ekle. Kullanıcı kripto/altın/döviz aldığını söylediğinde çağır.",
                JSONObject().apply {
                    put("asset_symbol", param("string", "Varlık sembolü: BTC, ETH, TIA, SOL, DOGE, ALTIN, USD, EUR vb."))
                    put("quantity",     param("number", "Miktar/adet"))
                    put("buy_price",    param("number", "Alış fiyatı (TL cinsinden, birim başına)"))
                    put("note",         param("string", "Opsiyonel not"))
                }, listOf("asset_symbol", "quantity", "buy_price")))

            put(tool("get_summary",
                "Bu ayın mali özetini hesapla: harcamalar, mesai kazancı, yan gelirler, kalan para.",
                JSONObject().apply {}, listOf()))
        }
    }

    private fun executeTool(context: Context, name: String, args: JSONObject): String {
        return try {
            when (name) {
                "add_overtime" -> {
                    val profile = ProfileManager(context).load()
                    val hours   = args.getDouble("hours")
                    val typeStr = args.optString("type", "PCT50")
                    val type    = try { OvertimeTrackType.valueOf(typeStr) } catch (_: Exception) { OvertimeTrackType.PCT50 }
                    val note    = args.optString("note", "")
                    val dateStr = args.optString("date", "today")
                    val dateMs  = if (dateStr == "today" || dateStr.isBlank()) {
                        System.currentTimeMillis()
                    } else {
                        try { SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).parse(dateStr)?.time ?: System.currentTimeMillis() }
                        catch (_: Exception) { System.currentTimeMillis() }
                    }
                    val brut = OvertimeManager.calcBrutAmount(profile.grossSalary, hours, type)
                    val net  = OvertimeManager.calcNetAmount(brut)
                    val record = OvertimeRecord(
                        dateMillis = dateMs, hours = hours, type = type,
                        brutAmount = brut, netAmount = net, note = note
                    )
                    OvertimeManager.add(context, record)
                    "BASARILI: ${hours}s ${type.label} mesai eklendi. Net kazanc: ${net.toLong()} TL, Brut: ${brut.toLong()} TL"
                }

                "update_payment" -> {
                    val keyword   = args.getString("payment_name").lowercase()
                    val newAmount = args.getDouble("new_amount")
                    val payments  = PaymentManager.getPayments(context)
                    val match     = payments.firstOrNull { it.name.lowercase().contains(keyword) }
                    if (match != null) {
                        PaymentManager.savePayment(context, match.copy(amount = newAmount))
                        "BASARILI: '${match.name}' odeme tutari ${newAmount.toLong()} TL olarak guncellendi."
                    } else {
                        "HATA: '${keyword}' adinda odeme bulunamadi. Mevcut odemeler: ${payments.map { it.name }}"
                    }
                }

                "add_payment" -> {
                    val name    = args.getString("name")
                    val amount  = args.getDouble("amount")
                    val catStr  = args.optString("category", "DIGER")
                    val cat     = try { PaymentCategory.valueOf(catStr) } catch (_: Exception) { PaymentCategory.DIGER }
                    val dueDay  = args.optInt("due_day", 1)
                    val payment = Payment(name = name, amount = amount, category = cat, dueDayOfMonth = dueDay)
                    PaymentManager.savePayment(context, payment)
                    "BASARILI: '${name}' odeme eklendi — ${amount.toLong()} TL/ay, her ayin ${dueDay}. gunu."
                }

                "add_savings" -> {
                    val symbol   = args.getString("asset_symbol").uppercase().trim()
                    val quantity = args.getDouble("quantity")
                    val buyPrice = args.getDouble("buy_price")
                    val note     = args.optString("note", "")

                    // Kategori ve assetId belirle
                    val coinId  = KnownCoins.idOf(symbol)
                    val metalId = KnownMetals.list.firstOrNull { it.second.contains(symbol, ignoreCase = true) }?.first
                    val currId  = KnownCurrencies.list.firstOrNull { it.first.equals(symbol, ignoreCase = true) }?.first

                    val (category, assetId, assetName) = when {
                        coinId  != null -> Triple(SavingsCategory.CRYPTO, coinId,  symbol)
                        metalId != null -> Triple(SavingsCategory.METAL,  metalId, symbol)
                        currId  != null -> Triple(SavingsCategory.DOVIZ,  currId,  KnownCurrencies.list.first { it.first == currId }.second)
                        symbol.contains("ALTIN", ignoreCase = true) || symbol.contains("GOLD", ignoreCase = true) ->
                            Triple(SavingsCategory.METAL, "tether-gold", "Altin (gram)")
                        else -> Triple(SavingsCategory.CRYPTO, symbol.lowercase(), symbol)
                    }

                    val record = SavingsRecord(
                        category = category, assetId = assetId,
                        assetName = assetName, quantity = quantity,
                        buyPriceTry = buyPrice, note = note
                    )
                    SavingsManager(context).add(record)
                    val totalCost = quantity * buyPrice
                    "BASARILI: ${quantity} adet ${assetName} eklendi. Alis maliyeti: ${totalCost.toLong()} TL (${buyPrice} TL/adet)"
                }

                "get_summary" -> {
                    val profile   = ProfileManager(context).load()
                    val payments  = PaymentManager.getPayments(context).filter { it.isActive }
                    val totalPay  = payments.sumOf { it.amount }
                    val otMonth   = OvertimeManager.thisMonthRecords(context)
                    val otNet     = otMonth.sumOf { it.netAmount }
                    val sideTotal = profile.sideIncomes.sumOf { it.currentMonthAmount() }
                    val cal       = java.util.Calendar.getInstance()
                    val today     = cal.get(java.util.Calendar.DAY_OF_MONTH)
                    val daysLeft  = if (profile.salaryDay > 0) {
                        val diff = profile.salaryDay - today
                        if (diff < 0) diff + 30 else diff
                    } else -1

                    buildString {
                        appendLine("Bu ayin ozeti:")
                        if (profile.netSalary > 0) appendLine("Net maas: ${profile.netSalary.toLong()} TL")
                        appendLine("Sabit odemeler: ${totalPay.toLong()} TL")
                        if (profile.netSalary > 0) appendLine("Sabit odemeler sonrasi kalan: ${(profile.netSalary - totalPay).toLong()} TL")
                        if (otNet > 0) appendLine("Bu ay mesai kazanci: ${otNet.toLong()} TL (${otMonth.size} kayit)")
                        if (sideTotal > 0) appendLine("Yan gelirler: ${sideTotal.toLong()} TL")
                        if (daysLeft >= 0) appendLine("Masaya ${daysLeft} gun kaldi.")
                    }
                }

                else -> "Bilinmeyen arac: $name"
            }
        } catch (e: Exception) { "Arac hatasi: ${e.message}" }
    }

    private fun callApi(apiKey: String, body: JSONObject): JSONObject {
        val conn = (URL(API_URL).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Authorization", "Bearer $apiKey")
            doOutput = true; connectTimeout = 30_000; readTimeout = 60_000
        }
        conn.outputStream.use { it.write(body.toString().toByteArray()) }
        val code = conn.responseCode
        val raw  = if (code == 200) conn.inputStream.bufferedReader().readText()
                   else conn.errorStream?.bufferedReader()?.readText() ?: "HTTP $code"
        if (code != 200) error("API hatasi $code: $raw")
        return JSONObject(raw)
    }

    suspend fun sendMessage(
        context: Context,
        history: List<ChatMessage>,
        userMessage: String
    ): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            val apiKey = DeepSeekKeyManager.getKey(context)
            if (apiKey.isBlank()) error("API_KEY_MISSING")

            val messages = JSONArray()
            messages.put(JSONObject().apply { put("role","system"); put("content", buildSystemPrompt(context)) })
            history.takeLast(10).forEach { msg ->
                messages.put(JSONObject().apply { put("role", msg.role); put("content", msg.content) })
            }
            messages.put(JSONObject().apply { put("role","user"); put("content", userMessage) })

            var body = JSONObject().apply {
                put("model", MODEL); put("messages", messages)
                put("max_tokens", 1024); put("temperature", 0.7)
                put("tools", toolDefinitions())
                put("tool_choice", "auto")
            }

            var response = callApi(apiKey, body)
            var choice   = response.getJSONArray("choices").getJSONObject(0)

            // Tool call loop — maks 3 tur
            repeat(3) {
                if (choice.optString("finish_reason") != "tool_calls") return@repeat
                val assistantMsg = choice.getJSONObject("message")
                messages.put(assistantMsg)

                val toolCalls = assistantMsg.getJSONArray("tool_calls")
                for (i in 0 until toolCalls.length()) {
                    val tc       = toolCalls.getJSONObject(i)
                    val toolId   = tc.getString("id")
                    val toolName = tc.getJSONObject("function").getString("name")
                    val toolArgs = JSONObject(tc.getJSONObject("function").getString("arguments"))
                    val result   = executeTool(context, toolName, toolArgs)
                    messages.put(JSONObject().apply {
                        put("role", "tool")
                        put("tool_call_id", toolId)
                        put("content", result)
                    })
                }

                body = JSONObject().apply {
                    put("model", MODEL); put("messages", messages)
                    put("max_tokens", 1024); put("temperature", 0.7)
                }
                response = callApi(apiKey, body)
                choice   = response.getJSONArray("choices").getJSONObject(0)
            }

            choice.getJSONObject("message").getString("content")
        }
    }
}
