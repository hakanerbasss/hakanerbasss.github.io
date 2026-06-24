package com.hakanerbasss.notificationreader

import android.app.Notification
import android.content.pm.PackageManager
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.widget.Toast
import java.util.Locale

class NotificationReaderService : NotificationListenerService() {

    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var wakeLock: PowerManager.WakeLock? = null
    private val prefs by lazy { AppPreferences(this) }

    companion object {
        private const val WAKELOCK_TIMEOUT_MS = 30_000L
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
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

        // WhatsApp ve benzeri uygulamalar MessagingStyle kullanır — mesaj EXTRA_MESSAGES içinde
        val text = extractText(extras)
        if (text.isBlank()) return

        val appName = getAppLabel(sbn.packageName)
        val utterance = buildUtterance(appName, title, text)
        toast("Okunuyor: $utterance")
        speak(utterance)
    }

    @Suppress("DEPRECATION")
    private fun extractText(extras: android.os.Bundle): String {
        // 1. MessagingStyle: son mesajı al (WhatsApp, Telegram vb.)
        val messages = extras.getParcelableArray(Notification.EXTRA_MESSAGES)
        if (messages != null && messages.isNotEmpty()) {
            val last = messages.last() as? android.os.Bundle
            val msgText = last?.getCharSequence("text")?.toString().orEmpty().trim()
            if (msgText.isNotBlank()) return msgText
        }
        // 2. Standart text
        val text = extras.getString(Notification.EXTRA_TEXT).orEmpty().trim()
        if (text.isNotBlank()) return text
        // 3. BigText (uzun mesajlar)
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

    private fun toast(msg: String) {
        Handler(Looper.getMainLooper()).post {
            Toast.makeText(applicationContext, msg, Toast.LENGTH_SHORT).show()
        }
    }

    private fun initTts() {
        tts = TextToSpeech(this) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val result = tts?.setLanguage(Locale("tr", "TR"))
                if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                    tts?.language = Locale.getDefault()
                    toast("TTS: Turkce ses paketi yok, varsayilan kullaniliyor")
                } else {
                    toast("TTS hazir - Turkce aktif")
                }
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {}
                    override fun onDone(utteranceId: String?) = releaseWakeLock()
                    @Deprecated("Deprecated in Java")
                    override fun onError(utteranceId: String?) = releaseWakeLock()
                })
                ttsReady = true
            } else {
                toast("TTS BASLATILAM ADI - hata kodu: $status")
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

    override fun onDestroy() {
        releaseTts()
        super.onDestroy()
    }
}
