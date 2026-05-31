package com.bluechip.finance

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.bluechip.finance.data.NotificationSettingsManager
import java.util.Calendar

object NotificationScheduler {

    private const val REQUEST_CODE = 1001

    fun schedule(context: Context) {
        val settings = NotificationSettingsManager.get(context)
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

        val intent = Intent(context, NotificationReceiver::class.java)
        val pi = PendingIntent.getBroadcast(
            context, REQUEST_CODE, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Bugün ayarlanan saate kadar geçtiyse yarın
        val cal = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, settings.hour)
            set(Calendar.MINUTE, settings.minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
            if (before(Calendar.getInstance())) add(Calendar.DAY_OF_YEAR, 1)
        }

        // Android 12+ izin kontrolü
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            if (am.canScheduleExactAlarms()) {
                am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, cal.timeInMillis, pi)
            } else {
                am.set(AlarmManager.RTC_WAKEUP, cal.timeInMillis, pi)
            }
        } else {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, cal.timeInMillis, pi)
        }
    }

    fun cancel(context: Context) {
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val intent = Intent(context, NotificationReceiver::class.java)
        val pi = PendingIntent.getBroadcast(
            context, REQUEST_CODE, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        am.cancel(pi)
    }

    fun scheduleTest(context: Context) {
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val intent = Intent(context, NotificationReceiver::class.java)
        val pi = PendingIntent.getBroadcast(
            context, REQUEST_CODE + 1, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        // 5 saniye sonra test
        am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,
            System.currentTimeMillis() + 5000, pi)
    }
}
