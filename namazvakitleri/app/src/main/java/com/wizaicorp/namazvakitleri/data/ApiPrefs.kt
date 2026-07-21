package com.wizaicorp.namazvakitleri.data

import android.content.Context

/**
 * Kullanicinin kendi girdigi API anahtarlari (BYOK).
 * Sadece cihazda SharedPreferences'ta durur; hicbir yere gonderilmez.
 */
object ApiPrefs {
    private const val PREF = "api_prefs"

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    fun getPexelsKey(ctx: Context): String =
        prefs(ctx).getString("pexels_key", "")?.trim() ?: ""

    fun setPexelsKey(ctx: Context, key: String) =
        prefs(ctx).edit().putString("pexels_key", key.trim()).apply()

    fun getDeepSeekKey(ctx: Context): String =
        prefs(ctx).getString("deepseek_key", "")?.trim() ?: ""

    fun setDeepSeekKey(ctx: Context, key: String) =
        prefs(ctx).edit().putString("deepseek_key", key.trim()).apply()

    fun hasPexels(ctx: Context) = getPexelsKey(ctx).isNotBlank()
    fun hasDeepSeek(ctx: Context) = getDeepSeekKey(ctx).isNotBlank()
}
