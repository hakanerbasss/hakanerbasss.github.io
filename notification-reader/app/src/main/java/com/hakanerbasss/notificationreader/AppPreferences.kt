package com.hakanerbasss.notificationreader

import android.content.Context

class AppPreferences(context: Context) {
    private val prefs = context.getSharedPreferences("app_prefs", Context.MODE_PRIVATE)

    fun isAppEnabled(packageName: String): Boolean =
        prefs.getBoolean("pkg_$packageName", false)

    fun setAppEnabled(packageName: String, enabled: Boolean) {
        prefs.edit().putBoolean("pkg_$packageName", enabled).apply()
    }

    fun isAnnounceApp(): Boolean = prefs.getBoolean("announce_app", true)
    fun setAnnounceApp(v: Boolean) { prefs.edit().putBoolean("announce_app", v).apply() }

    fun isAnnounceSender(): Boolean = prefs.getBoolean("announce_sender", true)
    fun setAnnounceSender(v: Boolean) { prefs.edit().putBoolean("announce_sender", v).apply() }

    fun isAnnounceNumber(): Boolean = prefs.getBoolean("announce_number", false)
    fun setAnnounceNumber(v: Boolean) { prefs.edit().putBoolean("announce_number", v).apply() }

    fun isReadAllMessages(): Boolean = prefs.getBoolean("read_all_msgs", false)
    fun setReadAllMessages(v: Boolean) { prefs.edit().putBoolean("read_all_msgs", v).apply() }
}
