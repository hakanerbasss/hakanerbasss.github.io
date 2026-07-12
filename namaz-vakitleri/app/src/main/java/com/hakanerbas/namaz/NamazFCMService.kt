package com.hakanerbas.namaz

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.hakanerbas.namaz.data.CityManager

class NamazFCMService : FirebaseMessagingService() {

    override fun onMessageReceived(message: RemoteMessage) {
        val title = message.notification?.title ?: message.data["title"] ?: "Namaz Vakti"
        val body  = message.notification?.body  ?: message.data["body"]  ?: ""
        showNotification(title, body)
    }

    override fun onNewToken(token: String) {
        // Yeni token → kayıtlı şehir topic'ine yeniden abone ol
        val city = CityManager.getSelected(this)
        com.google.firebase.messaging.FirebaseMessaging.getInstance()
            .subscribeToTopic("namaz_${city.apiName.lowercase()}")
    }

    private fun showNotification(title: String, body: String) {
        val channelId = "namaz_vakitleri"
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val channel = NotificationChannel(channelId, "Namaz Vakitleri",
            NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Namaz vakti bildirimleri"
            enableVibration(true)
        }
        nm.createNotificationChannel(channel)

        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pending = PendingIntent.getActivity(this, 0, intent,
            PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_IMMUTABLE)

        val notification = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(android.R.drawable.ic_menu_recent_history)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pending)
            .build()

        nm.notify(System.currentTimeMillis().toInt(), notification)
    }
}
