package com.bluechip.finance.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.data.SpecialDay
import com.bluechip.finance.data.SpecialDayManager

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SpecialDaysScreen(onBack: () -> Unit, autoAdd: Boolean = false) {
    val context = LocalContext.current
    var days by remember { mutableStateOf(SpecialDayManager.getAll(context)) }
    var showSheet by remember { mutableStateOf(autoAdd) }
    var editDay by remember { mutableStateOf<SpecialDay?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Özel Günler", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, null) }
                },
                actions = {
                    IconButton(onClick = { editDay = null; showSheet = true }) {
                        Icon(Icons.Filled.Add, null)
                    }
                }
            )
        }
    ) { padding ->
        if (days.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Filled.Celebration, null, modifier = Modifier.size(64.dp))
                    Spacer(Modifier.height(12.dp))
                    Text("Henüz özel gün yok", fontSize = 16.sp)
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = { editDay = null; showSheet = true }) { Text("Ekle") }
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                item { Spacer(Modifier.height(4.dp)) }
                items(days, key = { it.id }) { day ->
                    val remaining = SpecialDayManager.daysUntil(day.day, day.month)
                    Card(shape = RoundedCornerShape(12.dp)) {
                        Row(
                            Modifier.fillMaxWidth().padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            // Gün sayacı
                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                                modifier = Modifier.size(52.dp)
                            ) {
                                Column(
                                    Modifier.fillMaxSize(),
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                    verticalArrangement = Arrangement.Center
                                ) {
                                    Text(
                                        if (remaining == 0) "🎉" else "$remaining",
                                        fontWeight = FontWeight.Bold,
                                        fontSize = if (remaining == 0) 22.sp else 18.sp,
                                        color = MaterialTheme.colorScheme.primary
                                    )
                                    if (remaining > 0) Text("gün", fontSize = 10.sp, color = MaterialTheme.colorScheme.primary)
                                }
                            }
                            Spacer(Modifier.width(14.dp))
                            Column(Modifier.weight(1f)) {
                                Text(day.title, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                                if (day.subtitle.isNotEmpty()) {
                                    Text(day.subtitle, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                                }
                                Text("${day.day}/${day.month}", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                            }
                            Row {
                                IconButton(onClick = { editDay = day; showSheet = true }) {
                                    Icon(Icons.Filled.Edit, null, modifier = Modifier.size(18.dp))
                                }
                                IconButton(onClick = {
                                    SpecialDayManager.delete(context, day.id)
                                    days = SpecialDayManager.getAll(context)
                                }) {
                                    Icon(Icons.Filled.Delete, null, modifier = Modifier.size(18.dp))
                                }
                            }
                        }
                    }
                }
                item { Spacer(Modifier.height(16.dp)) }
            }
        }
    }

    if (showSheet) {
        SpecialDaySheet(
            initial = editDay,
            onDismiss = { showSheet = false },
            onSave = { day ->
                SpecialDayManager.save(context, day)
                days = SpecialDayManager.getAll(context)
                showSheet = false
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SpecialDaySheet(
    initial: SpecialDay?,
    onDismiss: () -> Unit,
    onSave: (SpecialDay) -> Unit
) {
    var title    by remember { mutableStateOf(initial?.title ?: "") }
    var subtitle by remember { mutableStateOf(initial?.subtitle ?: "") }
    var dayText  by remember { mutableStateOf(initial?.day?.toString() ?: "") }
    var monthText by remember { mutableStateOf(initial?.month?.toString() ?: "") }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 32.dp)) {
            Text(
                if (initial == null) "Özel Gün Ekle" else "Düzenle",
                fontWeight = FontWeight.Bold, fontSize = 18.sp
            )
            Spacer(Modifier.height(16.dp))

            OutlinedTextField(
                value = title,
                onValueChange = { title = it },
                label = { Text("Başlık (örn: Doğum Günü, Yıldönümü)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = subtitle,
                onValueChange = { subtitle = it },
                label = { Text("Alt Başlık (örn: Annem, Eşim)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = dayText,
                    onValueChange = { dayText = it },
                    label = { Text("Gün") },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
                )
                OutlinedTextField(
                    value = monthText,
                    onValueChange = { monthText = it },
                    label = { Text("Ay") },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
                )
            }
            Spacer(Modifier.height(20.dp))
            Button(
                onClick = {
                    val d = dayText.toIntOrNull() ?: return@Button
                    val m = monthText.toIntOrNull() ?: return@Button
                    if (d < 1 || d > 31 || m < 1 || m > 12) return@Button
                    if (title.isBlank()) return@Button
                    onSave(SpecialDay(
                        id = initial?.id ?: java.util.UUID.randomUUID().toString(),
                        title = title.trim(),
                        subtitle = subtitle.trim(),
                        day = d,
                        month = m
                    ))
                },
                modifier = Modifier.fillMaxWidth()
            ) { Text("Kaydet") }
        }
    }
}
