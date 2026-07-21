package com.wizaicorp.namazvakitleri.api

import com.google.gson.annotations.SerializedName
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Query
import java.time.LocalDate

interface PexelsService {
    @GET("v1/search")
    suspend fun search(
        @Header("Authorization") apiKey: String,
        @Query("query") query: String,
        @Query("per_page") perPage: Int = 15,
        @Query("page") page: Int = 1,
        @Query("orientation") orientation: String = "landscape"
    ): PexelsResponse
}

data class PexelsResponse(val photos: List<PexelsPhoto>)
data class PexelsPhoto(val src: PexelsSrc, val photographer: String)
data class PexelsSrc(
    @SerializedName("large") val large: String,
    @SerializedName("medium") val medium: String
)

object PexelsApi {
    private val service: PexelsService by lazy {
        Retrofit.Builder()
            .baseUrl("https://api.pexels.com/")
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(PexelsService::class.java)
    }

    private val queries = listOf(
        "mosque", "islamic architecture", "kaaba mecca", "masjid",
        "islamic art", "quran", "mosque sunset", "minaret"
    )

    /** Gunun dini gorseli - gune gore deterministik secilir. */
    suspend fun photoOfToday(apiKey: String): PexelsPhoto? {
        val doy = LocalDate.now().dayOfYear
        val query = queries[doy % queries.size]
        val resp = service.search("$apiKey", query, perPage = 15, page = 1 + (doy % 3))
        if (resp.photos.isEmpty()) return null
        return resp.photos[doy % resp.photos.size]
    }
}
