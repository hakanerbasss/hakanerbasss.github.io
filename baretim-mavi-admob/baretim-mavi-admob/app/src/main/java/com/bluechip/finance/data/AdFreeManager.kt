package com.bluechip.finance.data

import android.content.Context

object AdFreeManager {

    private const val PREFS = "ad_free_prefs"
    private const val KEY_UNTIL = "ad_free_until"
    private const val SEVEN_DAYS_MS  = 3L  * 24 * 60 * 60 * 1000
    private const val THIRTY_DAYS_MS = 30L * 24 * 60 * 60 * 1000

    fun isAdFree(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val until = prefs.getLong(KEY_UNTIL, 0L)
        return System.currentTimeMillis() < until
    }

    /** Her çağrıda mevcut süreye +7 gün ekler, max 30 gün. */
    fun activate(context: Context) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val now   = System.currentTimeMillis()
        val current = prefs.getLong(KEY_UNTIL, now)
        val base  = if (current > now) current else now          // süresi dolduysa bugünden başla
        val until = minOf(base + SEVEN_DAYS_MS, now + THIRTY_DAYS_MS)
        prefs.edit().putLong(KEY_UNTIL, until).apply()
    }

    fun remainingDays(context: Context): Int {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val until = prefs.getLong(KEY_UNTIL, 0L)
        val diff  = until - System.currentTimeMillis()
        return if (diff > 0) (diff / (24 * 60 * 60 * 1000)).toInt() + 1 else 0
    }
}
