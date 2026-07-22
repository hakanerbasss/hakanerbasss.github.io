package com.wizaicorp.namazvakitleri

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.wizaicorp.namazvakitleri.api.NewsRss
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.NotifPrefs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Periyodik olarak (AlarmScheduler.NEWS_CHECK_INTERVAL_MS araliklarla) dini
 * haberleri kontrol eder; en yeni haber daha once gorulmediyse bildirim gonderir.
 * Kendini her calismada yeniden zamanlar (self-chaining alarm).
 */
class NewsCheckReceiver : BroadcastReceiver() {

    companion object {
        const val CHANNEL_ID = "namaz_haber"
    }

    override fun onReceive(ctx: Context, intent: Intent) {
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                if (NotifPrefs.newsNotifEnabled(ctx)) {
                    val items = NewsRss.fetch()
                    val top = items.firstOrNull()
                    val lastLink = NotifPrefs.lastNewsLink(ctx)
                    if (top != null && top.link.isNotBlank() && top.link != lastLink) {
                        showNotification(ctx, top.title, top.source)
                        NotifPrefs.setLastNewsLink(ctx, top.link)
                    }
                }
            } catch (e: Exception) {
                // Ag hatasi - bir sonraki periyodik kontrolde tekrar denenir
            } finally {
                AlarmScheduler.scheduleNewsCheck(ctx)
                pending.finish()
            }
        }
    }

    private fun showNotification(ctx: Context, title: String, source: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(
                CHANNEL_ID, Lang.get("news"), NotificationManager.IMPORTANCE_DEFAULT
            )
            (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(ch)
        }

        val openIntent = Intent(ctx, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val contentPi = PendingIntent.getActivity(
            ctx, 9200, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val body = if (source.isNotBlank()) "$title — $source" else title

        val notif = NotificationCompat.Builder(ctx, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(Lang.get("news"))
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(contentPi)
            .setAutoCancel(true)
            .build()

        (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .notify(9200, notif)
    }
}
