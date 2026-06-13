package com.bluechip.finance.util

import android.content.Context

object DeepSeekKeyManager {

    const val PREFS = "deepseek_prefs"
    private const val KEY = "api_key"

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun getKey(context: Context): String =
        prefs(context).getString(KEY, "") ?: ""

    fun saveKey(context: Context, apiKey: String) {
        prefs(context).edit().putString(KEY, apiKey.trim()).apply()
    }

    fun hasKey(context: Context): Boolean = getKey(context).isNotBlank()

    fun clearKey(context: Context) {
        prefs(context).edit().remove(KEY).apply()
    }
}
