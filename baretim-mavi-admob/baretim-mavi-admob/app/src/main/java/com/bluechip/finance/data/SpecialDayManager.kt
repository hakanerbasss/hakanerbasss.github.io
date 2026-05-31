package com.bluechip.finance.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.*

data class SpecialDay(
    val id: String = UUID.randomUUID().toString(),
    val title: String = "",        // "Doğum Günü", "Evlilik Yıldönümü" vb
    val subtitle: String = "",     // "Emel Ezgi Erbaş" vb
    val day: Int = 1,
    val month: Int = 1             // 1-12
)

object SpecialDayManager {
    private const val PREFS = "special_days"
    private const val KEY   = "days_json"

    fun getAll(context: Context): List<SpecialDay> {
        val json = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY, "[]") ?: "[]"
        val arr = JSONArray(json)
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            SpecialDay(
                id       = o.optString("id", UUID.randomUUID().toString()),
                title    = o.optString("title", ""),
                subtitle = o.optString("subtitle", ""),
                day      = o.optInt("day", 1),
                month    = o.optInt("month", 1)
            )
        }
    }

    fun save(context: Context, day: SpecialDay) {
        val list = getAll(context).toMutableList()
        val idx = list.indexOfFirst { it.id == day.id }
        if (idx >= 0) list[idx] = day else list.add(day)
        saveAll(context, list)
    }

    fun delete(context: Context, id: String) {
        saveAll(context, getAll(context).filter { it.id != id })
    }

    private fun saveAll(context: Context, list: List<SpecialDay>) {
        val arr = JSONArray()
        list.forEach { d ->
            arr.put(JSONObject().apply {
                put("id", d.id)
                put("title", d.title)
                put("subtitle", d.subtitle)
                put("day", d.day)
                put("month", d.month)
            })
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY, arr.toString()).apply()
    }

    // Bugünden itibaren kaç gün kaldı (yıllık tekrar)
    fun daysUntil(day: Int, month: Int): Int {
        val today = Calendar.getInstance()
        val todayDay = today.get(Calendar.DAY_OF_MONTH)
        val todayMonth = today.get(Calendar.MONTH) + 1
        // Bugün ise 0 döndür
        if (day == todayDay && month == todayMonth) return 0
        val target = Calendar.getInstance()
        target.set(Calendar.DAY_OF_MONTH, day)
        target.set(Calendar.MONTH, month - 1)
        target.set(Calendar.HOUR_OF_DAY, 0); target.set(Calendar.MINUTE, 0); target.set(Calendar.SECOND, 0); target.set(Calendar.MILLISECOND, 0)
        val now = Calendar.getInstance().also { it.set(Calendar.HOUR_OF_DAY, 0); it.set(Calendar.MINUTE, 0); it.set(Calendar.SECOND, 0); it.set(Calendar.MILLISECOND, 0) }
        if (target.before(now)) target.add(Calendar.YEAR, 1)
        return ((target.timeInMillis - now.timeInMillis) / 86400000).toInt()
    }

    fun getUpcoming(context: Context, withinDays: Int = 30): List<Pair<SpecialDay, Int>> {
        return getAll(context)
            .map { it to daysUntil(it.day, it.month) }
            .filter { it.second <= withinDays }
            .sortedBy { it.second }
    }
}
