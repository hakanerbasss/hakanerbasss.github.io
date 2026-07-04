package com.bluechip.finance.ui.screens

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccessTime
import androidx.compose.material.icons.filled.AttachMoney
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.TrendingUp
import androidx.compose.material.icons.filled.WorkOff
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.ui.components.SectionHeader
import com.bluechip.finance.ui.components.formatMoney
import com.bluechip.finance.ui.theme.FuchsiaAccent
import com.bluechip.finance.ui.theme.GradientPrimary
import com.bluechip.finance.ui.theme.IndigoDeep
import com.bluechip.finance.ui.theme.LocalAppColors
import com.bluechip.finance.ui.theme.PurplePrimary
import com.bluechip.finance.ui.theme.SuccessGreen
import com.bluechip.finance.ui.theme.WarningOrange
import kotlinx.coroutines.delay
import java.util.Calendar

private val motivationalQuotes = listOf(
    "\"Çalışmak, hayatın en büyük zevklerinden biridir.\" — Mustafa Kemal Atatürk",
    "\"Başarı, her gün tekrarlanan küçük çabaların toplamıdır.\" — Robert Collier",
    "\"Bugün yaptığın fedakarlıklar, yarınki başarılarının temelidir.\"",
    "\"Emek olmadan zafer olmaz. Her saniye seni hedefe yaklaştırıyor.\"",
    "\"Büyük işler zaman alır, ama her geçen saniye seni oraya taşıyor.\""
)

