package com.wizaicorp.namazvakitleri.api

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST

interface DeepSeekService {
    @POST("chat/completions")
    suspend fun chat(
        @Header("Authorization") auth: String,
        @Body body: DsRequest
    ): DsResponse
}

data class DsMessage(val role: String, val content: String)
data class DsRequest(
    val model: String = "deepseek-chat",
    val messages: List<DsMessage>,
    val temperature: Double = 0.7,
    val max_tokens: Int = 800
)
data class DsChoice(val message: DsMessage)
data class DsResponse(val choices: List<DsChoice>)

object DeepSeekApi {

    private const val SYSTEM_PROMPT =
        "You are a respectful Islamic knowledge assistant inside a prayer times app. " +
        "Answer questions about Islam: worship, prayer, fasting, Quran, duas, Islamic history and daily religious life. " +
        "Always answer in the same language the user writes in (Turkish or English). " +
        "Be concise, kind and accurate. " +
        "IMPORTANT: You do NOT issue fatwas or binding religious rulings. " +
        "For personal rulings, disputes, divorce, finance or health-related religious questions, " +
        "advise the user to consult their local mufti or official religious authority (e.g. Diyanet). " +
        "If you are not sure about something, say so honestly. " +
        "Politely decline questions unrelated to religion or general knowledge."

    private val service: DeepSeekService by lazy {
        Retrofit.Builder()
            .baseUrl("https://api.deepseek.com/")
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(DeepSeekService::class.java)
    }

    /** Soru sorar; onceki konusma da baglam olarak gonderilir. */
    suspend fun ask(apiKey: String, history: List<Pair<String, String>>, question: String): String {
        val messages = mutableListOf(DsMessage("system", SYSTEM_PROMPT))
        history.takeLast(6).forEach { (q, a) ->
            messages.add(DsMessage("user", q))
            messages.add(DsMessage("assistant", a))
        }
        messages.add(DsMessage("user", question))
        val resp = service.chat("Bearer $apiKey", DsRequest(messages = messages))
        return resp.choices.firstOrNull()?.message?.content?.trim() ?: ""
    }
}
