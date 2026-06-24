package com.hakanerbasss.notificationreader

import android.content.Context

class AppPreferences(context: Context) {
    private val prefs = context.getSharedPreferences("app_prefs", Context.MODE_PRIVATE)

    fun isAppEnabled(packageName: String): Boolean =
        prefs.getBoolean("pkg_$packageName", false)

    fun setAppEnabled(packageName: String, enabled: Boolean) {
        prefs.edit().putBoolean("pkg_$packageName", enabled).apply()
    }
}
