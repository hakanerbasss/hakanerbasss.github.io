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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.wizaicorp.namazvakitleri.data.EduTopic
import com.wizaicorp.namazvakitleri.data.EducationData
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.util.Speech

/** Egitim konulari listesi */
@Composable
fun EducationScreen(onOpen: (EduTopic) -> Unit, onBack: () -> Unit) {
    FeatureScaffold(title = Lang.get("education"), onBack = onBack) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            itemsIndexed(EducationData.topics) { _, topic ->
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier.fillMaxWidth().clickable { onOpen(topic) }
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(topic.emoji, fontSize = 28.sp)
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                topic.name,
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.SemiBold,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                topic.intro,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                                maxLines = 2
                            )
                        }
                    }
                }
            }
            item {
                Text(
                    Lang.get("edu_disclaimer"),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
        }
    }
}

/** Konu detayi - adim adim kartlar, sesli okuma + otomatik takip */
@Composable
fun EducationDetailScreen(topic: EduTopic, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val listState = rememberLazyListState()
    var current by remember { mutableIntStateOf(-1) }
    var isPlaying by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { Speech.init(ctx) }
    DisposableEffect(Unit) { onDispose { Speech.stop() } }

    LaunchedEffect(current) {
        if (current >= 0) listState.animateScrollToItem(current + 1)
    }

    fun play() {
        isPlaying = true
        current = -1
        Speech.speakSequence(
            topic.steps.map { "${it.title}. ${it.body}" },
            onIndex = { current = it },
            onFinished = { isPlaying = false; current = -1 }
        )
    }

    fun stop() {
        Speech.stop()
        isPlaying = false
        current = -1
    }

    FeatureScaffold(title = topic.name, onBack = { stop(); onBack() }) { padding ->
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            item {
                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = MaterialTheme.colorScheme.primaryContainer,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        Modifier.padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            topic.intro,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                            modifier = Modifier.weight(1f)
                        )
                        Spacer(Modifier.width(8.dp))
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
                }
            }

            itemsIndexed(topic.steps) { i, step ->
                val active = i == current
                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = if (active) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { Speech.speak("${step.title}. ${step.body}") }
                ) {
                    Row(Modifier.padding(14.dp)) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(step.emoji, fontSize = 26.sp)
                            Spacer(Modifier.height(4.dp))
                            Text(
                                "${i + 1}",
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold,
                                color = if (active) MaterialTheme.colorScheme.secondary
                                        else MaterialTheme.colorScheme.primary
                            )
                        }
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                step.title,
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold,
                                color = if (active) MaterialTheme.colorScheme.onPrimary
                                        else MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(Modifier.height(4.dp))
                            Text(
                                step.body,
                                style = MaterialTheme.typography.bodyMedium,
                                color = if (active)
                                    MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.9f)
                                else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.85f)
                            )
                        }
                    }
                }
            }
        }
    }
}
