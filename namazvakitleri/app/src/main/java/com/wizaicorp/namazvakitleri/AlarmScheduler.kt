package com.wizaicorp.namazvakitleri

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import com.wizaicorp.namazvakitleri.data.NotifPrefs
import com.wizaicorp.namazvakitleri.data.PrayerTimes
import java.util.Calendar

object AlarmScheduler {

    fun schedule(ctx: Context, times: PrayerTimes) {
        val am     = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val offset = NotifPrefs.getOffsetMin(ctx)

        listOf(
            "imsak"  to times.imsak,
            "gunes"  to times.gunes,
            "ogle"   to times.ogle,
            "ikindi" to times.ikindi,
            "aksam"  to times.aksam,
            "yatsi"  to times.yatsi
        ).forEach { (key, timeStr) ->
            val pi = pendingIntent(ctx, key)
            am.cancel(pi)
            if (!NotifPrefs.isEnabled(ctx, key)) return@forEach
            val ms = toMillis(timeStr, offset) ?: return@forEach
            if (ms <= System.currentTimeMillis()) return@forEach
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M)
                    am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, ms, pi)
                else
                    am.setExact(AlarmManager.RTC_WAKEUP, ms, pi)
            } catch (e: SecurityException) {
                am.set(AlarmManager.RTC_WAKEUP, ms, pi)
            }
        }
    }

    private fun pendingIntent(ctx: Context, key: String): PendingIntent {
        val labels = mapOf(
            "imsak" to "İmsak", "gunes" to "Güneş", "ogle" to "Öğle",
            "ikindi" to "İkindi", "aksam" to "Akşam", "yatsi" to "Yatsı"
        )
        val intent = Intent(ctx, PrayerAlarmReceiver::class.java)
            .putExtra(PrayerAlarmReceiver.EXTRA_KEY,  key)
            .putExtra(PrayerAlarmReceiver.EXTRA_NAME, labels[key] ?: key)
        return PendingIntent.getBroadcast(
            ctx, key.hashCode(), intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    private fun toMillis(timeStr: String, offsetMin: Int): Long? = try {
        val (h, m) = timeStr.split(":").map { it.toInt() }
        Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, h)
            set(Calendar.MINUTE, m - offsetMin)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }.timeInMillis
    } catch (e: Exception) { null }
}
