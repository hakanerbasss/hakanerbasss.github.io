package com.bluechip.finance.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.NotificationWorker
import com.bluechip.finance.data.NotificationSettingsManager
import com.bluechip.finance.data.SpecialDayManager

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NotificationSettingsScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    var settings by remember { mutableStateOf(NotificationSettingsManager.get(context)) }

    fun save() {
        NotificationSettingsManager.save(context, settings)
        NotificationWorker.schedule(context)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Bildirim Ayarlari", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, null) }
                }
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item { Spacer(Modifier.height(4.dp)) }

            // Bildirim saati
            item {
                Card(shape = RoundedCornerShape(12.dp)) {
                    Column(Modifier.padding(16.dp)) {
                        Text("Bildirim Saati", fontWeight = FontWeight.Bold, fontSize = 15.sp)
                        Spacer(Modifier.height(12.dp))
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("Saat:", fontSize = 14.sp)
                            var hourText by remember { mutableStateOf(settings.hour.toString().padStart(2, '0')) }
                            OutlinedTextField(
                                value = hourText,
                                onValueChange = {
                                    hourText = it
                                    it.toIntOrNull()?.let { h -> if (h in 0..23) { settings = settings.copy(hour = h); save() } }
                                },
                                modifier = Modifier.width(72.dp),
                                singleLine = true,
                                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Number),
                                label = { Text("Saat") }
                            )
                            Text(":", fontSize = 18.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                            var minuteText by remember { mutableStateOf(settings.minute.toString().padStart(2, '0')) }
                            OutlinedTextField(
                                value = minuteText,
                                onValueChange = {
                                    minuteText = it
                                    it.toIntOrNull()?.let { m -> if (m in 0..59) { settings = settings.copy(minute = m); save() } }
                                },
                                modifier = Modifier.width(72.dp),
                                singleLine = true,
                                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Number),
                                label = { Text("Dakika") }
                            )
                        }
                    }
                }
            }

            // Maaş bildirimi
            item {
                NotifToggleCard(
                    title = "Maas Gunu",
                    icon = Icons.Filled.AccountBalance,
                    enabled = settings.salaryEnabled,
                    daysBefore = settings.salaryDaysBefore,
                    onToggle = { settings = settings.copy(salaryEnabled = it); save() },
                    onDaysChange = { settings = settings.copy(salaryDaysBefore = it); save() }
                )
            }

            // Avans bildirimi
            item {
                NotifToggleCard(
                    title = "Avans Gunu",
                    icon = Icons.Filled.Payments,
                    enabled = settings.advanceEnabled,
                    daysBefore = settings.advanceDaysBefore,
                    onToggle = { settings = settings.copy(advanceEnabled = it); save() },
                    onDaysChange = { settings = settings.copy(advanceDaysBefore = it); save() }
                )
            }

            // Emekli maaşı
            item {
                NotifToggleCard(
                    title = "Emekli Maasi",
                    icon = Icons.Filled.ElderlyWoman,
                    enabled = settings.retirementEnabled,
                    daysBefore = settings.retirementDaysBefore,
                    onToggle = { settings = settings.copy(retirementEnabled = it); save() },
                    onDaysChange = { settings = settings.copy(retirementDaysBefore = it); save() }
                )
            }

            // Yan gelir
            item {
                NotifToggleCard(
                    title = "Yan Gelir",
                    icon = Icons.Filled.TrendingUp,
                    enabled = settings.sideIncomeEnabled,
                    daysBefore = settings.sideDaysBefore,
                    onToggle = { settings = settings.copy(sideIncomeEnabled = it); save() },
                    onDaysChange = { settings = settings.copy(sideDaysBefore = it); save() }
                )
            }

            // Ödemeler
            item {
                NotifToggleCard(
                    title = "Yaklasan Odemeler",
                    icon = Icons.Filled.CreditCard,
                    enabled = settings.paymentEnabled,
                    daysBefore = settings.paymentDaysBefore,
                    onToggle = { settings = settings.copy(paymentEnabled = it); save() },
                    onDaysChange = { settings = settings.copy(paymentDaysBefore = it); save() }
                )
            }
            item {
                // Özel günler
                val specialDays = remember { SpecialDayManager.getAll(context) }
                Card(shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)) {
                    Column(Modifier.padding(16.dp)) {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Filled.Celebration, null, modifier = Modifier.size(20.dp))
                                Spacer(Modifier.width(10.dp))
                                androidx.compose.material3.Text("Özel Günler", fontWeight = androidx.compose.ui.text.font.FontWeight.Medium, fontSize = 15.sp)
                            }
                            Switch(
                                checked = settings.specialDayEnabled,
                                onCheckedChange = { settings = settings.copy(specialDayEnabled = it); save() }
                            )
                        }
                        if (settings.specialDayEnabled) {
                            Spacer(Modifier.height(12.dp))
                            androidx.compose.material3.Text("Kaç gün önce gelsin?", fontSize = 13.sp, color = androidx.compose.ui.graphics.Color.Gray)
                            Spacer(Modifier.height(8.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                listOf(1, 2, 3, 5, 7).forEach { day ->
                                    FilterChip(
                                        selected = settings.specialDaysBefore == day,
                                        onClick = { settings = settings.copy(specialDaysBefore = day); save() },
                                        label = { androidx.compose.material3.Text("${day}g") }
                                    )
                                }
                            }
                            if (specialDays.isEmpty()) {
                                Spacer(Modifier.height(8.dp))
                                androidx.compose.material3.Text("Henüz özel gün eklenmedi.", fontSize = 12.sp, color = androidx.compose.ui.graphics.Color.Gray)
                            } else {
                                Spacer(Modifier.height(8.dp))
                                androidx.compose.material3.Text("${specialDays.size} özel gün için bildirim aktif.", fontSize = 12.sp, color = androidx.compose.ui.graphics.Color.Gray)
                            }
                        }
                    }
                }
            }

            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

@Composable
private fun NotifToggleCard(
    title: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    enabled: Boolean,
    daysBefore: Int,
    onToggle: (Boolean) -> Unit,
    onDaysChange: (Int) -> Unit
) {
    Card(shape = RoundedCornerShape(12.dp)) {
        Column(Modifier.padding(16.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(icon, null, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(10.dp))
                    Text(title, fontWeight = FontWeight.Medium, fontSize = 15.sp)
                }
                Switch(checked = enabled, onCheckedChange = onToggle)
            }
            if (enabled) {
                Spacer(Modifier.height(12.dp))
                Text("Kac gun once gelsin?", fontSize = 13.sp, color = Color.Gray)
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(1, 2, 3, 5, 7).forEach { day ->
                        FilterChip(
                            selected = daysBefore == day,
                            onClick = { onDaysChange(day) },
                            label = { Text("${day}g") }
                        )
                    }
                }
            }
        }
    }
}
