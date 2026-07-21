package com.wizaicorp.namazvakitleri.ui.screens

import android.app.Activity
import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.NotifPrefs

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SettingsScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val offsets = listOf(0, 5, 10, 15, 20, 30, 45)
    var selectedOffset by remember { mutableIntStateOf(NotifPrefs.getOffsetMin(ctx)) }
    var langSetting by remember { mutableStateOf(Lang.getSetting(ctx)) }
    val toggles = remember {
        NotifPrefs.allPrayers.associate { (key, _) ->
            key to mutableStateOf(NotifPrefs.isEnabled(ctx, key))
        }
    }

    FeatureScaffold(title = Lang.get("settings_title"), onBack = onBack) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                Lang.get("pre_reminder_q"),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary
            )

            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                offsets.forEach { min ->
                    FilterChip(
                        selected = selectedOffset == min,
                        onClick  = {
                            selectedOffset = min
                            NotifPrefs.setOffsetMin(ctx, min)
                            Toast.makeText(ctx, Lang.get("saved"), Toast.LENGTH_SHORT).show()
                        },
                        label = {
                            Text(
                                if (min == 0) Lang.get("on_time_chip")
                                else "$min ${Lang.get("min_before")}"
                            )
                        }
                    )
                }
            }

            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

            Text(
                Lang.get("which_prayers"),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary
            )

            NotifPrefs.allPrayers.forEach { (key, nameKey) ->
                val state = toggles[key] ?: return@forEach
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(Lang.get(nameKey), style = MaterialTheme.typography.bodyLarge)
                    Switch(
                        checked         = state.value,
                        onCheckedChange = { on ->
                            state.value = on
                            NotifPrefs.setEnabled(ctx, key, on)
                            Toast.makeText(ctx, Lang.get("saved"), Toast.LENGTH_SHORT).show()
                        }
                    )
                }
            }

            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

            Text(
                Lang.get("lang_label"),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary
            )

            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(
                    "system" to Lang.get("lang_system"),
                    "tr" to "Türkçe",
                    "en" to "English"
                ).forEach { (value, label) ->
                    FilterChip(
                        selected = langSetting == value,
                        onClick = {
                            langSetting = value
                            Lang.setSetting(ctx, value)
                            (ctx as? Activity)?.recreate()
                        },
                        label = { Text(label) }
                    )
                }
            }

            Spacer(Modifier.height(8.dp))
        }
    }
}
