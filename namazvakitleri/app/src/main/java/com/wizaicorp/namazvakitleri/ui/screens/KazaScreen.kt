package com.wizaicorp.namazvakitleri.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.data.KazaPrefs
import com.wizaicorp.namazvakitleri.data.Lang

@Composable
fun KazaScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val counts = remember {
        KazaPrefs.prayers.associate { (key, _) ->
            key to mutableIntStateOf(KazaPrefs.get(ctx, key))
        }
    }

    FeatureScaffold(title = Lang.get("kaza"), onBack = onBack) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Text(
                Lang.get("kaza_desc"),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
            )

            Button(
                onClick = {
                    KazaPrefs.addDayToAll(ctx)
                    KazaPrefs.prayers.forEach { (key, _) ->
                        counts[key]?.intValue = KazaPrefs.get(ctx, key)
                    }
                },
                modifier = Modifier.fillMaxWidth()
            ) { Text(Lang.get("add_one_day")) }

            KazaPrefs.prayers.forEach { (key, nameKey) ->
                val state = counts[key] ?: return@forEach
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            Lang.get(nameKey),
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.weight(1f),
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        IconButton(onClick = {
                            val v = (state.intValue - 1).coerceAtLeast(0)
                            state.intValue = v
                            KazaPrefs.set(ctx, key, v)
                        }) {
                            Icon(Icons.Filled.Remove, contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary)
                        }
                        Text(
                            state.intValue.toString(),
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.widthIn(min = 44.dp),
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center
                        )
                        IconButton(onClick = {
                            val v = state.intValue + 1
                            state.intValue = v
                            KazaPrefs.set(ctx, key, v)
                        }) {
                            Icon(Icons.Filled.Add, contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }

            Spacer(Modifier.height(8.dp))
        }
    }
}
