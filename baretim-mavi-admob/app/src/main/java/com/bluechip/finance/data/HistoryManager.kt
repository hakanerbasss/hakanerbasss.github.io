package com.bluechip.finance.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

data class HistoryEntry(
    val screenId: String,
    val timestamp: Long,
    val label: String,         // "Ocak — 40.000₺ brüt"
    val resultSummary: String, // "Net: 32.450₺"
    val salary: String         // Ana giris alani (geri yukleme icin)
)

object HistoryManager {

    private const val PREFS = "calc_history"
    private const val MAX   = 5

    fun save(context: Context, entry: HistoryEntry) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val key   = "history_${entry.screenId}"
        val arr   = load(context, entry.screenId).toMutableList()

        // Ayni maaş/label varsa guncelle, yoksa basa ekle
        arr.removeAll { it.label == entry.label }
        arr.add(0, entry)
        if (arr.size > MAX) arr.subList(MAX, arr.size).clear()

        val json = JSONArray()
        arr.forEach { e ->
            json.put(JSONObject().apply {
                put("screenId",      e.screenId)
                put("timestamp",     e.timestamp)
                put("label",         e.label)
                put("resultSummary", e.resultSummary)
                put("salary",        e.salary)
            })
        }
        prefs.edit().putString(key, json.toString()).apply()
    }

    fun load(context: Context, screenId: String): List<HistoryEntry> {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val raw   = prefs.getString("history_$screenId", null) ?: return emptyList()
        return try {
            val arr  = JSONArray(raw)
            val list = mutableListOf<HistoryEntry>()
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                list.add(HistoryEntry(
                    screenId      = o.getString("screenId"),
                    timestamp     = o.getLong("timestamp"),
                    label         = o.getString("label"),
                    resultSummary = o.getString("resultSummary"),
                    salary        = o.getString("salary")
                ))
            }
            list
        } catch (_: Exception) { emptyList() }
    }

    fun clear(context: Context, screenId: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().remove("history_$screenId").apply()
    }
}
