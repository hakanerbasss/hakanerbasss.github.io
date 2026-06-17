package com.bluechip.finance.data

import android.content.Context
import org.json.JSONObject
import java.io.InputStream
import java.io.OutputStream

object BackupManager {

    private val PREF_NAMES = listOf(
        "user_profile",
        "overtime_track_prefs",
        "payment_prefs",
        "savings_prefs",
        "special_days",
        "notif_settings",
        "deepseek_prefs",
        "ad_free_prefs",
        "calc_history",
        "custom_cryptos"
    )

    fun export(context: Context, out: OutputStream) {
        val root  = JSONObject()
        root.put("version", 1)
        root.put("timestamp", System.currentTimeMillis())
        val prefs = JSONObject()
        PREF_NAMES.forEach { name ->
            val sp  = context.getSharedPreferences(name, Context.MODE_PRIVATE)
            val obj = JSONObject()
            sp.all.forEach { (k, v) ->
                val entry = JSONObject()
                when (v) {
                    is Boolean -> { entry.put("t", "b"); entry.put("v", v.toString()) }
                    is Int     -> { entry.put("t", "i"); entry.put("v", v.toString()) }
                    is Long    -> { entry.put("t", "l"); entry.put("v", v.toString()) }
                    is Float   -> { entry.put("t", "f"); entry.put("v", v.toString()) }
                    else       -> { entry.put("t", "s"); entry.put("v", v?.toString() ?: "") }
                }
                obj.put(k, entry)
            }
            prefs.put(name, obj)
        }
        root.put("prefs", prefs)
        out.write(root.toString(2).toByteArray())
        out.flush()
        markBackupDone(context)
    }

    /** export() ile aynı ama markBackupDone() çağırmaz — sadece okuma amaçlı. */
    fun exportForRead(context: Context, out: OutputStream) {
        val root  = JSONObject()
        root.put("version", 1)
        root.put("timestamp", System.currentTimeMillis())
        val prefs = JSONObject()
        PREF_NAMES.forEach { name ->
            val sp  = context.getSharedPreferences(name, Context.MODE_PRIVATE)
            val obj = JSONObject()
            sp.all.forEach { (k, v) ->
                val entry = JSONObject()
                when (v) {
                    is Boolean -> { entry.put("t", "b"); entry.put("v", v.toString()) }
                    is Int     -> { entry.put("t", "i"); entry.put("v", v.toString()) }
                    is Long    -> { entry.put("t", "l"); entry.put("v", v.toString()) }
                    is Float   -> { entry.put("t", "f"); entry.put("v", v.toString()) }
                    else       -> { entry.put("t", "s"); entry.put("v", v?.toString() ?: "") }
                }
                obj.put(k, entry)
            }
            prefs.put(name, obj)
        }
        root.put("prefs", prefs)
        out.write(root.toString(2).toByteArray())
        out.flush()
    }

    fun markBackupDone(context: Context) {
        val today = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.getDefault()).format(java.util.Date())
        context.getSharedPreferences("notif_settings", Context.MODE_PRIVATE).edit()
            .putString(NotificationSettingsManager.KEY_LAST_BACKUP_DATE, today).apply()
    }

    fun import(context: Context, input: InputStream): Boolean {
        return try {
            val root  = JSONObject(input.bufferedReader().readText())
            val prefs = root.getJSONObject("prefs")
            PREF_NAMES.forEach { name ->
                if (!prefs.has(name)) return@forEach
                val obj    = prefs.getJSONObject(name)
                val editor = context.getSharedPreferences(name, Context.MODE_PRIVATE).edit()
                obj.keys().forEach { key ->
                    val entry = obj.getJSONObject(key)
                    val v     = entry.getString("v")
                    when (entry.getString("t")) {
                        "b"  -> editor.putBoolean(key, v.toBoolean())
                        "i"  -> editor.putInt(key, v.toIntOrNull() ?: 0)
                        "l"  -> editor.putLong(key, v.toLongOrNull() ?: 0L)
                        "f"  -> editor.putFloat(key, v.toFloatOrNull() ?: 0f)
                        else -> editor.putString(key, v)
                    }
                }
                editor.apply()
            }
            true
        } catch (_: Exception) { false }
    }
}
