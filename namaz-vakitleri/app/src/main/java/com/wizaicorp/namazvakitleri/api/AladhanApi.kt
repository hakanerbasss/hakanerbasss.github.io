package com.wizaicorp.namazvakitleri.api

import com.google.gson.annotations.SerializedName
import com.wizaicorp.namazvakitleri.data.PrayerTimes
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Query
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

interface AladhanService {
    @GET("v1/timingsByCity")
    suspend fun getTimes(
        @Query("city")    city: String,
        @Query("country") country: String = "Turkey",
        @Query("method")  method: Int = 13
    ): AladhanResponse
}

data class AladhanResponse(val data: AladhanData)
data class AladhanData(val timings: AladhanTimings, val date: AladhanDate)
data class AladhanTimings(
    @SerializedName("Fajr")    val fajr: String,
    @SerializedName("Sunrise") val sunrise: String,
    @SerializedName("Dhuhr")   val dhuhr: String,
    @SerializedName("Asr")     val asr: String,
    @SerializedName("Maghrib") val maghrib: String,
    @SerializedName("Isha")    val isha: String
)
data class AladhanDate(val readable: String)

object AladhanApi {
    private val service: AladhanService by lazy {
        Retrofit.Builder()
            .baseUrl("https://api.aladhan.com/")
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(AladhanService::class.java)
    }

    suspend fun getPrayerTimes(city: String, country: String = "Turkey"): PrayerTimes {
        val resp = service.getTimes(city, country)
        val t = resp.data.timings
        val today = SimpleDateFormat("d MMMM yyyy", Locale("tr")).format(Date())
        return PrayerTimes(
            imsak  = t.fajr.take(5),
            gunes  = t.sunrise.take(5),
            ogle   = t.dhuhr.take(5),
            ikindi = t.asr.take(5),
            aksam  = t.maghrib.take(5),
            yatsi  = t.isha.take(5),
            city   = city,
            date   = today
        )
    }
}
