package com.wizaicorp.namazvakitleri.util

import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Handler
import android.os.Looper

/**
 * Gercek hafiz kiraati - everyayah.com'dan ayet ayet stream eder
 * (Mishary Alafasy, 128kbps). Ek kutuphane gerektirmez.
 */
object QuranPlayer {

    private const val BASE = "https://everyayah.com/data/Alafasy_128kbps/"

    private var mp: MediaPlayer? = null
    private var stopped = false
    private val mainHandler = Handler(Looper.getMainLooper())

    fun playSequence(ids: List<String>, onIndex: (Int) -> Unit, onFinished: () -> Unit) {
        stop()
        stopped = false
        playAt(0, ids, onIndex, onFinished)
    }

    private fun playAt(i: Int, ids: List<String>, onIndex: (Int) -> Unit, onFinished: () -> Unit) {
        if (stopped) return
        if (i >= ids.size) { mainHandler.post { onFinished() }; return }
        try {
            val p = MediaPlayer()
            mp = p
            p.setAudioAttributes(
                AudioAttributes.Builder()
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .build()
            )
            p.setDataSource(BASE + ids[i] + ".mp3")
            p.setOnPreparedListener {
                if (!stopped) {
                    // Vurgu/kaydirma tam bu ayetin sesi baslarken tetiklenir
                    mainHandler.post { onIndex(i) }
                    it.start()
                } else {
                    it.release()
                }
            }
            p.setOnCompletionListener {
                it.release()
                if (mp == it) mp = null
                playAt(i + 1, ids, onIndex, onFinished)
            }
            p.setOnErrorListener { pl, _, _ ->
                pl.release()
                if (mp == pl) mp = null
                playAt(i + 1, ids, onIndex, onFinished)
                true
            }
            p.prepareAsync()
        } catch (e: Exception) {
            playAt(i + 1, ids, onIndex, onFinished)
        }
    }

    fun stop() {
        stopped = true
        try { mp?.stop() } catch (e: Exception) { }
        try { mp?.release() } catch (e: Exception) { }
        mp = null
    }
}
