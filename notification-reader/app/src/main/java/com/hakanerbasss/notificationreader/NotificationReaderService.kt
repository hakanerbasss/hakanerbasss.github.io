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
        val appName = getAppLabel(sbn.packageName)

        val texts = if (prefs.isReadAllMessages()) {
            extractAllTexts(extras)
        } else {
            listOf(extractLatestText(extras))
        }

        texts.filter { it.isNotBlank() }.forEach { text ->
            speak(buildUtterance(appName, title, text))
        }
    }

    private fun buildUtterance(appName: String, title: String, text: String): String {
        val parts = mutableListOf<String>()

        if (prefs.isAnnounceApp()) {
            parts.add(appName)
        }

        if (prefs.isAnnounceSender()) {
            val isSenderSameAsApp = title.isBlank() || title.equals(appName, ignoreCase = true)
            if (!isSenderSameAsApp) {
                if (isPhoneNumber(title)) {
                    if (prefs.isAnnounceNumber()) parts.add(title)
                } else {
                    parts.add(title)
                }
            }
        }

        return if (parts.isEmpty()) {
            text
        } else {
            "${parts.joinToString(", ")}: $text"
        }
    }

    private fun isPhoneNumber(text: String): Boolean =
        text.replace("+", "").replace("-", "").replace(" ", "")
            .all { it.isDigit() } && text.length >= 5

    @Suppress("DEPRECATION")
    private fun extractLatestText(extras: android.os.Bundle): String {
        val messages = extras.getParcelableArray(Notification.EXTRA_MESSAGES)
        if (messages != null && messages.isNotEmpty()) {
            val t = (messages.last() as? android.os.Bundle)
                ?.getCharSequence("text")?.toString().orEmpty().trim()
            if (t.isNotBlank()) return t
        }
        val t = extras.getString(Notification.EXTRA_TEXT).orEmpty().trim()
        if (t.isNotBlank()) return t
        return extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty().trim()
    }

    @Suppress("DEPRECATION")
    private fun extractAllTexts(extras: android.os.Bundle): List<String> {
        val messages = extras.getParcelableArray(Notification.EXTRA_MESSAGES)
        if (messages != null && messages.size > 1) {
            val all = messages.mapNotNull {
                (it as? android.os.Bundle)?.getCharSequence("text")?.toString()?.trim()
            }.filter { it.isNotBlank() }
            if (all.isNotEmpty()) return all
        }
        return listOf(extractLatestText(extras))
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
            NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) }
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
