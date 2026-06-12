package com.bluechip.finance.util

import android.content.Context
import com.bluechip.finance.BuildConfig
import com.bluechip.finance.data.PaymentManager
import com.bluechip.finance.data.ProfileManager
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
        val profile  = ProfileManager(context).load()
        val payments = PaymentManager.getPayments(context).filter { it.isActive }
        val totalPayments = payments.sumOf { it.amount }

        return buildString {
            appendLine("Sen 'Baretim' adli Turkce konusan bir finansal asistansin.")
            appendLine("Kullanicinin tum uygulama verisine erisimin var.")
            appendLine("Her zaman Turkce yaz. Kisa ve ozetli cevaplar ver.")
            appendLine()
            appendLine("=== KULLANICI PROFILI ===")
            if (profile.name.isNotEmpty()) appendLine("Ad: ${profile.name}")
            if (profile.grossSalary > 0) appendLine("Brut Maas: ${profile.grossSalary.toLong()} TL")
            if (profile.netSalary > 0)   appendLine("Net Maas: ${profile.netSalary.toLong()} TL")
            val totalIncome = profile.totalIncome()
            if (totalIncome > 0) appendLine("Toplam Gelir: ${totalIncome.toLong()} TL (yan gelirler dahil)")
            appendLine()
            if (payments.isNotEmpty()) {
                appendLine("=== ODEME TAKIBI (aylik) ===")
                payments.forEach { p ->
                    appendLine("- ${p.name} (${p.category.label}): ${p.amount.toLong()} TL")
                }
                appendLine("Toplam aylik odeme: ${totalPayments.toLong()} TL")
                appendLine()
            }
            if (profile.netSalary > 0 && totalPayments > 0) {
                val remaining = profile.netSalary - totalPayments
                appendLine("Net maas sonrasi kalan: ${remaining.toLong()} TL")
                appendLine()
            }
            appendLine("Kullanicinin finansal sorularini cevapla, tasarruf onerileri ver, harcama analizi yap.")
            appendLine("Turkiye calisma mevzuatini da biliyorsun (kidem, ihbar, yillik izin, fazla mesai vs).")
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

            val url = URL(API_URL)
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Authorization", "Bearer ${BuildConfig.DEEPSEEK_API_KEY}")
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
