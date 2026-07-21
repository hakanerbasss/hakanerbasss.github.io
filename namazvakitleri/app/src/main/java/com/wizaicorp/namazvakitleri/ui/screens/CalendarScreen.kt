package com.wizaicorp.namazvakitleri.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.api.AladhanApi
import com.wizaicorp.namazvakitleri.api.CalendarDayItem
import com.wizaicorp.namazvakitleri.data.City
import com.wizaicorp.namazvakitleri.data.Lang
import kotlinx.coroutines.launch
import java.util.Calendar as JCalendar

@Composable
fun CalendarContent(city: City, modifier: Modifier = Modifier) {
    val scope = rememberCoroutineScope()
    val now   = remember { JCalendar.getInstance() }

    var year     by remember { mutableIntStateOf(now.get(JCalendar.YEAR)) }
    var month    by remember { mutableIntStateOf(now.get(JCalendar.MONTH) + 1) }
    var days     by remember { mutableStateOf<List<CalendarDayItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var error    by remember { mutableStateOf<String?>(null) }

    val todayYear  = remember { now.get(JCalendar.YEAR) }
    val todayMonth = remember { now.get(JCalendar.MONTH) + 1 }
    val todayDay   = remember { now.get(JCalendar.DAY_OF_MONTH) }

    val monthNames = (1..12).map { Lang.get("month_$it") }

    fun loadCalendar() {
        scope.launch {
            isLoading = true
            error     = null
            try {
                days = AladhanApi.getMonthlyTimes(city.apiName, city.country, year, month)
            } catch (e: Exception) {
                error = Lang.get("err_calendar")
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(city.apiName, year, month) { loadCalendar() }

    Column(modifier = modifier.fillMaxSize()) {

        // Month navigation header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment     = Alignment.CenterVertically
        ) {
            TextButton(onClick = {
                if (month == 1) { month = 12; year-- } else month--
            }) {
                Text("<<")
            }

            Text(
                text       = "${monthNames[month - 1]} $year",
                style      = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            TextButton(onClick = {
                if (month == 12) { month = 1; year++ } else month++
            }) {
                Text(">>")
            }
        }

        when {
            isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
            }
            error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(error!!, color = MaterialTheme.colorScheme.error)
            }
            else -> LazyColumn(
                modifier        = Modifier.fillMaxSize(),
                contentPadding  = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(days) { day ->
                    val isToday = year == todayYear && month == todayMonth && day.dayNum == todayDay
                    CalendarDayCard(day = day, isToday = isToday)
                }
            }
        }
    }
}

@Composable
private fun CalendarDayCard(day: CalendarDayItem, isToday: Boolean) {
    val fridayGold = Color(0xFFD4AF37)
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape    = RoundedCornerShape(8.dp),
        color    = if (isToday) MaterialTheme.colorScheme.primaryContainer
                   else MaterialTheme.colorScheme.surfaceVariant
    ) {
        Row(
            modifier          = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Left: day number, weekday, hijri date
            Column(modifier = Modifier.width(80.dp)) {
                Text(
                    text       = day.dayNum.toString(),
                    style      = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color      = if (isToday) MaterialTheme.colorScheme.onPrimaryContainer
                                 else MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text  = if (Lang.code == "tr") day.weekdayTr else day.weekdayEn,
                    style = MaterialTheme.typography.bodySmall,
                    color = when {
                        day.weekdayEn == "Friday" -> fridayGold
                        isToday -> MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
                        else    -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
                    }
                )
                Text(
                    text  = day.hijriDate,
                    style = MaterialTheme.typography.labelSmall,
                    color = if (isToday) MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.6f)
                            else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                )
            }

            Spacer(Modifier.width(8.dp))

            // Right: prayer times in 2-column grid
            Row(modifier = Modifier.weight(1f)) {
                // Left column: İmsak, Öğle, Akşam
                Column(
                    modifier  = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(3.dp)
                ) {
                    PrayerTimeEntry(Lang.get("p_imsak"),  day.times.imsak,  isToday)
                    PrayerTimeEntry(Lang.get("p_ogle"),   day.times.ogle,   isToday)
                    PrayerTimeEntry(Lang.get("p_aksam"),  day.times.aksam,  isToday)
                }
                // Right column: Güneş, İkindi, Yatsı
                Column(
                    modifier  = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(3.dp)
                ) {
                    PrayerTimeEntry(Lang.get("p_gunes"),  day.times.gunes,  isToday)
                    PrayerTimeEntry(Lang.get("p_ikindi"), day.times.ikindi, isToday)
                    PrayerTimeEntry(Lang.get("p_yatsi"),  day.times.yatsi,  isToday)
                }
            }
        }
    }
}

@Composable
private fun PrayerTimeEntry(name: String, time: String, isToday: Boolean) {
    val textColor = if (isToday) MaterialTheme.colorScheme.onPrimaryContainer
                   else MaterialTheme.colorScheme.onSurfaceVariant
    Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(
            text  = name,
            style = MaterialTheme.typography.labelSmall,
            color = textColor.copy(alpha = 0.65f)
        )
        Text(
            text       = time,
            style      = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color      = textColor
        )
    }
}
