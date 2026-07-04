package com.bluechip.finance.data

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Query
import com.bluechip.finance.BuildConfig

data class NewsResponse(val articles: List<Article>)
data class Article(
    val title: String,
    val description: String?,
    val urlToImage: String?,
    val url: String
)

interface NewsApiService {
    @GET("v2/everything")
    suspend fun getNews(
        @Query("q") query: String = "borsa OR ekonomi OR finans",
        @Query("language") language: String = "tr",
        @Query("sortBy") sortBy: String = "publishedAt",
        @Query("apiKey") apiKey: String = BuildConfig.NEWS_API_KEY
    ): NewsResponse

    companion object {
        val instance: NewsApiService by lazy {
            Retrofit.Builder()
                .baseUrl("https://newsapi.org/")
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(NewsApiService::class.java)
        }
        @Deprecated("Use NewsApiService.instance", ReplaceWith("NewsApiService.instance"))
        fun create(): NewsApiService = instance
    }
}
