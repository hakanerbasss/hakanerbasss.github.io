package com.wizaicorp.namazvakitleri.data

import android.content.Context

object KazaPrefs {
    private const val PREF = "kaza_prefs"

    // (anahtar, Lang isim anahtari)
    val prayers = listOf(
        "sabah"  to "p_sabah",
        "ogle"   to "p_ogle",
        "ikindi" to "p_ikindi",
        "aksam"  to "p_aksam",
        "yatsi"  to "p_yatsi",
        "vitir"  to "p_vitir"
    )

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    fun get(ctx: Context, key: String): Int = prefs(ctx).getInt("kaza_$key", 0)

    fun set(ctx: Context, key: String, v: Int) =
        prefs(ctx).edit().putInt("kaza_$key", v.coerceAtLeast(0)).apply()

    fun addDayToAll(ctx: Context) {
        val e = prefs(ctx).edit()
        prayers.forEach { (key, _) -> e.putInt("kaza_$key", get(ctx, key) + 1) }
        e.apply()
    }

    fun totalAll(ctx: Context): Int = prayers.sumOf { (key, _) -> get(ctx, key) }

    /** "Sabah 3, Öğle 2" gibi kisa ozet - sifir olanlar atlanir */
    fun summary(ctx: Context): String =
        prayers.mapNotNull { (key, nameKey) ->
            val c = get(ctx, key)
            if (c > 0) "${Lang.get(nameKey)} $c" else null
        }.joinToString(", ")
}
