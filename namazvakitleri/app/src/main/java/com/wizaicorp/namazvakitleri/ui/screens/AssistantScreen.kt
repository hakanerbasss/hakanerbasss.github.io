package com.wizaicorp.namazvakitleri.ui.screens

import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.api.DeepSeekApi
import com.wizaicorp.namazvakitleri.data.ApiPrefs
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.util.Speech
import kotlinx.coroutines.launch

@Composable
fun AssistantScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()

    // (soru, cevap) ciftleri; cevap bos ise henuz yanit bekleniyor
    var messages by remember { mutableStateOf(listOf<Pair<String, String>>()) }
    var input by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var readAloud by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) { Speech.init(ctx) }
    DisposableEffect(Unit) { onDispose { Speech.stop() } }

    LaunchedEffect(messages.size, busy) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }

    fun send(question: String) {
        val q = question.trim()
        if (q.isEmpty() || busy) return
        val key = ApiPrefs.getDeepSeekKey(ctx)
        if (key.isEmpty()) return
        input = ""
        busy = true
        val history = messages.filter { it.second.isNotEmpty() }
        messages = messages + (q to "")
        scope.launch {
            val answer = try {
                DeepSeekApi.ask(key, history, q).ifBlank { Lang.get("assistant_err") }
            } catch (e: Exception) {
                Lang.get("assistant_err")
            }
            messages = messages.dropLast(1) + (q to answer)
            busy = false
            if (readAloud) Speech.speak(answer)
        }
    }

    val speechLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val text = result.data
            ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
            ?.firstOrNull()
        if (!text.isNullOrBlank()) send(text)
    }

    fun startVoice() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
            )
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE,
                if (Lang.code == "tr") "tr-TR" else "en-US"
            )
        }
        try { speechLauncher.launch(intent) } catch (e: Exception) { }
    }

    FeatureScaffold(title = Lang.get("assistant"), onBack = { Speech.stop(); onBack() }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {

            // Fetva degildir uyarisi - kalici
            Surface(
                color = MaterialTheme.colorScheme.secondary.copy(alpha = 0.15f),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    Lang.get("assistant_disclaimer"),
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                )
            }

            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                itemsIndexed(messages) { _, (q, a) ->
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        // Kullanici balonu
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                            Surface(
                                shape = RoundedCornerShape(16.dp, 16.dp, 4.dp, 16.dp),
                                color = MaterialTheme.colorScheme.primary
                            ) {
                                Text(
                                    q,
                                    modifier = Modifier.padding(12.dp).widthIn(max = 280.dp),
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onPrimary
                                )
                            }
                        }
                        // Asistan balonu
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Start) {
                            Surface(
                                shape = RoundedCornerShape(16.dp, 16.dp, 16.dp, 4.dp),
                                color = MaterialTheme.colorScheme.surfaceVariant
                            ) {
                                if (a.isEmpty()) {
                                    Row(
                                        Modifier.padding(12.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        CircularProgressIndicator(
                                            modifier = Modifier.size(16.dp),
                                            strokeWidth = 2.dp
                                        )
                                        Spacer(Modifier.width(8.dp))
                                        Text(
                                            Lang.get("thinking"),
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                    }
                                } else {
                                    Text(
                                        a,
                                        modifier = Modifier.padding(12.dp).widthIn(max = 300.dp),
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                    }
                }
            }

            // Sesli okuma anahtari
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(Lang.get("tts_toggle"), style = MaterialTheme.typography.labelMedium)
                Switch(checked = readAloud, onCheckedChange = {
                    readAloud = it
                    if (!it) Speech.stop()
                })
            }

            // Giris satiri
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    placeholder = { Text(Lang.get("ask_hint")) },
                    modifier = Modifier.weight(1f),
                    maxLines = 3
                )
                FilledIconButton(onClick = { startVoice() }, enabled = !busy) {
                    Icon(Icons.Filled.Mic, contentDescription = null)
                }
                FilledIconButton(onClick = { send(input) }, enabled = !busy && input.isNotBlank()) {
                    Icon(Icons.Filled.Send, contentDescription = null)
                }
            }
        }
    }
}