@Composable
fun EarningsTickerScreen() {
    val context = LocalContext.current
    val colors = LocalAppColors.current
    val scrollState = rememberScrollState()

    val profile = remember { ProfileManager(context).load() }
    val hasProfile = profile.isLoggedIn && (profile.grossSalary > 0 || profile.netSalary > 0)

    val netSalary = remember(profile) {
        when {
            profile.netSalary > 0 -> profile.netSalary
            profile.grossSalary > 0 -> profile.grossSalary * 0.80
            else -> 0.0
        }
    }

    // perSecond = netSalary / 22 workdays / 8 hours / 3600 seconds
    val perSecond = remember(netSalary) {
        if (netSalary > 0) netSalary / 22.0 / 8.0 / 3600.0 else 0.0
    }

    var todayEarnings by remember { mutableDoubleStateOf(0.0) }
    var weekEarnings by remember { mutableDoubleStateOf(0.0) }
    var monthEarnings by remember { mutableDoubleStateOf(0.0) }
    var isWorkingHours by remember { mutableStateOf(false) }
    var isAfterWork by remember { mutableStateOf(false) }

    val randomQuote = remember { motivationalQuotes.random() }

    // Pulse animation for the main ticker
    val pulseTransition = rememberInfiniteTransition(label = "pulse")
    val pulseScale by pulseTransition.animateFloat(
        initialValue = 1f,
        targetValue = 1.04f,
        animationSpec = infiniteRepeatable(
            animation = tween(900, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulseScale"
    )

    LaunchedEffect(Unit) {
        while (true) {
            val now = Calendar.getInstance()
            val hour = now.get(Calendar.HOUR_OF_DAY)
            val minute = now.get(Calendar.MINUTE)
            val second = now.get(Calendar.SECOND)
            val dayOfWeek = now.get(Calendar.DAY_OF_WEEK)

            val isWeekend = dayOfWeek == Calendar.SATURDAY || dayOfWeek == Calendar.SUNDAY
            val workStartSeconds = 9 * 3600
            val workEndSeconds = 18 * 3600
            val nowSeconds = hour * 3600 + minute * 60 + second

            isWorkingHours = !isWeekend && nowSeconds in workStartSeconds until workEndSeconds
            isAfterWork = !isWeekend && nowSeconds >= workEndSeconds

            val secondsWorkedToday = when {
                isWorkingHours -> nowSeconds - workStartSeconds
                isAfterWork -> 8 * 3600
                else -> 0
            }
            todayEarnings = secondsWorkedToday * perSecond

            // Weekly earnings: completed weekdays * full day + today
            val weekdayIndex = when (dayOfWeek) {
                Calendar.MONDAY -> 1
                Calendar.TUESDAY -> 2
                Calendar.WEDNESDAY -> 3
                Calendar.THURSDAY -> 4
                Calendar.FRIDAY -> 5
                Calendar.SATURDAY -> 5
                Calendar.SUNDAY -> 0
                else -> 0
            }
            val completedDays = if (!isWeekend && weekdayIndex > 1) weekdayIndex - 1 else if (isWeekend) weekdayIndex else 0
            weekEarnings = completedDays * 8.0 * 3600.0 * perSecond + todayEarnings

            // Monthly earnings: (dayOfMonth - 1) full days capped at 22 + today
            val dayOfMonth = now.get(Calendar.DAY_OF_MONTH)
            val workedFullDays = (dayOfMonth - 1).coerceAtMost(22)
            monthEarnings = workedFullDays * 8.0 * 3600.0 * perSecond + todayEarnings

            delay(1000L)
        }
    }

    val annualTarget = remember(netSalary) { netSalary * 12.0 }
    val monthProgress = remember {
        val month = Calendar.getInstance().get(Calendar.MONTH) + 1
        (month.toFloat() / 12f).coerceIn(0f, 1f)
    }
    val currentMonth = remember { Calendar.getInstance().get(Calendar.MONTH) + 1 }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .verticalScroll(scrollState)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        SectionHeader(title = "ANLIK KAZANÇ SAYACI", icon = Icons.Default.AttachMoney)

        if (!hasProfile) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                elevation = CardDefaults.cardElevation(4.dp)
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Icon(
                        Icons.Default.Person,
                        contentDescription = null,
                        tint = PurplePrimary,
                        modifier = Modifier.size(48.dp)
                    )
                    Text(
                        "Maaş bilgisi bulunamadı",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = colors.textPrimary
                    )
                    Text(
                        "Anlık kazanç sayacını kullanmak için lütfen Profil ekranına giderek brüt veya net maaşınızı girin.",
                        fontSize = 14.sp,
                        color = colors.textSecondary,
                        lineHeight = 20.sp
                    )
                }
            }
            return@Column
        }

        // Card 1: Anlık Kazanç
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            elevation = CardDefaults.cardElevation(6.dp)
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(32.dp)
                            .background(SuccessGreen.copy(alpha = 0.15f), RoundedCornerShape(10.dp)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            Icons.Default.TrendingUp,
                            contentDescription = null,
                            tint = SuccessGreen,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "Anlık Kazanç",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = colors.textPrimary
                    )
                }

                Spacer(Modifier.height(16.dp))

                Text(
                    text = "₺${formatMoney(todayEarnings)}",
                    fontSize = 36.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = SuccessGreen,
                    modifier = Modifier.graphicsLayer {
                        scaleX = if (isWorkingHours) pulseScale else 1f
                        scaleY = if (isWorkingHours) pulseScale else 1f
                    }
                )

                Spacer(Modifier.height(6.dp))

                Text(
                    text = "saniyede ₺${"%.4f".format(perSecond)}",
                    fontSize = 12.sp,
                    color = colors.textSecondary
                )

                if (!isWorkingHours && !isAfterWork) {
                    Spacer(Modifier.height(12.dp))
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(WarningOrange.copy(alpha = 0.10f), RoundedCornerShape(10.dp))
                            .padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.WorkOff,
                            contentDescription = null,
                            tint = WarningOrange,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "Mesai dışı — sonraki çalışma günü sayılmıyor",
                            fontSize = 12.sp,
                            color = WarningOrange
                        )
                    }
                }

                if (isAfterWork) {
                    Spacer(Modifier.height(12.dp))
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(IndigoDeep.copy(alpha = 0.10f), RoundedCornerShape(10.dp))
                            .padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.AccessTime,
                            contentDescription = null,
                            tint = IndigoDeep,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "Mesai bitti — günlük kazanç donduruldu",
                            fontSize = 12.sp,
                            color = IndigoDeep
                        )
                    }
                }
            }
        }

        // Cards 2 & 3: Bu Hafta + Bu Ay in a row
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Card 2: Bu Hafta
            Card(
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = colors.cardGray),
                elevation = CardDefaults.cardElevation(4.dp)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(28.dp)
                            .background(FuchsiaAccent.copy(alpha = 0.15f), RoundedCornerShape(8.dp)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            Icons.Default.CalendarMonth,
                            contentDescription = null,
                            tint = FuchsiaAccent,
                            modifier = Modifier.size(16.dp)
                        )
                    }
                    Text(
                        "Bu Hafta",
                        fontSize = 13.sp,
                        color = colors.textSecondary,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        "₺${formatMoney(weekEarnings)}",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.ExtraBold,
                        color = FuchsiaAccent
                    )
                }
            }

            // Card 3: Bu Ay
            Card(
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = colors.cardGray),
                elevation = CardDefaults.cardElevation(4.dp)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(28.dp)
                            .background(PurplePrimary.copy(alpha = 0.15f), RoundedCornerShape(8.dp)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            Icons.Default.Star,
                            contentDescription = null,
                            tint = PurplePrimary,
                            modifier = Modifier.size(16.dp)
                        )
                    }
                    Text(
                        "Bu Ay",
                        fontSize = 13.sp,
                        color = colors.textSecondary,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        "₺${formatMoney(monthEarnings)}",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.ExtraBold,
                        color = PurplePrimary
                    )
                }
            }
        }

        // Card 4: Yıllık Hedef
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            elevation = CardDefaults.cardElevation(4.dp)
        ) {
            Column(modifier = Modifier.padding(18.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(28.dp)
                            .background(IndigoDeep.copy(alpha = 0.15f), RoundedCornerShape(8.dp)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            Icons.Default.EmojiEvents,
                            contentDescription = null,
                            tint = IndigoDeep,
                            modifier = Modifier.size(16.dp)
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "Yıllık Hedef",
                        fontSize = 14.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = colors.textPrimary,
                        modifier = Modifier.weight(1f)
                    )
                    Text(
                        "₺${formatMoney(annualTarget)}",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.ExtraBold,
                        color = IndigoDeep
                    )
                }

                Spacer(Modifier.height(12.dp))

                Text(
                    text = "Yılın $currentMonth. ayı — %${"%.0f".format(monthProgress * 100)} tamamlandı",
                    fontSize = 12.sp,
                    color = colors.textSecondary
                )
                Spacer(Modifier.height(6.dp))
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(10.dp)
                        .clip(RoundedCornerShape(5.dp))
                        .background(IndigoDeep.copy(alpha = 0.12f))
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth(monthProgress)
                            .height(10.dp)
                            .background(GradientPrimary, RoundedCornerShape(5.dp))
                    )
                }
            }
        }

        // Motivational Quote
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardGray),
            elevation = CardDefaults.cardElevation(2.dp)
        ) {
            Row(
                modifier = Modifier.padding(16.dp),
                verticalAlignment = Alignment.Top
            ) {
                Text(
                    text = "💡",
                    fontSize = 20.sp
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    text = randomQuote,
                    fontSize = 13.sp,
                    color = colors.textSecondary,
                    fontStyle = FontStyle.Italic,
                    lineHeight = 19.sp
                )
            }
        }

        Spacer(Modifier.height(16.dp))
    }
}
