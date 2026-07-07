package com.bluechip.finance

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.bluechip.finance.data.NotificationSettingsManager
import com.bluechip.finance.data.WizNewsApiService
import java.util.concurrent.TimeUnit

/** Haber sitesinde yeni icerik dustukce bildirim gonderir (site + Instagram trafigi icin). */
class NewsNotificationWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        if (!NotificationSettingsManager.get(applicationContext).newsEnabled) return Result.success()

        return try {
            val articles = WizNewsApiService.instance.getHaberler(limit = 10)
            val prefs = applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            val lastSeenId = prefs.getInt(KEY_LAST_SEEN_ID, 0)

            if (lastSeenId == 0) {
                // Ilk calisma: gecmis haberleri "yeni" diye bildirmemek icin sadece baz al
                articles.maxOfOrNull { it.id }?.let {
                    prefs.edit().putInt(KEY_LAST_SEEN_ID, it).apply()
                }
                return Result.success()
            }

            val newOnes = articles.filter { it.id > lastSeenId }.sortedBy { it.id }
            if (newOnes.isNotEmpty()) {
                val nm = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                newOnes.takeLast(3).forEach { article ->
                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(article.url))
                    val pi = PendingIntent.getActivity(
                        applicationContext, article.id, intent,
                        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                    )
                    val n = NotificationCompat.Builder(applicationContext, NotificationReceiver.CHANNEL_NEWS)
                        .setSmallIcon(android.R.drawable.ic_popup_reminder)
                        .setContentTitle("📰 ${article.title}")
                        .setContentText("Detaylar icin dokun")
                        .setStyle(NotificationCompat.BigTextStyle().bigText(article.title))
                        .setAutoCancel(true)
                        .setContentIntent(pi)
                        .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                        .build()
                    nm.notify(NOTIF_ID_BASE + article.id, n)
                }
                prefs.edit().putInt(KEY_LAST_SEEN_ID, newOnes.maxOf { it.id }).apply()
            }
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }

    companion object {
        private const val PREFS = "notif_settings"
        private const val KEY_LAST_SEEN_ID = "last_seen_haber_id"
        private const val NOTIF_ID_BASE = 500
        private const val WORK_NAME = "news_check_worker"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<NewsNotificationWorker>(30, TimeUnit.MINUTES)
                .setConstraints(
                    Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
                )
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, request
            )
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
        }
    }
}
