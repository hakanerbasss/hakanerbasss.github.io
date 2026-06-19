package com.bluechip.finance.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

data class HistoryEntry(
    val type: String,
    val label: String,
    val amount: Double,
    val timestamp: Long = System.currentTimeMillis()
)

object HistoryManager {
    private const val PREFS = "history_prefs"
    private const val KEY = "entries"
    private const val MAX = 100

    fun add(context: Context, entry: HistoryEntry) {
        val list = getAll(context).toMutableList()
        list.add(0, entry)
        if (list.size > MAX) list.removeAt(list.size - 1)
        val arr = JSONArray()
        list.forEach { e ->
            arr.put(JSONObject().apply {
                put("type", e.type)
                put("label", e.label)
                put("amount", e.amount)
                put("ts", e.timestamp)
            })
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY, arr.toString()).apply()
    }

    fun getAll(context: Context): List<HistoryEntry> {
        val json = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY, "[]") ?: "[]"
        val arr = JSONArray(json)
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            HistoryEntry(o.getString("type"), o.getString("label"), o.getDouble("amount"), o.getLong("ts"))
        }
    }

    fun clear(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().apply()
    }
}
