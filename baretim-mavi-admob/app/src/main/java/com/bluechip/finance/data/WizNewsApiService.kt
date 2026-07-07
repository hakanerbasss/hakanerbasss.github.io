package com.bluechip.finance.data

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Query

data class WizArticle(
    val id: Int,
    val title: String,
    val description: String?,
    val category: String?,
    val categoryColor: String?,
    val thumbnail: String?,
    val url: String,
    val createdAt: String?
)

fun WizArticle.toArticle() = Article(
    title = title,
    description = description,
    urlToImage = thumbnail,
    url = url
)

interface WizNewsApiService {
    @GET("api/haberler")
    suspend fun getHaberler(@Query("limit") limit: Int = 3): List<WizArticle>

    companion object {
        val instance: WizNewsApiService by lazy {
            Retrofit.Builder()
                .baseUrl("https://hakanerbas.wizaicorp.com/")
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(WizNewsApiService::class.java)
        }
    }
}
