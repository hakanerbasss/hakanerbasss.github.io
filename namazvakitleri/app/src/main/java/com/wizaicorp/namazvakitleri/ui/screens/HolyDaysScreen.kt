package com.wizaicorp.namazvakitleri.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.data.HolyDay
import com.wizaicorp.namazvakitleri.data.HolyDays
import com.wizaicorp.namazvakitleri.data.Lang
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun HolyDaysScreen(onBack: () -> Unit) {
    val days = remember { HolyDays.upcoming() }
    val locale = if (Lang.code == "tr") Locale("tr") else Locale.ENGLISH
    val fmt = remember { DateTimeFormatter.ofPattern("d MMMM yyyy, EEEE", locale) }

    FeatureScaffold(title = Lang.get("holy_days"), onBack = onBack) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            items(days) { day -> HolyDayCard(day, fmt, isNext = day == days.firstOrNull()) }
            item {
                Text(
                    Lang.get("holy_disclaimer"),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
        }
    }
}

@Composable
private fun HolyDayCard(day: HolyDay, fmt: DateTimeFormatter, isNext: Boolean) {
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = if (isNext) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    Lang.get(day.nameKey),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (isNext) MaterialTheme.colorScheme.onPrimary
                            else MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    day.date.format(fmt),
                    style = MaterialTheme.typography.bodySmall,
                    color = if (isNext) MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.8f)
                            else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )
            }
            val left = day.daysLeft
            Text(
                if (left == 0L) Lang.get("today")
                else "$left ${Lang.get("days_left")}",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = if (isNext) MaterialTheme.colorScheme.secondary
                        else MaterialTheme.colorScheme.primary
            )
        }
    }
}
