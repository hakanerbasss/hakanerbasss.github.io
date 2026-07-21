package com.wizaicorp.namazvakitleri.data

import android.content.Context

object NotifPrefs {
    private const val PREF       = "notif_prefs"
    private const val KEY_OFFSET = "offset_min"

    // (anahtar, Lang isim anahtari)
    val allPrayers = listOf(
        "imsak"  to "p_imsak",
        "gunes"  to "p_gunes",
        "ogle"   to "p_ogle",
        "ikindi" to "p_ikindi",
        "aksam"  to "p_aksam",
        "yatsi"  to "p_yatsi"
    )

    fun labelOf(key: String): String = Lang.get("p_$key")

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

    // Dini gun bildirimleri
    fun holyDaysEnabled(ctx: Context): Boolean =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getBoolean("holy_enabled", true)

    fun setHolyDaysEnabled(ctx: Context, on: Boolean) =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putBoolean("holy_enabled", on).apply()

    // Kaza hatirlatmasi
    fun kazaReminderEnabled(ctx: Context): Boolean =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getBoolean("kaza_enabled", true)

    fun setKazaReminderEnabled(ctx: Context, on: Boolean) =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putBoolean("kaza_enabled", on).apply()

    fun kazaHour(ctx: Context): Int =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getInt("kaza_hour", 21)

    fun setKazaHour(ctx: Context, h: Int) =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putInt("kaza_hour", h).apply()
}
