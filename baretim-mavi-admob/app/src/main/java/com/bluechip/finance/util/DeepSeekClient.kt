package com.bluechip.finance.util

import android.content.Context
import com.bluechip.finance.data.OvertimeManager
import com.bluechip.finance.data.PaymentManager
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.data.SavingsManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

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
        val savings       = SavingsManager(context).loadAll()

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
                val totalCost = savings.sumOf { it.totalCostTry() }
                savings.groupBy { it.category }.forEach { (cat, records) ->
                    appendLine("${cat.emoji} ${cat.label}:")
                    records.forEach { s ->
                        appendLine("  - ${s.assetName}: ${s.quantity} adet/birim (alis maliyeti: ${s.totalCostTry().toLong()} TL)")
                    }
                }
                appendLine("Toplam alis maliyeti: ${totalCost.toLong()} TL")
            }

            appendLine()
            appendLine("Kullanicinin finansal sorularini cevapla, tasarruf onerileri ver, harcama analizi yap.")
            appendLine("Turkiye calisma mevzuatini da biliyorsun: kidem, ihbar, yillik izin, fazla mesai, SGK vs.")
        }
    }

    suspend fun sendMessage(
        context: Context,
        history: List<ChatMessage>,
        userMessage: String
    ): Result<String> = withContext(Dispatchers.IO) {
        try {
            val messages = JSONArray()

            val sysMsgObj = JSONObject()
            sysMsgObj.put("role", "system")
            sysMsgObj.put("content", buildSystemPrompt(context))
            messages.put(sysMsgObj)

            history.takeLast(10).forEach { msg ->
                val obj = JSONObject()
                obj.put("role", msg.role)
                obj.put("content", msg.content)
                messages.put(obj)
            }

            val userObj = JSONObject()
            userObj.put("role", "user")
            userObj.put("content", userMessage)
            messages.put(userObj)

            val body = JSONObject()
            body.put("model", MODEL)
            body.put("messages", messages)
            body.put("max_tokens", 1024)
            body.put("temperature", 0.7)

            val apiKey = DeepSeekKeyManager.getKey(context)
            if (apiKey.isBlank()) return@withContext Result.failure(Exception("API_KEY_MISSING"))

            val url = URL(API_URL)
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Authorization", "Bearer $apiKey")
            conn.doOutput = true
            conn.connectTimeout = 30000
            conn.readTimeout = 60000

            conn.outputStream.use { it.write(body.toString().toByteArray()) }

            val responseCode = conn.responseCode
            val responseBody = if (responseCode == 200) {
                conn.inputStream.bufferedReader().readText()
            } else {
                conn.errorStream?.bufferedReader()?.readText() ?: "HTTP $responseCode"
            }

            if (responseCode != 200) {
                return@withContext Result.failure(Exception("API hatasi: $responseCode - $responseBody"))
            }

            val json = JSONObject(responseBody)
            val content = json
                .getJSONArray("choices")
                .getJSONObject(0)
                .getJSONObject("message")
                .getString("content")

            Result.success(content)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
