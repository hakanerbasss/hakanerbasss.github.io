package com.bluechip.finance.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import java.util.*
import java.util.concurrent.TimeUnit

data class PublicHoliday(
    val name: String,
    val localName: String,
    val day: Int,
    val month: Int,
    val year: Int
)

object HolidayManager {
    private const val PREFS     = "holidays_cache"
    private const val KEY_DATA  = "holidays_json"
    private const val KEY_YEAR  = "cache_year"
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    suspend fun getHolidays(context: Context): List<PublicHoliday> = withContext(Dispatchers.IO) {
        val year = Calendar.getInstance().get(Calendar.YEAR)
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val cachedYear = prefs.getInt(KEY_YEAR, 0)

        // Cache geçerliyse kullan
        if (cachedYear == year) {
            val json = prefs.getString(KEY_DATA, null)
            if (json != null) return@withContext parseHolidays(json)
        }

        // Nager.Date API'den çek
        try {
            val req = Request.Builder()
                .url("https://date.nager.at/api/v3/PublicHolidays/$year/TR")
                .build()
            val resp = client.newCall(req).execute()
            if (resp.isSuccessful) {
                val body = resp.body?.string() ?: return@withContext emptyList()
                prefs.edit()
                    .putString(KEY_DATA, body)
                    .putInt(KEY_YEAR, year)
                    .apply()
                return@withContext parseHolidays(body)
            }
        } catch (_: Exception) {}

        // Cache yoksa boş
        val oldJson = prefs.getString(KEY_DATA, null)
        if (oldJson != null) parseHolidays(oldJson) else emptyList()
    }

    private fun parseHolidays(json: String): List<PublicHoliday> {
        return try {
            val arr = JSONArray(json)
            (0 until arr.length()).mapNotNull { i ->
                val o = arr.getJSONObject(i)
                val date = o.optString("date", "") // "2025-01-01"
                val parts = date.split("-")
                if (parts.size != 3) return@mapNotNull null
                PublicHoliday(
                    name      = o.optString("name", ""),
                    localName = o.optString("localName", o.optString("name", "")),
                    day       = parts[2].toIntOrNull() ?: return@mapNotNull null,
                    month     = parts[1].toIntOrNull() ?: return@mapNotNull null,
                    year      = parts[0].toIntOrNull() ?: return@mapNotNull null
                )
            }
        } catch (_: Exception) { emptyList() }
    }

    fun daysUntil(day: Int, month: Int): Int {
        return SpecialDayManager.daysUntil(day, month)
    }

    fun getUpcoming(holidays: List<PublicHoliday>, withinDays: Int = 30): List<Pair<PublicHoliday, Int>> {
        return holidays
            .map { it to daysUntil(it.day, it.month) }
            .filter { it.second <= withinDays }
            .sortedBy { it.second }
    }
}
