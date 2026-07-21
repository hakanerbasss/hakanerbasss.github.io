package com.wizaicorp.namazvakitleri.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
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
import com.wizaicorp.namazvakitleri.data.EsmaData
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.util.Speech

@Composable
fun EsmaScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val todayEsma = remember { EsmaData.ofToday() }
    var isPlaying by remember { mutableStateOf(false) }
    // Okuma modu: "audio" = Arapca kiraat, "meaning" = isim+anlam
    var readMode by remember { mutableStateOf("audio") }

    LaunchedEffect(Unit) { Speech.init(ctx) }
    DisposableEffect(Unit) { onDispose { Speech.stop() } }

    fun stop() {
        Speech.stop()
        isPlaying = false
    }

    fun speakOne(name: String, arabic: String, meaning: String) {
        if (readMode == "audio") {
            val arabicOk = Speech.arabicAvailable()
            Speech.speak(if (arabicOk) arabic else name, arabic = arabicOk)
        } else {
            Speech.speak("$name. $meaning")
        }
    }

    fun playAll() {
        isPlaying = true
        val arabicOk = readMode == "audio" && Speech.arabicAvailable()
        val texts = EsmaData.list.map { esma ->
            when {
                readMode == "audio" && arabicOk -> esma.arabic
                readMode == "audio" -> esma.name
                else -> "${esma.name}. ${esma.meaning}"
            }
        }
        Speech.speakSequence(
            texts,
            onIndex = { },
            onFinished = { isPlaying = false },
            arabic = arabicOk
        )
    }

    FeatureScaffold(title = Lang.get("esma"), onBack = { stop(); onBack() }) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            item {
                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { speakOne(todayEsma.name, todayEsma.arabic, todayEsma.meaning) }
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            Lang.get("esma_of_day"),
                            style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.8f)
                        )
                        Spacer(Modifier.height(6.dp))
                        Text(
                            todayEsma.arabic,
                            style = MaterialTheme.typography.headlineMedium,
                            color = MaterialTheme.colorScheme.onPrimary
                        )
                        Spacer(Modifier.height(2.dp))
                        Text(
                            todayEsma.name,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.9f)
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            todayEsma.meaning,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.secondary
                        )
                    }
                }
                Spacer(Modifier.height(8.dp))

                // Okuma modu
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = readMode == "audio",
                        onClick = { stop(); readMode = "audio" },
                        label = { Text(Lang.get("mode_audio")) }
                    )
                    FilterChip(
                        selected = readMode == "meaning",
                        onClick = { stop(); readMode = "meaning" },
                        label = { Text(Lang.get("mode_meaning")) }
                    )
                }
                Spacer(Modifier.height(8.dp))

                // Sesli okuma kontrolleri
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (isPlaying) {
                        Button(onClick = { stop() }, modifier = Modifier.weight(1f)) {
                            Icon(Icons.Filled.Stop, contentDescription = null)
                            Spacer(Modifier.width(6.dp))
                            Text(Lang.get("stop"))
                        }
                    } else {
                        Button(onClick = { playAll() }, modifier = Modifier.weight(1f)) {
                            Icon(Icons.Filled.PlayArrow, contentDescription = null)
                            Spacer(Modifier.width(6.dp))
                            Text(Lang.get("read_all"))
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
            }

            itemsIndexed(EsmaData.list) { i, esma ->
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { speakOne(esma.name, esma.arabic, esma.meaning) }
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            "${i + 1}",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.width(28.dp)
                        )
                        Column(Modifier.weight(1f)) {
                            Text(
                                esma.name,
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.SemiBold,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                esma.meaning,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                            )
                        }
                        Text(
                            esma.arabic,
                            style = MaterialTheme.typography.titleLarge,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }
                }
            }
        }
    }
}
