package com.wizaicorp.namazvakitleri.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.windowInsetsBottomHeight
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocationCity
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.BannerAd
import com.wizaicorp.namazvakitleri.data.PrayerTimes
import kotlinx.coroutines.delay
import java.util.Calendar

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PrayerTimesScreen(
    prayerTimes: PrayerTimes?,
    isLoading: Boolean,
    error: String?,
    onRefresh: () -> Unit,
    onCityClick: () -> Unit,
    onSettingsClick: () -> Unit = {}
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(prayerTimes?.city ?: "Namaz Vakitleri", fontWeight = FontWeight.Bold) },
                actions = {
                    IconButton(onClick = onSettingsClick) {
                        Icon(Icons.Default.Notifications, contentDescription = "Bildirim Ayarları")
                    }
                    IconButton(onClick = onCityClick) {
                        Icon(Icons.Default.LocationCity, contentDescription = "şehir seç")
                    }
                    IconButton(onClick = onRefresh, enabled = !isLoading) {
                        Icon(Icons.Default.Refresh, contentDescription = "Yenile")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor      = MaterialTheme.colorScheme.primary,
                    titleContentColor   = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        },
        bottomBar = {
            Column {
                BannerAd()
                androidx.compose.foundation.layout.Spacer(
                    Modifier.windowInsetsBottomHeight(androidx.compose.foundation.layout.WindowInsets.navigationBars)
                )
            }
        }
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp)
        ) {
            Spacer(Modifier.height(12.dp))
            when {
                isLoading -> Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                }
                error != null -> ErrorCard(error, onRefresh)
                prayerTimes != null -> {
                    DateCard(prayerTimes.date)
                    Spacer(Modifier.height(12.dp))
                    NextPrayerCard(prayerTimes)
                    Spacer(Modifier.height(12.dp))
                    PrayerList(prayerTimes)
                }
            }
        }
    }
}

@Composable
private fun DateCard(date: String) {
    Surface(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.primaryContainer) {
        Text(text = date, modifier = Modifier.padding(12.dp),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onPrimaryContainer,
            textAlign = TextAlign.Center)
    }
}

@Composable
private fun NextPrayerCard(times: PrayerTimes) {
    val (label, timeStr) = remember(times) { nextPrayer(times) }
    var countdown by remember { mutableStateOf("") }
    LaunchedEffect(timeStr) {
        while (true) { countdown = remainingTime(timeStr); delay(1000) }
    }
    Surface(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.primary) {
        Column(modifier = Modifier.padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("Sıradaki Vakit", style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.8f))
            Spacer(Modifier.height(4.dp))
            Text(label, style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onPrimary)
            Spacer(Modifier.height(6.dp))
            Text(timeStr, style = MaterialTheme.typography.displaySmall,
                fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.secondary)
            Spacer(Modifier.height(4.dp))
            Text("$countdown kaldı", style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.7f))
        }
    }
}

@Composable
private fun PrayerList(times: PrayerTimes) {
    val now = remember { currentTimeStr() }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        times.asList().forEach { (name, time) ->
            PrayerRow(name = name, time = time, isPassed = time <= now)
        }
    }
}

@Composable
private fun PrayerRow(name: String, time: String, isPassed: Boolean) {
    val alpha = if (isPassed) 0.5f else 1f
    Surface(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = if (isPassed) 0.5f else 1f)) {
        Row(modifier = Modifier.padding(horizontal = 20.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text(name, style = MaterialTheme.typography.titleMedium,
                fontWeight = if (!isPassed) FontWeight.SemiBold else FontWeight.Normal,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = alpha),
                modifier = Modifier.weight(1f))
            Text(time, style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary.copy(alpha = alpha))
        }
    }
}

@Composable
private fun ErrorCard(error: String, onRetry: () -> Unit) {
    Surface(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.errorContainer) {
        Column(modifier = Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(error, color = MaterialTheme.colorScheme.onErrorContainer, textAlign = TextAlign.Center)
            Spacer(Modifier.height(8.dp))
            Button(onClick = onRetry) { Text("Tekrar Dene") }
        }
    }
}

private fun currentTimeStr(): String {
    val cal = Calendar.getInstance()
    return "%02d:%02d".format(cal.get(Calendar.HOUR_OF_DAY), cal.get(Calendar.MINUTE))
}

private fun nextPrayer(t: PrayerTimes): Pair<String, String> {
    val now = currentTimeStr()
    return t.asList().firstOrNull { (_, time) -> time > now } ?: t.asList().first()
}

private fun remainingTime(target: String): String {
    val cal = Calendar.getInstance()
    val nowMin = cal.get(Calendar.HOUR_OF_DAY) * 60 + cal.get(Calendar.MINUTE)
    val (h, m) = target.split(":").map { it.toInt() }
    var diff = h * 60 + m - nowMin
    if (diff < 0) diff += 24 * 60
    return "%d:%02d".format(diff / 60, diff % 60)
}
