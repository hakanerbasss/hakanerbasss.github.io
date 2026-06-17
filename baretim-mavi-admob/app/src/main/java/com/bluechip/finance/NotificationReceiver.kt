package com.bluechip.finance

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.bluechip.finance.data.*
import java.util.Calendar

class NotificationReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            "android.intent.action.QUICKBOOT_POWERON" -> {
                // Telefon yeniden başlayınca alarmı yeniden kur
                NotificationScheduler.schedule(context)
                return
            }
        }
        // Alarm tetiklendi — bildirimleri gönder
        sendNotifications(context)
        // Yarın için yeniden kur
        NotificationScheduler.schedule(context)
    }

    companion object {
        const val CHANNEL_SALARY  = "ch_salary"
        const val CHANNEL_PAYMENT = "ch_payment"
        const val CHANNEL_INCOME  = "ch_income"
        const val CHANNEL_BACKUP  = "ch_backup"

        fun createChannels(context: Context) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            listOf(
                Triple(CHANNEL_SALARY,  "Maas ve Gelir Bildirimleri", NotificationManager.IMPORTANCE_DEFAULT),
                Triple(CHANNEL_PAYMENT, "Odeme Hatirlatici",          NotificationManager.IMPORTANCE_DEFAULT),
                Triple(CHANNEL_INCOME,  "Yan Gelir Bildirimleri",     NotificationManager.IMPORTANCE_LOW),
                Triple(CHANNEL_BACKUP,  "Yedekleme Hatirlatici",      NotificationManager.IMPORTANCE_DEFAULT)
            ).forEach { (id, name, imp) ->
                nm.createNotificationChannel(NotificationChannel(id, name, imp))
            }
        }

        fun sendNotifications(context: Context) {
            val settings = NotificationSettingsManager.get(context)
            val profile  = ProfileManager(context).load()
            val today    = Calendar.getInstance().get(Calendar.DAY_OF_MONTH)
            val nm       = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            var notifId  = 100

            fun send(title: String, body: String, channel: String) {
                val n = NotificationCompat.Builder(context, channel)
                    .setSmallIcon(android.R.drawable.ic_popup_reminder)
                    .setContentTitle(title)
                    .setContentText(body)
                    .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                    .setAutoCancel(true)
                    .build()
                nm.notify(notifId++, n)
            }

            // Maaş
            if (settings.salaryEnabled && profile.salaryDay > 0) {
                val diff = (profile.salaryDay - today).let { if (it < 0) it + 30 else it }
                if (diff == settings.salaryDaysBefore)
                    send("Maas Yaklasiyor!", "${settings.salaryDaysBefore} gun sonra maasiniz yatiyor.", CHANNEL_SALARY)
                else if (diff == 0)
                    send("Bugun Maas Gunu!", "Maasiniz bugun yatmali.", CHANNEL_SALARY)
            }

            // Avans
            if (settings.advanceEnabled && profile.advanceDay > 0) {
                val diff = (profile.advanceDay - today).let { if (it < 0) it + 30 else it }
                if (diff == settings.advanceDaysBefore)
                    send("Avans Yaklasiyor!", "${settings.advanceDaysBefore} gun sonra avansiniz yatiyor.", CHANNEL_SALARY)
                else if (diff == 0)
                    send("Bugun Avans Gunu!", "Avansiniz bugun yatmali.", CHANNEL_SALARY)
            }

            // Emekli maaşı
            if (settings.retirementEnabled && profile.isRetired && profile.retirementDay > 0) {
                val diff = (profile.retirementDay - today).let { if (it < 0) it + 30 else it }
                if (diff == settings.retirementDaysBefore)
                    send("Emekli Maasi Yaklasiyor!", "${settings.retirementDaysBefore} gun sonra emekli maasiniz yatiyor.", CHANNEL_SALARY)
                else if (diff == 0)
                    send("Bugun Emekli Maasi!", "Emekli maasiniz bugun yatmali.", CHANNEL_SALARY)
            }

            // Yan gelirler
            if (settings.sideIncomeEnabled) {
                profile.sideIncomes.forEach { side ->
                    if (side.dayOfMonth > 0) {
                        val diff = side.dayOfMonth - today
                        if (diff == settings.sideDaysBefore || diff == 0) {
                            val msg = if (diff == 0) "Bugun yatmali." else "${settings.sideDaysBefore} gun sonra yatiyor."
                            send("${side.label} Geliyor!", msg, CHANNEL_INCOME)
                        }
                    }
                }
            }

            // Yaklaşan ödemeler
            if (settings.paymentEnabled) {
                PaymentManager.getActivePayments(context).forEach { payment ->
                    val diff = payment.dueDayOfMonth - today
                    if (diff == settings.paymentDaysBefore || diff == 0) {
                        val msg = if (diff == 0) "Bugun son odeme gunu!" else "${settings.paymentDaysBefore} gun sonra odeme gunu."
                        send("${payment.name} Hatirlatici", msg, CHANNEL_PAYMENT)
                    }
                }
            }

            // Özel günler
            if (settings.specialDayEnabled) {
                SpecialDayManager.getAll(context).forEach { day ->
                    val diff = SpecialDayManager.daysUntil(day.day, day.month)
                    if (diff == settings.specialDaysBefore || diff == 0) {
                        val msg = if (diff == 0) "Bugun ${day.title}!" else "${settings.specialDaysBefore} gun sonra: ${day.title}"
                        val detail = if (day.subtitle.isNotEmpty()) day.subtitle else day.title
                        send(msg, detail, CHANNEL_INCOME)
                    }
                }
            }

            // Yedekleme hatirlatici
            if (settings.backupReminderEnabled) {
                val todayStr = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.getDefault()).format(java.util.Date())
                val prefs = context.getSharedPreferences("notif_settings", Context.MODE_PRIVATE)
                val lastBackup = prefs.getString(NotificationSettingsManager.KEY_LAST_BACKUP_DATE, "")
                if (lastBackup != todayStr) {
                    send("Yedekleme Hatirlatici", "Bugun yedekleme yapmadiniz. Verileriniz kaybolmasin!", CHANNEL_BACKUP)
                }
            }
        }
    }
}
