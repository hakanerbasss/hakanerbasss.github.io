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
    }
}
