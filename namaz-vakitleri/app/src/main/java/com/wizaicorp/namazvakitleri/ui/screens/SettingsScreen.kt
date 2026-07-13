package com.wizaicorp.namazvakitleri.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.data.NotifPrefs

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun SettingsScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val offsets = listOf(0, 5, 10, 15, 20, 30)
    var selectedOffset by remember { mutableIntStateOf(NotifPrefs.getOffsetMin(ctx)) }
    val toggles = remember {
        NotifPrefs.allPrayers.associate { (key, _) ->
            key to mutableStateOf(NotifPrefs.isEnabled(ctx, key))
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Bildirim Ayarları") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, null)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor             = MaterialTheme.colorScheme.primary,
                    titleContentColor          = MaterialTheme.colorScheme.onPrimary,
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text("Kaç dakika önce?", style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary)

            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                offsets.forEach { min ->
                    FilterChip(
                        selected = selectedOffset == min,
                        onClick  = { selectedOffset = min; NotifPrefs.setOffsetMin(ctx, min) },
                        label    = { Text(if (min == 0) "Tam vakitte" else "$min dk önce") }
                    )
                }
            }

            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

            Text("Hangi vakitler?", style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary)

            NotifPrefs.allPrayers.forEach { (key, label) ->
                val state = toggles[key] ?: return@forEach
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(label, style = MaterialTheme.typography.bodyLarge)
                    Switch(
                        checked         = state.value,
                        onCheckedChange = { on -> state.value = on; NotifPrefs.setEnabled(ctx, key, on) }
                    )
                }
            }
        }
    }
}
