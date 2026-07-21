package com.wizaicorp.namazvakitleri

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.wizaicorp.namazvakitleri.data.HolyDays
import com.wizaicorp.namazvakitleri.data.KazaPrefs
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.NotifPrefs
import com.wizaicorp.namazvakitleri.data.PrayerTimes
import com.wizaicorp.namazvakitleri.data.TimesCache
import java.time.LocalDate
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
        scheduleReminders(ctx)
        PrayerWidgetProvider.updateAll(ctx)
    }

    /** Dini gun ve kaza hatirlatma alarmlarini kurar (bugun icin). */
    fun scheduleReminders(ctx: Context) {
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager

        // Dini gunler: bugun etkinlikse 09:00, yarin etkinlikse bu aksam 20:00
        val piToday = reminderPi(ctx, 9101, "", "")
        val piEve   = reminderPi(ctx, 9102, "", "")
        am.cancel(piToday)
        am.cancel(piEve)
        if (NotifPrefs.holyDaysEnabled(ctx)) {
            val events = HolyDays.upcoming()
            val today = LocalDate.now()
            events.firstOrNull { it.date == today }?.let { e ->
                val name = Lang.get(e.nameKey)
                atHour(9, 0)?.let { ms ->
                    setExact(am, ms, reminderPi(ctx, 9101, name, Lang.fmt("holy_today_notif", name)))
                }
            }
            events.firstOrNull { it.date == today.plusDays(1) }?.let { e ->
                val name = Lang.get(e.nameKey)
                atHour(20, 0)?.let { ms ->
                    setExact(am, ms, reminderPi(ctx, 9102, name, Lang.fmt("holy_eve_notif", name)))
                }
            }
        }

        // Kaza hatirlatmasi: kayitli kaza varsa secilen saatte
        val piKaza = reminderPi(ctx, 9103, "", "")
        am.cancel(piKaza)
        if (NotifPrefs.kazaReminderEnabled(ctx) && KazaPrefs.totalAll(ctx) > 0) {
            atHour(NotifPrefs.kazaHour(ctx), 0)?.let { ms ->
                setExact(
                    am, ms,
                    reminderPi(
                        ctx, 9103,
                        Lang.get("kaza"),
                        "${Lang.get("kaza_left")}: ${KazaPrefs.summary(ctx)}"
                    )
                )
            }
        }
    }

    /** Bugun icin verilen saat; gecmisse null */
    private fun atHour(hour: Int, minute: Int): Long? {
        val ms = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, hour)
            set(Calendar.MINUTE, minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }.timeInMillis
        return if (ms > System.currentTimeMillis()) ms else null
    }

    private fun reminderPi(ctx: Context, reqCode: Int, title: String, body: String): PendingIntent {
        val intent = Intent(ctx, ReminderReceiver::class.java)
            .putExtra(ReminderReceiver.EXTRA_TITLE, title)
            .putExtra(ReminderReceiver.EXTRA_BODY, body)
            .putExtra(ReminderReceiver.EXTRA_ID, reqCode)
        return PendingIntent.getBroadcast(
            ctx, reqCode, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
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
