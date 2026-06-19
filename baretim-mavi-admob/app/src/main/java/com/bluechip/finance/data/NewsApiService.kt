package com.bluechip.finance.data

import retrofit2.http.GET
import retrofit2.http.Query

data class NewsResponse(
    val status: String,
    val totalResults: Int,
    val articles: List<Article>
)

data class Article(
    val title: String,
    val description: String?,
    val url: String,
    val urlToImage: String?,
    val publishedAt: String,
    val source: Source
)

data class Source(
    val id: String?,
    val name: String
)

interface NewsApiService {
    @GET("v2/everything")
    suspend fun getNews(
        @Query("q") query: String,
        @Query("language") language: String = "tr",
        @Query("sortBy") sortBy: String = "publishedAt",
        @Query("pageSize") pageSize: Int = 20,
        @Query("apiKey") apiKey: String
    ): NewsResponse
}
