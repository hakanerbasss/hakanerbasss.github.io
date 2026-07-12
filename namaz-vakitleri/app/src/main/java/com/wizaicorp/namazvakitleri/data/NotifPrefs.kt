package com.wizaicorp.namazvakitleri.data

import android.content.Context

object NotifPrefs {
    private const val PREF       = "notif_prefs"
    private const val KEY_OFFSET = "offset_min"

    val allPrayers = listOf(
        "imsak"  to "İmsak",
        "gunes"  to "Güneş",
        "ogle"   to "Öğle",
        "ikindi" to "İkindi",
        "aksam"  to "Akşam",
        "yatsi"  to "Yatsı"
    )

    fun isEnabled(ctx: Context, key: String): Boolean =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
            .getBoolean("enabled_$key", key != "gunes")

    fun setEnabled(ctx: Context, key: String, on: Boolean) =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putBoolean("enabled_$key", on).apply()

    fun getOffsetMin(ctx: Context): Int =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getInt(KEY_OFFSET, 0)

    fun setOffsetMin(ctx: Context, min: Int) =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putInt(KEY_OFFSET, min).apply()
}
