package com.wizaicorp.namazvakitleri.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
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
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.ZikirPrefs

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

    val zikirKey = ZikirPrefs.zikirKeys[selected]
    val done = target > 0 && count >= target

    fun tap() {
        count++
        ZikirPrefs.setCount(ctx, zikirKey, count)
        ZikirPrefs.addTotal(ctx)
        total = ZikirPrefs.getTotal(ctx)
        haptic.performHapticFeedback(
            if (target > 0 && count == target) HapticFeedbackType.LongPress
            else HapticFeedbackType.TextHandleMove
        )
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

            Spacer(Modifier.height(8.dp))

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
