package com.wizaicorp.namazvakitleri

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.wizaicorp.namazvakitleri.data.NotifPrefs

class PrayerAlarmReceiver : BroadcastReceiver() {
    companion object {
        const val EXTRA_NAME = "prayer_name"
        const val EXTRA_KEY  = "prayer_key"
        const val CHANNEL_ID = "namaz_vakitleri"
    }

    override fun onReceive(ctx: Context, intent: Intent) {
        val name = intent.getStringExtra(EXTRA_NAME) ?: return
        val key  = intent.getStringExtra(EXTRA_KEY)  ?: return
        if (!NotifPrefs.isEnabled(ctx, key)) return

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(CHANNEL_ID, "Namaz Vakitleri", NotificationManager.IMPORTANCE_HIGH)
            (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(ch)
        }

        val offset = NotifPrefs.getOffsetMin(ctx)
        val body = if (offset > 0) "$offset dakika sonra $name vakti." else "$name vakti girdi."

        val notif = NotificationCompat.Builder(ctx, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(name)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .build()

        (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .notify(key.hashCode(), notif)
    }
}
