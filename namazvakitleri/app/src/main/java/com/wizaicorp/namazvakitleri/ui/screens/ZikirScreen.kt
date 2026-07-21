package com.wizaicorp.namazvakitleri.ui.screens

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.ZikirPrefs
import com.wizaicorp.namazvakitleri.util.Speech

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ZikirScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val haptic = LocalHapticFeedback.current

    var selected by remember { mutableIntStateOf(ZikirPrefs.getSelected(ctx)) }
    var target   by remember { mutableIntStateOf(ZikirPrefs.getTarget(ctx)) }
    var count    by remember {
        mutableIntStateOf(ZikirPrefs.getCount(ctx, ZikirPrefs.zikirKeys[ZikirPrefs.getSelected(ctx)]))
    }
    var total by remember { mutableStateOf(ZikirPrefs.getTotal(ctx)) }
    var soundMode by remember { mutableStateOf(ZikirPrefs.getSoundMode(ctx)) }
    var isRecording by remember { mutableStateOf(false) }
    var recorder by remember { mutableStateOf<MediaRecorder?>(null) }
    var player by remember { mutableStateOf<MediaPlayer?>(null) }

    val zikirKey = ZikirPrefs.zikirKeys[selected]
    val done = target > 0 && count >= target

    LaunchedEffect(Unit) { Speech.init(ctx) }

    fun releasePlayer() {
        try { player?.release() } catch (e: Exception) { }
        player = null
    }

    fun preparePlayer() {
        releasePlayer()
        val f = ZikirPrefs.recFile(ctx, zikirKey)
        if (f.exists()) {
            try {
                player = MediaPlayer().apply { setDataSource(f.absolutePath); prepare() }
            } catch (e: Exception) { player = null }
        }
    }

    LaunchedEffect(selected) { preparePlayer() }
    DisposableEffect(Unit) {
        onDispose {
            releasePlayer()
            try { recorder?.release() } catch (e: Exception) { }
            Speech.stop()
        }
    }

    fun stopRecording() {
        try { recorder?.stop() } catch (e: Exception) { }
        try { recorder?.release() } catch (e: Exception) { }
        recorder = null
        isRecording = false
        preparePlayer()
        Toast.makeText(ctx, Lang.get("rec_saved"), Toast.LENGTH_SHORT).show()
    }

    fun startRecording() {
        try {
            val f = ZikirPrefs.recFile(ctx, zikirKey)
            releasePlayer()
            val r = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
                MediaRecorder(ctx) else @Suppress("DEPRECATION") MediaRecorder()
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setOutputFile(f.absolutePath)
            r.prepare()
            r.start()
            recorder = r
            isRecording = true
        } catch (e: Exception) {
            isRecording = false
        }
    }

    val micPermLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startRecording()
        else Toast.makeText(ctx, Lang.get("mic_perm"), Toast.LENGTH_SHORT).show()
    }

    fun playSound() {
        when (soundMode) {
            "tts" -> Speech.speak(Lang.get(zikirKey))
            "rec" -> {
                val p = player
                if (p == null) {
                    Toast.makeText(ctx, Lang.get("rec_missing"), Toast.LENGTH_SHORT).show()
                } else {
                    try {
                        if (p.isPlaying) p.seekTo(0) else p.start()
                    } catch (e: Exception) { }
                }
            }
        }
    }

    fun tap() {
        if (isRecording) return
        count++
        ZikirPrefs.setCount(ctx, zikirKey, count)
        ZikirPrefs.addTotal(ctx)
        total = ZikirPrefs.getTotal(ctx)
        haptic.performHapticFeedback(
            if (target > 0 && count == target) HapticFeedbackType.LongPress
            else HapticFeedbackType.TextHandleMove
        )
        playSound()
    }

    FeatureScaffold(title = Lang.get("zikir"), onBack = onBack) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
        ) {
            // Zikir secimi
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ZikirPrefs.zikirKeys.forEachIndexed { i, key ->
                    FilterChip(
                        selected = selected == i,
                        onClick = {
                            selected = i
                            ZikirPrefs.setSelected(ctx, i)
                            count = ZikirPrefs.getCount(ctx, ZikirPrefs.zikirKeys[i])
                        },
                        label = { Text(Lang.get(key)) }
                    )
                }
            }

            Spacer(Modifier.height(4.dp))

            // Hedef secimi
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "${Lang.get("target")}: ",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary
                )
                ZikirPrefs.targets.forEach { t ->
                    TextButton(onClick = { target = t; ZikirPrefs.setTarget(ctx, t) }) {
                        Text(
                            if (t == 0) Lang.get("unlimited") else t.toString(),
                            fontWeight = if (target == t) FontWeight.Bold else FontWeight.Normal,
                            color = if (target == t) MaterialTheme.colorScheme.primary
                                    else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                        )
                    }
                }
            }

            // Ses modu
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "${Lang.get("sound_label")}: ",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary
                )
                listOf(
                    "off" to Lang.get("sound_off"),
                    "tts" to Lang.get("sound_tts"),
                    "rec" to Lang.get("sound_rec")
                ).forEach { (mode, label) ->
                    TextButton(onClick = {
                        soundMode = mode
                        ZikirPrefs.setSoundMode(ctx, mode)
                    }) {
                        Text(
                            label,
                            fontWeight = if (soundMode == mode) FontWeight.Bold else FontWeight.Normal,
                            color = if (soundMode == mode) MaterialTheme.colorScheme.primary
                                    else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                        )
                    }
                }
            }

            // Kayit butonu (sadece "Kaydim" modunda)
            if (soundMode == "rec") {
                Button(
                    onClick = {
                        if (isRecording) {
                            stopRecording()
                        } else {
                            val has = ContextCompat.checkSelfPermission(
                                ctx, Manifest.permission.RECORD_AUDIO
                            ) == PackageManager.PERMISSION_GRANTED
                            if (has) startRecording()
                            else micPermLauncher.launch(Manifest.permission.RECORD_AUDIO)
                        }
                    },
                    colors = if (isRecording)
                        ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)
                    else ButtonDefaults.buttonColors(),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(Icons.Filled.Mic, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text(if (isRecording) Lang.get("record_stop") else Lang.get("record_start"))
                }
                Spacer(Modifier.height(8.dp))
            }

            // Buyuk sayac alani - dokununca sayar
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = if (done) MaterialTheme.colorScheme.secondary.copy(alpha = 0.25f)
                        else MaterialTheme.colorScheme.primaryContainer,
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .clickable(
                        interactionSource = remember { MutableInteractionSource() },
                        indication = null
                    ) { tap() }
            ) {
                Column(
                    modifier = Modifier.fillMaxSize(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Text(
                        Lang.get(zikirKey),
                        style = MaterialTheme.typography.titleLarge,
                        color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f)
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(
                        count.toString(),
                        fontSize = 96.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                    if (target > 0) {
                        Spacer(Modifier.height(8.dp))
                        LinearProgressIndicator(
                            progress = { (count.toFloat() / target).coerceIn(0f, 1f) },
                            modifier = Modifier.fillMaxWidth(0.6f)
                        )
                        Spacer(Modifier.height(6.dp))
                        Text(
                            if (done) Lang.get("target_done") else "$count / $target",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = if (done) FontWeight.Bold else FontWeight.Normal,
                            color = MaterialTheme.colorScheme.onPrimaryContainer
                        )
                    }
                    Spacer(Modifier.height(12.dp))
                    Text(
                        Lang.get("tap_hint"),
                        style = MaterialTheme.typography.bodySmall,
                        textAlign = TextAlign.Center,
                        color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.5f)
                    )
                }
            }

            Spacer(Modifier.height(12.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "${Lang.get("total")}: $total",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                )
                OutlinedButton(onClick = {
                    count = 0
                    ZikirPrefs.setCount(ctx, zikirKey, 0)
                }) { Text(Lang.get("reset")) }
            }
        }
    }
}
