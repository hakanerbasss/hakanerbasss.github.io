package com.wizaicorp.namazvakitleri

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.wizaicorp.namazvakitleri.data.NotifPrefs
import com.wizaicorp.namazvakitleri.data.PrayerTimes
import com.wizaicorp.namazvakitleri.data.TimesCache
import java.util.Calendar

object AlarmScheduler {

    /** Onbellekteki bugunun vakitlerinden alarmlari kurar (arka plan icin). */
    fun scheduleFromCache(ctx: Context) {
        TimesCache.getToday(ctx)?.let { schedule(ctx, it) }
    }

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
            val piMain = pendingIntent(ctx, key, isPre = false)
            val piPre  = pendingIntent(ctx, key, isPre = true)
            am.cancel(piMain)
            am.cancel(piPre)
            if (!NotifPrefs.isEnabled(ctx, key)) return@forEach

            // Tam vakitte bildirim
            toMillis(timeStr, 0)?.let { ms ->
                if (ms > System.currentTimeMillis()) setExact(am, ms, piMain)
            }
            // Vakitten X dk once hatirlatma
            if (offset > 0) {
                toMillis(timeStr, offset)?.let { ms ->
                    if (ms > System.currentTimeMillis()) setExact(am, ms, piPre)
                }
            }
        }

        scheduleDailyRefresh(ctx)
        PrayerWidgetProvider.updateAll(ctx)
    }

    /** Her gece 00:05'te DailyReceiver'i uyandirip yeni gunun alarmlarini kurdurur. */
    fun scheduleDailyRefresh(ctx: Context) {
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val intent = Intent(ctx, DailyReceiver::class.java).setAction(DailyReceiver.ACTION_DAILY)
        val pi = PendingIntent.getBroadcast(
            ctx, 9001, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val next = Calendar.getInstance().apply {
            add(Calendar.DAY_OF_YEAR, 1)
            set(Calendar.HOUR_OF_DAY, 0)
            set(Calendar.MINUTE, 5)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        am.cancel(pi)
        setExact(am, next.timeInMillis, pi)
    }

    private fun setExact(am: AlarmManager, ms: Long, pi: PendingIntent) {
        try {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, ms, pi)
        } catch (e: SecurityException) {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, ms, pi)
        }
    }

    private fun pendingIntent(ctx: Context, key: String, isPre: Boolean): PendingIntent {
        val intent = Intent(ctx, PrayerAlarmReceiver::class.java)
            .putExtra(PrayerAlarmReceiver.EXTRA_KEY, key)
            .putExtra(PrayerAlarmReceiver.EXTRA_IS_PRE, isPre)
        val reqCode = key.hashCode() + if (isPre) 100000 else 0
        return PendingIntent.getBroadcast(
            ctx, reqCode, intent,
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
