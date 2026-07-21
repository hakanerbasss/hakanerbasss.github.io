package com.wizaicorp.namazvakitleri

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.NotifPrefs

class PrayerAlarmReceiver : BroadcastReceiver() {
    companion object {
        const val EXTRA_KEY    = "prayer_key"
        const val EXTRA_IS_PRE = "is_pre"
        const val CHANNEL_ID   = "namaz_vakitleri"
    }

    override fun onReceive(ctx: Context, intent: Intent) {
        val key   = intent.getStringExtra(EXTRA_KEY) ?: return
        val isPre = intent.getBooleanExtra(EXTRA_IS_PRE, false)
        if (!NotifPrefs.isEnabled(ctx, key)) return

        val name = NotifPrefs.labelOf(key)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(
                CHANNEL_ID, Lang.get("notif_channel"), NotificationManager.IMPORTANCE_HIGH
            )
            (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(ch)
        }

        val offset = NotifPrefs.getOffsetMin(ctx)
        val body = if (isPre) Lang.fmt("notif_pre", name, offset)
                   else Lang.fmt("notif_entered", name)

        val openIntent = Intent(ctx, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val contentPi = PendingIntent.getActivity(
            ctx, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notif = NotificationCompat.Builder(ctx, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(name)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(contentPi)
            .setAutoCancel(true)
            .build()

        (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .notify(key.hashCode() + if (isPre) 100000 else 0, notif)

        // Vakit degisti - widget'taki "siradaki vakit" guncellensin
        PrayerWidgetProvider.updateAll(ctx)
    }
}
