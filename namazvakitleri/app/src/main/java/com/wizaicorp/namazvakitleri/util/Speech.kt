package com.wizaicorp.namazvakitleri.util

import android.content.Context
import android.speech.tts.TextToSpeech
import com.wizaicorp.namazvakitleri.data.Lang
import java.util.Locale

/** Cihazin kendi TTS motoruyla seslendirme - ekstra ses dosyasi gerekmez. */
object Speech {

    private var tts: TextToSpeech? = null
    private var ready = false

    fun init(ctx: Context) {
        if (tts != null) return
        tts = TextToSpeech(ctx.applicationContext) { status ->
            ready = status == TextToSpeech.SUCCESS
            if (ready) {
                val locale = if (Lang.code == "tr") Locale("tr", "TR") else Locale.US
                try { tts?.language = locale } catch (e: Exception) { }
            }
        }
    }

    fun speak(text: String, flush: Boolean = true) {
        if (!ready) return
        tts?.speak(
            text,
            if (flush) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD,
            null,
            "namaz_tts_${System.currentTimeMillis()}"
        )
    }

    fun stop() {
        try { tts?.stop() } catch (e: Exception) { }
        try { tts?.setOnUtteranceProgressListener(null) } catch (e: Exception) { }
    }

    /**
     * Parcalari sirayla okur; her parca baslarken onIndex(i) cagirilir
     * (imlec takibi / otomatik kaydirma icin), hepsi bitince onFinished().
     * Geri cagrilar ana thread'e post edilir.
     */
    fun speakSequence(
        texts: List<String>,
        onIndex: (Int) -> Unit,
        onFinished: () -> Unit
    ) {
        if (!ready || texts.isEmpty()) return
        val t = tts ?: return
        val main = android.os.Handler(android.os.Looper.getMainLooper())
        t.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {
                utteranceId?.removePrefix("seq_")?.toIntOrNull()?.let { i ->
                    main.post { onIndex(i) }
                }
            }
            override fun onDone(utteranceId: String?) {
                if (utteranceId == "seq_${texts.size - 1}") main.post { onFinished() }
            }
            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) { }
        })
        texts.forEachIndexed { i, s ->
            t.speak(
                s,
                if (i == 0) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD,
                null,
                "seq_$i"
            )
        }
    }
}
