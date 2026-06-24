package com.hakanerbasss.notificationreader

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.PowerManager
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.core.app.NotificationCompat
import java.util.Locale

class NotificationReaderService : NotificationListenerService() {

    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var wakeLock: PowerManager.WakeLock? = null
    private val prefs by lazy { AppPreferences(this) }

    companion object {
        private const val CHANNEL_ID = "notif_reader_fg"
        private const val FG_ID = 1001
        private const val WAKELOCK_TIMEOUT_MS = 30_000L
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        createChannel()
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(FG_ID, buildFgNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
            } else {
                startForeground(FG_ID, buildFgNotification())
            }
        } catch (_: Exception) {}
        initTts()
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        releaseTts()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (!ttsReady) return
        if (sbn.isOngoing) return
        if (!prefs.isAppEnabled(sbn.packageName)) return

        val extras = sbn.notification.extras
        val title = extras.getString(Notification.EXTRA_TITLE).orEmpty().trim()
        val text = extractText(extras)
        if (text.isBlank()) return

        val appName = getAppLabel(sbn.packageName)
        speak(buildUtterance(appName, title, text))
    }

    @Suppress("DEPRECATION")
    private fun extractText(extras: android.os.Bundle): String {
        val messages = extras.getParcelableArray(Notification.EXTRA_MESSAGES)
        if (messages != null && messages.isNotEmpty()) {
            val msgText = (messages.last() as? android.os.Bundle)
                ?.getCharSequence("text")?.toString().orEmpty().trim()
            if (msgText.isNotBlank()) return msgText
        }
        val text = extras.getString(Notification.EXTRA_TEXT).orEmpty().trim()
        if (text.isNotBlank()) return text
        return extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty().trim()
    }

    private fun buildUtterance(appName: String, title: String, text: String): String {
        return if (title.isNotBlank() && !title.equals(appName, ignoreCase = true)) {
            "$appName, $title: $text"
        } else {
            "$appName: $text"
        }
    }

    private fun getAppLabel(packageName: String): String {
        return try {
            val info = packageManager.getApplicationInfo(packageName, 0)
            packageManager.getApplicationLabel(info).toString()
        } catch (_: PackageManager.NameNotFoundException) {
            packageName
        }
    }

    private fun speak(text: String) {
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        val wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "NotifReader::TTS")
        wl.acquire(WAKELOCK_TIMEOUT_MS)
        wakeLock = wl
        tts?.speak(text, TextToSpeech.QUEUE_ADD, null, "u_${System.currentTimeMillis()}")
    }

    private fun initTts() {
        tts = TextToSpeech(this) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val result = tts?.setLanguage(Locale("tr", "TR"))
                if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                    tts?.language = Locale.getDefault()
                }
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {}
                    override fun onDone(utteranceId: String?) = releaseWakeLock()
                    @Deprecated("Deprecated in Java")
                    override fun onError(utteranceId: String?) = releaseWakeLock()
                })
                ttsReady = true
            }
        }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
    }

    private fun releaseTts() {
        ttsReady = false
        tts?.stop()
        tts?.shutdown()
        tts = null
        releaseWakeLock()
    }

    private fun createChannel() {
        val ch = NotificationChannel(CHANNEL_ID, "Bildirim Okuyucu",
            NotificationManager.IMPORTANCE_LOW).apply {
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
    }

    private fun buildFgNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Bildirim Okuyucu aktif")
            .setSmallIcon(R.drawable.ic_service)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }

    override fun onDestroy() {
        releaseTts()
        super.onDestroy()
    }
}
