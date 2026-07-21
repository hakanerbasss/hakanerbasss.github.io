package com.wizaicorp.namazvakitleri.ui.screens

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.api.PexelsApi
import com.wizaicorp.namazvakitleri.data.ApiPrefs
import com.wizaicorp.namazvakitleri.data.HolyDays
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.PrayerTimes
import com.wizaicorp.namazvakitleri.data.QuoteData
import com.wizaicorp.namazvakitleri.util.ImageLoader
import kotlinx.coroutines.delay
import java.util.Calendar

@Composable
fun PrayerTimesContent(
    prayerTimes: PrayerTimes?,
    isLoading: Boolean,
    error: String?,
    isOffline: Boolean,
    onRefresh: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp)
    ) {
        Spacer(Modifier.height(12.dp))
        when {
            isLoading -> Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
            }
            error != null && prayerTimes == null -> ErrorCard(error, onRefresh)
            prayerTimes != null -> {
                if (isOffline) {
                    OfflineNotice()
                    Spacer(Modifier.height(8.dp))
                }
                DateCard(prayerTimes.date)
                Spacer(Modifier.height(12.dp))
                NextPrayerCard(prayerTimes)
                Spacer(Modifier.height(12.dp))
                PrayerList(prayerTimes)
                Spacer(Modifier.height(12.dp))
                TodayCard()
                Spacer(Modifier.height(12.dp))
            }
        }
    }
}

/** Gunun sozu + (Pexels anahtari girildiyse) gunun dini gorseli */
@Composable
private fun TodayCard() {
    val ctx = LocalContext.current
    val quote = remember { QuoteData.ofToday() }
    val pexelsKey = remember { ApiPrefs.getPexelsKey(ctx) }
    var bitmap by remember { mutableStateOf<Bitmap?>(null) }
    var photographer by remember { mutableStateOf("") }

    LaunchedEffect(pexelsKey) {
        if (pexelsKey.isNotBlank()) {
            try {
                val photo = PexelsApi.photoOfToday(pexelsKey)
                if (photo != null) {
                    photographer = photo.photographer
                    bitmap = ImageLoader.load(photo.src.large)
                }
            } catch (e: Exception) { /* gorsel yoksa sadece soz gosterilir */ }
        }
    }

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surfaceVariant
    ) {
        Column {
            bitmap?.let { bmp ->
                Image(
                    bitmap = bmp.asImageBitmap(),
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(170.dp)
                        .clip(RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp))
                )
            }
            Column(Modifier.padding(16.dp)) {
                Text(
                    Lang.get("quote_of_day"),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    "“${quote.text}”",
                    style = MaterialTheme.typography.bodyLarge,
                    fontStyle = FontStyle.Italic,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(6.dp))
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        quote.source,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.secondary
                    )
                    if (photographer.isNotEmpty() && bitmap != null) {
                        Text(
                            "Pexels / $photographer",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun OfflineNotice() {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(10.dp),
        color = MaterialTheme.colorScheme.secondary.copy(alpha = 0.2f)
    ) {
        Text(
            Lang.get("offline_cached"),
            modifier = Modifier.padding(10.dp),
            style = MaterialTheme.typography.labelMedium,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f)
        )
    }
}

@Composable
private fun DateCard(date: String) {
    val hijri = remember { HolyDays.hijriToday() }
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.primaryContainer
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = date,
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
                textAlign = TextAlign.Center
            )
            Text(
                text = hijri,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f),
                textAlign = TextAlign.Center
            )
        }
    }
}

@Composable
private fun NextPrayerCard(times: PrayerTimes) {
    val (label, timeStr) = remember(times) { nextPrayer(times) }
    var countdown by remember { mutableStateOf("") }
    var progress by remember { mutableFloatStateOf(0f) }
    LaunchedEffect(timeStr) {
        while (true) {
            countdown = remainingTime(timeStr)
            progress = intervalProgress(times, timeStr)
            delay(1000)
        }
    }
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.primary
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                Lang.get("next_prayer"),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.8f)
            )
            Spacer(Modifier.height(4.dp))
            Text(
                label,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onPrimary
            )
            Spacer(Modifier.height(6.dp))
            Text(
                "$countdown ${Lang.get("left")}",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.secondary
            )
            Spacer(Modifier.height(12.dp))
            LinearProgressIndicator(
                progress = { progress },
                modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.secondary,
                trackColor = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.2f)
            )
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
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = if (isPassed) 0.5f else 1f)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                name,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = if (!isPassed) FontWeight.SemiBold else FontWeight.Normal,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = alpha),
                modifier = Modifier.weight(1f)
            )
            Text(
                time,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary.copy(alpha = alpha)
            )
        }
    }
}

@Composable
private fun ErrorCard(error: String, onRetry: () -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.errorContainer
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(error, color = MaterialTheme.colorScheme.onErrorContainer, textAlign = TextAlign.Center)
            Spacer(Modifier.height(8.dp))
            Button(onClick = onRetry) { Text(Lang.get("retry")) }
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

private fun toMin(time: String): Int = try {
    val (h, m) = time.split(":").map { it.toInt() }
    h * 60 + m
} catch (e: Exception) { 0 }

/** Onceki vakitten siradaki vakte gecen surenin orani (0..1) */
private fun intervalProgress(t: PrayerTimes, nextTime: String): Float {
    val timesList = t.asList().map { it.second }
    val nowCal = Calendar.getInstance()
    val nowMin = nowCal.get(Calendar.HOUR_OF_DAY) * 60 + nowCal.get(Calendar.MINUTE)
    val nextMin = toMin(nextTime)
    val prevMin = timesList.map { toMin(it) }.filter { it <= nowMin }.maxOrNull()
        ?: (toMin(timesList.last()) - 24 * 60)
    var total = nextMin - prevMin
    if (total <= 0) total += 24 * 60
    var elapsed = nowMin - prevMin
    if (elapsed < 0) elapsed += 24 * 60
    return (elapsed.toFloat() / total).coerceIn(0f, 1f)
}

private fun remainingTime(target: String): String {
    val cal = Calendar.getInstance()
    val nowMin = cal.get(Calendar.HOUR_OF_DAY) * 60 + cal.get(Calendar.MINUTE)
    val (h, m) = target.split(":").map { it.toInt() }
    var diff = h * 60 + m - nowMin
    if (diff < 0) diff += 24 * 60
    val hours = diff / 60
    val mins = diff % 60
    val hs = Lang.get("h_short")
    val ms = Lang.get("m_short")
    return when {
        hours > 0 && mins > 0 -> "$hours $hs $mins $ms"
        hours > 0 -> "$hours $hs"
        else -> "$mins $ms"
    }
}
