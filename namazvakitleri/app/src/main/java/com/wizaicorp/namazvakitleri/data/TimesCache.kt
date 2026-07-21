package com.wizaicorp.namazvakitleri.data

import android.content.Context
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/**
 * Gunluk vakitleri tarihe gore onbellege alir.
 * Cevrimdisi calisma, widget ve gece yarisi alarm kurulumu buradan beslenir.
 */
object TimesCache {

    private const val PREF = "times_cache"

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    fun isoToday(): String = isoOf(Calendar.getInstance())

    private fun isoOf(cal: Calendar): String = "%04d-%02d-%02d".format(
        cal.get(Calendar.YEAR), cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH)
    )

    fun isoOf(year: Int, month: Int, day: Int): String = "%04d-%02d-%02d".format(year, month, day)

    fun saveDay(ctx: Context, iso: String, t: PrayerTimes) {
        prefs(ctx).edit()
            .putString("d_$iso", listOf(t.imsak, t.gunes, t.ogle, t.ikindi, t.aksam, t.yatsi).joinToString("|"))
            .putString("city_display", t.city)
            .apply()
    }

    fun getDay(ctx: Context, iso: String): PrayerTimes? {
        val raw = prefs(ctx).getString("d_$iso", null) ?: return null
        val p = raw.split("|")
        if (p.size != 6) return null
        val city = prefs(ctx).getString("city_display", "") ?: ""
        val locale = if (Lang.code == "tr") Locale("tr") else Locale.ENGLISH
        val dateStr = SimpleDateFormat("d MMMM yyyy", locale).format(Date())
        return PrayerTimes(p[0], p[1], p[2], p[3], p[4], p[5], city, dateStr)
    }

    fun getToday(ctx: Context): PrayerTimes? = getDay(ctx, isoToday())

    /** Eski kayitlari temizle (30 gunden eski) */
    fun cleanup(ctx: Context) {
        val p = prefs(ctx)
        val cutoff = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, -30) }
        val cutoffIso = isoOf(cutoff)
        val editor = p.edit()
        p.all.keys.filter { it.startsWith("d_") && it.removePrefix("d_") < cutoffIso }
            .forEach { editor.remove(it) }
        editor.apply()
    }
}
