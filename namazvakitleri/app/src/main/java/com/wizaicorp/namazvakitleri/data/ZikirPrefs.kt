package com.wizaicorp.namazvakitleri.data

import android.content.Context

object ZikirPrefs {
    private const val PREF = "zikir_prefs"

    val zikirKeys = listOf("z_1", "z_2", "z_3", "z_4", "z_5", "z_6")
    val targets = listOf(33, 99, 500, 1000, 0) // 0 = serbest

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    fun getCount(ctx: Context, zikirKey: String): Int = prefs(ctx).getInt("count_$zikirKey", 0)
    fun setCount(ctx: Context, zikirKey: String, v: Int) =
        prefs(ctx).edit().putInt("count_$zikirKey", v).apply()

    fun getTotal(ctx: Context): Long = prefs(ctx).getLong("total_all", 0L)
    fun addTotal(ctx: Context) =
        prefs(ctx).edit().putLong("total_all", getTotal(ctx) + 1).apply()

    fun getSelected(ctx: Context): Int = prefs(ctx).getInt("selected", 0)
    fun setSelected(ctx: Context, i: Int) = prefs(ctx).edit().putInt("selected", i).apply()

    fun getTarget(ctx: Context): Int = prefs(ctx).getInt("target", 33)
    fun setTarget(ctx: Context, t: Int) = prefs(ctx).edit().putInt("target", t).apply()
}
