package com.wizaicorp.namazvakitleri.ui.screens

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.data.ApiPrefs
import com.wizaicorp.namazvakitleri.data.Lang

@Composable
fun ApiSettingsScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    var pexelsKey by remember { mutableStateOf(ApiPrefs.getPexelsKey(ctx)) }
    var deepseekKey by remember { mutableStateOf(ApiPrefs.getDeepSeekKey(ctx)) }

    FeatureScaffold(title = Lang.get("api_settings"), onBack = onBack) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            KeyCard(
                title = "Pexels API Key",
                unlocks = Lang.get("pexels_unlocks"),
                guide = Lang.get("pexels_guide"),
                value = pexelsKey,
                onValueChange = { pexelsKey = it },
                onSave = {
                    ApiPrefs.setPexelsKey(ctx, pexelsKey)
                    Toast.makeText(ctx, Lang.get("saved"), Toast.LENGTH_SHORT).show()
                }
            )

            KeyCard(
                title = "DeepSeek API Key",
                unlocks = Lang.get("deepseek_unlocks"),
                guide = Lang.get("deepseek_guide"),
                value = deepseekKey,
                onValueChange = { deepseekKey = it },
                onSave = {
                    ApiPrefs.setDeepSeekKey(ctx, deepseekKey)
                    Toast.makeText(ctx, Lang.get("saved"), Toast.LENGTH_SHORT).show()
                }
            )

            Text(
                Lang.get("key_stored_note"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f)
            )
        }
    }
}

@Composable
private fun KeyCard(
    title: String,
    unlocks: String,
    guide: String,
    value: String,
    onValueChange: (String) -> Unit,
    onSave: () -> Unit
) {
    var showGuide by remember { mutableStateOf(false) }

    Surface(
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                unlocks,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary
            )
            OutlinedTextField(
                value = value,
                onValueChange = onValueChange,
                placeholder = { Text(Lang.get("key_hint")) },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onSave) { Text(Lang.get("save")) }
                TextButton(onClick = { showGuide = !showGuide }) {
                    Text(Lang.get("how_to_get"))
                }
            }
            if (showGuide) {
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        guide,
                        modifier = Modifier.padding(12.dp),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}
