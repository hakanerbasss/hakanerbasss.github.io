package com.bluechip.finance.data

import android.content.Context
import org.json.JSONObject
import java.io.InputStream
import java.io.OutputStream

object BackupManager {

    private val PREF_NAMES = listOf(
        "user_profile",
        "overtime_prefs",
        "payment_prefs",
        "savings_prefs",
        "notif_settings",
        "ad_free_prefs",
        "history_prefs",
        "overtime_track_prefs",
        "special_day_prefs"
    )

    fun export(context: Context, out: OutputStream) {
        val root = JSONObject()
        for (name in PREF_NAMES) {
            val prefs = context.getSharedPreferences(name, Context.MODE_PRIVATE)
            val obj = JSONObject()
            for ((k, v) in prefs.all) {
                when (v) {
                    is String  -> obj.put(k, v)
                    is Int     -> obj.put(k, v)
                    is Long    -> obj.put(k, v)
                    is Float   -> obj.put(k, v)
                    is Boolean -> obj.put(k, v)
                    is Set<*>  -> obj.put(k, org.json.JSONArray(v.toList()))
                }
            }
            root.put(name, obj)
        }
        out.write(root.toString(2).toByteArray(Charsets.UTF_8))
    }

    fun import(context: Context, inp: InputStream): Boolean {
        return try {
            val text = inp.bufferedReader().readText()
            val root = JSONObject(text)
            for (name in PREF_NAMES) {
                if (!root.has(name)) continue
                val obj = root.getJSONObject(name)
                val editor = context.getSharedPreferences(name, Context.MODE_PRIVATE).edit()
                editor.clear()
                for (k in obj.keys()) {
                    when (val v = obj.get(k)) {
                        is String  -> editor.putString(k, v)
                        is Int     -> editor.putInt(k, v)
                        is Long    -> editor.putLong(k, v)
                        is Double  -> editor.putFloat(k, v.toFloat())
                        is Boolean -> editor.putBoolean(k, v)
                        is org.json.JSONArray -> {
                            val set = mutableSetOf<String>()
                            for (i in 0 until v.length()) set.add(v.getString(i))
                            editor.putStringSet(k, set)
                        }
                    }
                }
                editor.apply()
            }
            true
        } catch (e: Exception) {
            false
        }
    }
}
