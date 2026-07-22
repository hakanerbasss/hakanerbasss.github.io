package com.bluechip.finance

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.core.app.NotificationCompat
import com.bluechip.finance.data.NotificationSettingsManager
import com.bluechip.finance.data.WizNewsApiService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/** Haber sitesinde yeni icerik dustukce bildirim gonderir (site + Instagram trafigi icin). */
class NewsAlarmReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            "android.intent.action.QUICKBOOT_POWERON" -> {
                NewsAlarmScheduler.schedule(context)
                return
            }
        }
        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                checkAndNotify(context)
            } catch (_: Exception) {
                // sessizce gec, bir sonraki alarmda tekrar denenir
            } finally {
                NewsAlarmScheduler.schedule(context)
                pendingResult.finish()
            }
        }
    }

    private suspend fun checkAndNotify(context: Context) {
        if (!NotificationSettingsManager.get(context).newsEnabled) return

        val articles = WizNewsApiService.instance.getHaberler(limit = 10)
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val lastSeenId = prefs.getInt(KEY_LAST_SEEN_ID, 0)

        if (lastSeenId == 0) {
            // Ilk calisma: gecmis haberleri "yeni" diye bildirmemek icin sadece baz al
            articles.maxOfOrNull { it.id }?.let {
                prefs.edit().putInt(KEY_LAST_SEEN_ID, it).apply()
            }
            return
        }

        val newOnes = articles.filter { it.id > lastSeenId }.sortedBy { it.id }
        if (newOnes.isEmpty()) return

        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        newOnes.takeLast(3).forEach { article ->
            val viewIntent = Intent(Intent.ACTION_VIEW, Uri.parse(article.url))
            val pi = PendingIntent.getActivity(
                context, article.id, viewIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val bitmap = loadBitmap(article.thumbnail)
            val builder = NotificationCompat.Builder(context, NotificationReceiver.CHANNEL_NEWS)
                .setSmallIcon(android.R.drawable.ic_popup_reminder)
                .setContentTitle("📰 ${article.title}")
                .setContentText("Detaylar icin dokun")
                .setAutoCancel(true)
                .setContentIntent(pi)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)

            if (bitmap != null) {
                builder
                    .setLargeIcon(bitmap)
                    .setStyle(
                        NotificationCompat.BigPictureStyle()
                            .bigPicture(bitmap)
                            .bigLargeIcon(null as Bitmap?)
                            .setBigContentTitle("📰 ${article.title}")
                            .setSummaryText("Detaylar icin dokun")
                    )
            } else {
                builder.setStyle(NotificationCompat.BigTextStyle().bigText(article.title))
            }

            nm.notify(NOTIF_ID_BASE + article.id, builder.build())
        }
        prefs.edit().putInt(KEY_LAST_SEEN_ID, newOnes.maxOf { it.id }).apply()
    }

    private suspend fun loadBitmap(url: String?): Bitmap? {
        if (url.isNullOrEmpty()) return null
        return try {
            val conn = java.net.URL(url).openConnection()
            conn.connectTimeout = 5000
            conn.readTimeout = 5000
            val bytes = conn.getInputStream().use { it.readBytes() }

            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
            options.inSampleSize = calculateInSampleSize(options, MAX_BITMAP_DIMEN, MAX_BITMAP_DIMEN)
            options.inJustDecodeBounds = false

            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
        } catch (_: Exception) {
            null
        }
    }

    private fun calculateInSampleSize(options: BitmapFactory.Options, reqWidth: Int, reqHeight: Int): Int {
        val height = options.outHeight
        val width = options.outWidth
        var inSampleSize = 1
        if (height > reqHeight || width > reqWidth) {
            val halfHeight = height / 2
            val halfWidth = width / 2
            while (halfHeight / inSampleSize >= reqHeight && halfWidth / inSampleSize >= reqWidth) {
                inSampleSize *= 2
            }
        }
        return inSampleSize
    }

    companion object {
        private const val PREFS = "notif_settings"
        private const val KEY_LAST_SEEN_ID = "last_seen_haber_id"
        private const val NOTIF_ID_BASE = 500
        private const val MAX_BITMAP_DIMEN = 1024
    }
}
