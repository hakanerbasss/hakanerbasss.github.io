package com.wizaicorp.namazvakitleri.api

import com.google.gson.annotations.SerializedName
import com.wizaicorp.namazvakitleri.data.PrayerTimes
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Path
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

    @GET("v1/calendarByCity/{year}/{month}")
    suspend fun getCalendar(
        @Path("year")     year: Int,
        @Path("month")    month: Int,
        @Query("city")    city: String,
        @Query("country") country: String,
        @Query("method")  method: Int = 13
    ): AladhanCalendarResponse
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

// Calendar response data classes
data class AladhanCalendarResponse(val data: List<AladhanDayData>)
data class AladhanDayData(val timings: AladhanTimings, val date: AladhanFullDate)
data class AladhanFullDate(val readable: String, val gregorian: AladhanGregorian, val hijri: AladhanHijri)
data class AladhanGregorian(val day: String, val weekday: AladhanWeekday, val month: AladhanMonthInfo)
data class AladhanWeekday(val en: String)
data class AladhanMonthInfo(val en: String)
data class AladhanHijri(val day: String, val month: AladhanHijriMonth, val year: String)
data class AladhanHijriMonth(val en: String, val ar: String)

data class CalendarDayItem(
    val dayNum: Int,
    val weekdayTr: String,
    val hijriDate: String,
    val times: PrayerTimes
)

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

    suspend fun getMonthlyTimes(
        city: String,
        country: String,
        year: Int,
        month: Int
    ): List<CalendarDayItem> {
        val resp = service.getCalendar(year, month, city, country)
        val weekdayMap = mapOf(
            "Monday"    to "Pazartesi",
            "Tuesday"   to "Salı",
            "Wednesday" to "Çarşamba",
            "Thursday"  to "Perşembe",
            "Friday"    to "Cuma",
            "Saturday"  to "Cumartesi",
            "Sunday"    to "Pazar"
        )
        val hijriMonthMap = mapOf(
            "Muharram"  to "Muharrem",
            "Muḥarram" to "Muharrem",
            "Safar"     to "Safer",
            "Ṣafar" to "Safer",
            "Rajab"     to "Recep",
            "Ramadan"   to "Ramazan",
            "Ramaḏān" to "Ramazan",
            "Shawwal"   to "Şevval",
            "Shawwāl" to "Şevval"
        )
        return resp.data.map { day ->
            val t = day.timings
            val weekdayEn = day.date.gregorian.weekday.en
            val weekdayTr = weekdayMap[weekdayEn] ?: weekdayEn
            val hijriMonthEn = day.date.hijri.month.en
            val hijriMonthTr = hijriMonthMap[hijriMonthEn] ?: hijriMonthEn
            val hijriDate = "${day.date.hijri.day} $hijriMonthTr ${day.date.hijri.year}"
            CalendarDayItem(
                dayNum    = day.date.gregorian.day.toIntOrNull() ?: 0,
                weekdayTr = weekdayTr,
                hijriDate = hijriDate,
                times     = PrayerTimes(
                    imsak  = t.fajr.take(5),
                    gunes  = t.sunrise.take(5),
                    ogle   = t.dhuhr.take(5),
                    ikindi = t.asr.take(5),
                    aksam  = t.maghrib.take(5),
                    yatsi  = t.isha.take(5),
                    city   = city,
                    date   = day.date.readable
                )
            )
        }
    }
}
