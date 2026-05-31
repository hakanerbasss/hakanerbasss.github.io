package com.bluechip.finance.data

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Query

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
        @Query("apiKey") apiKey: String = "bc7b44a1f4844c018557d4945800d61c"
    ): NewsResponse

    companion object {
        fun create(): NewsApiService {
            return Retrofit.Builder()
                .baseUrl("https://newsapi.org/")
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(NewsApiService::class.java)
        }
    }
}
