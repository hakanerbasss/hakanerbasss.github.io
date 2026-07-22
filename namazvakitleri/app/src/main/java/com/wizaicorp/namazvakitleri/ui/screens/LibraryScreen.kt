package com.wizaicorp.namazvakitleri.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.LibraryData
import com.wizaicorp.namazvakitleri.data.LibraryItem
import com.wizaicorp.namazvakitleri.util.QuranPlayer
import com.wizaicorp.namazvakitleri.util.Speech

/** Sure/dua listesi */
@Composable
fun LibraryScreen(onOpen: (LibraryItem) -> Unit, onBack: () -> Unit) {
    var tab by remember { mutableIntStateOf(0) }
    val items = if (tab == 0) LibraryData.sureler else LibraryData.dualar

    FeatureScaffold(title = Lang.get("library"), onBack = onBack) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Row(
                Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = tab == 0,
                    onClick = { tab = 0 },
                    label = { Text(Lang.get("lib_sure_tab")) }
                )
                FilterChip(
                    selected = tab == 1,
                    onClick = { tab = 1 },
                    label = { Text(Lang.get("lib_dua_tab")) }
                )
            }
            LazyColumn(
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                itemsIndexed(items) { _, item ->
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        modifier = Modifier.fillMaxWidth().clickable { onOpen(item) }
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(
                                    item.name,
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.SemiBold,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Text(
                                    item.info,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                                )
                            }
                            Text(
                                item.nameAr,
                                style = MaterialTheme.typography.titleLarge,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }
                    }
                }
            }
        }
    }
}

/** Sure/dua detayi - sesli okuma + otomatik vurgu ve kaydirma */
@Composable
fun LibraryDetailScreen(item: LibraryItem, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val listState = rememberLazyListState()
    var current by remember { mutableIntStateOf(-1) }
    var isPlaying by remember { mutableStateOf(false) }
    // Okuma modu: "audio" = kiraat (hafiz kaydi ya da Arapca TTS), "reading" = okunus, "meaning" = meal
    val hasAudio = item.audioIds.isNotEmpty()
    var readMode by remember { mutableStateOf("audio") }

    LaunchedEffect(Unit) { Speech.init(ctx) }
    DisposableEffect(Unit) { onDispose { Speech.stop(); QuranPlayer.stop() } }

    // Okunan ayete otomatik kaydir (imlec takibi) - -2 = tum kartlar birlikte vurgulu, kaydirma yok
    LaunchedEffect(current) {
        if (current >= 0) listState.animateScrollToItem(current)
    }

    fun play() {
        isPlaying = true
        current = -1
        if (readMode == "audio" && hasAudio) {
            // Gercek hafiz kaydi. Ayet kodu sayisi kart sayisiyla eslesiyorsa
            // kart kart takip; tek ses dosyasi birden fazla karti kapsiyorsa
            // (orn. Ayetel Kursi) butun kartlar birlikte vurgulanir.
            val sync = item.audioIds.size == item.verses.size
            QuranPlayer.playSequence(
                item.audioIds,
                onIndex = { current = if (sync) it else -2 },
                onFinished = { isPlaying = false; current = -1 }
            )
        } else if (readMode == "audio") {
            // Hafiz kaydi olmayan dualar: Arapca TTS ile kiraat;
            // Arapca ses paketi yoksa okunusa duser
            val arabicOk = Speech.arabicAvailable()
            Speech.speakSequence(
                item.verses.map { if (arabicOk) it.arabic else it.reading },
                onIndex = { current = it },
                onFinished = { isPlaying = false; current = -1 },
                arabic = arabicOk
            )
        } else {
            val texts = item.verses.map { v ->
                if (readMode == "reading") v.reading else v.meaning
            }
            Speech.speakSequence(
                texts,
                onIndex = { current = it },
                onFinished = { isPlaying = false; current = -1 }
            )
        }
    }

    fun stop() {
        Speech.stop()
        QuranPlayer.stop()
        isPlaying = false
        current = -1
    }

    FeatureScaffold(title = item.name, onBack = { stop(); onBack() }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {

            // Kontroller
            Row(
                Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                FilterChip(
                    selected = readMode == "audio",
                    onClick = { stop(); readMode = "audio" },
                    label = { Text(Lang.get("mode_audio")) }
                )
                FilterChip(
                    selected = readMode == "reading",
                    onClick = { stop(); readMode = "reading" },
                    label = { Text(Lang.get("mode_reading")) }
                )
                FilterChip(
                    selected = readMode == "meaning",
                    onClick = { stop(); readMode = "meaning" },
                    label = { Text(Lang.get("mode_meaning")) }
                )
                Spacer(Modifier.weight(1f))
                if (isPlaying) {
                    FilledIconButton(onClick = { stop() }) {
                        Icon(Icons.Filled.Stop, contentDescription = Lang.get("stop"))
                    }
                } else {
                    FilledIconButton(onClick = { play() }) {
                        Icon(Icons.Filled.PlayArrow, contentDescription = Lang.get("read_all"))
                    }
                }
            }

            LazyColumn(
                state = listState,
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.weight(1f)
            ) {
                itemsIndexed(item.verses) { i, verse ->
                    val active = current == -2 || i == current
                    Surface(
                        shape = RoundedCornerShape(14.dp),
                        color = if (active) MaterialTheme.colorScheme.primary
                                else MaterialTheme.colorScheme.surfaceVariant,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                when {
                                    readMode == "audio" && item.audioIds.size == item.verses.size ->
                                        QuranPlayer.playSequence(
                                            listOf(item.audioIds[i]),
                                            onIndex = { },
                                            onFinished = { }
                                        )
                                    readMode == "audio" && !hasAudio -> {
                                        val arabicOk = Speech.arabicAvailable()
                                        Speech.speak(
                                            if (arabicOk) verse.arabic else verse.reading,
                                            arabic = arabicOk
                                        )
                                    }
                                    else -> Speech.speak(
                                        if (readMode == "reading") verse.reading else verse.meaning
                                    )
                                }
                            }
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(
                                verse.arabic,
                                fontSize = 24.sp,
                                lineHeight = 40.sp,
                                textAlign = TextAlign.End,
                                modifier = Modifier.fillMaxWidth(),
                                color = if (active) MaterialTheme.colorScheme.onPrimary
                                        else MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(Modifier.height(8.dp))
                            Text(
                                verse.reading,
                                style = MaterialTheme.typography.bodyLarge,
                                fontStyle = FontStyle.Italic,
                                fontWeight = if (active) FontWeight.Bold else FontWeight.Normal,
                                color = if (active) MaterialTheme.colorScheme.secondary
                                        else MaterialTheme.colorScheme.primary
                            )
                            Spacer(Modifier.height(4.dp))
                            Text(
                                verse.meaning,
                                style = MaterialTheme.typography.bodyMedium,
                                color = if (active)
                                    MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.9f)
                                else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
                            )
                        }
                    }
                }
                item { Spacer(Modifier.height(8.dp)) }
            }
        }
    }
}
