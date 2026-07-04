package com.bluechip.finance.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
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
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.TrendingUp
import androidx.compose.material.icons.filled.WorkOutline
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.ui.components.SectionHeader
import com.bluechip.finance.ui.components.formatMoney
import com.bluechip.finance.ui.theme.FuchsiaAccent
import com.bluechip.finance.ui.theme.GradientButton
import com.bluechip.finance.ui.theme.IndigoDeep
import com.bluechip.finance.ui.theme.LocalAppColors
import com.bluechip.finance.ui.theme.PurplePrimary
import com.bluechip.finance.ui.theme.SuccessGreen
import com.bluechip.finance.ui.theme.WarningOrange
import com.bluechip.finance.ui.theme.ErrorRed

// Triple = (min, median, max) in monthly gross TL
private val salaryTable: Map<String, Triple<Int, Int, Int>> = linkedMapOf(
    "Yazılım Geliştirici" to Triple(45000, 85000, 160000),
    "Veri Bilimci / AI" to Triple(50000, 95000, 180000),
    "Muhasebe Uzmanı" to Triple(24000, 40000, 70000),
    "Mali Müşavir / CPA" to Triple(30000, 55000, 100000),
    "İnşaat Mühendisi" to Triple(28000, 52000, 95000),
    "Makine / Elektrik Müh." to Triple(28000, 55000, 105000),
    "Öğretmen / Akademisyen" to Triple(22000, 36000, 60000),
    "Doktor / Uzman Hekim" to Triple(40000, 80000, 150000),
    "Hemşire / Sağlık Tek." to Triple(22000, 35000, 58000),
    "Avukat" to Triple(28000, 60000, 130000),
    "Mimar / İç Mimar" to Triple(24000, 46000, 85000),
    "Eczacı / Veteriner" to Triple(28000, 50000, 95000),
    "Satış / Müşteri Tem." to Triple(20000, 36000, 65000),
    "Pazarlama Uzmanı" to Triple(24000, 44000, 80000),
    "İnsan Kaynakları" to Triple(22000, 38000, 68000),
    "Grafik / UI Tasarımcı" to Triple(20000, 38000, 70000),
    "Proje Yöneticisi" to Triple(35000, 70000, 130000),
    "Yönetici / Direktör" to Triple(50000, 100000, 200000),
    "Usta / Teknisyen" to Triple(18000, 28000, 48000),
    "Diğer" to Triple(18000, 30000, 55000)
)

private val cityMultipliers: Map<String, Double> = linkedMapOf(
    "Büyükşehir (İstanbul/Ankara/İzmir)" to 1.0,
    "Orta Şehir" to 0.85,
    "Küçük Şehir" to 0.72
)

private val experienceMultipliers: Map<String, Double> = linkedMapOf(
    "0-2 yıl" to 0.82,
    "3-5 yıl" to 1.0,
    "6-10 yıl" to 1.20,
    "11+ yıl" to 1.45
)

private data class CoachResult(
    val adjustedMin: Int,
    val adjustedMedian: Int,
    val adjustedMax: Int,
    val userSalary: Double?,
    val percentOfMedian: Double?,
    val salaryStatus: SalaryStatus
)

private enum class SalaryStatus { BELOW_80, BETWEEN_80_100, AT_OR_ABOVE }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SalaryCoachScreen() {
    val colors = LocalAppColors.current
    val scrollState = rememberScrollState()

    val jobCategories = remember { salaryTable.keys.toList() }
    val cityOptions = remember { cityMultipliers.keys.toList() }
    val experienceOptions = remember { experienceMultipliers.keys.toList() }

    var selectedJob by remember { mutableStateOf(jobCategories.first()) }
    var selectedCity by remember { mutableStateOf(cityOptions.first()) }
    var selectedExperience by remember { mutableStateOf(experienceOptions[1]) }
    var currentSalaryInput by remember { mutableStateOf("") }

    var jobExpanded by remember { mutableStateOf(false) }
    var cityExpanded by remember { mutableStateOf(false) }
    var expExpanded by remember { mutableStateOf(false) }

    var result by remember { mutableStateOf<CoachResult?>(null) }

    fun analyze() {
        val base = salaryTable[selectedJob] ?: return
        val cityMult = cityMultipliers[selectedCity] ?: 1.0
        val expMult = experienceMultipliers[selectedExperience] ?: 1.0
        val totalMult = cityMult * expMult

        val adjMin = (base.first * totalMult).toInt()
        val adjMedian = (base.second * totalMult).toInt()
        val adjMax = (base.third * totalMult).toInt()

        val userSalary = currentSalaryInput.toDoubleOrNull()
        val percentOfMedian = if (userSalary != null && adjMedian > 0) {
            (userSalary / adjMedian) * 100.0
        } else null

        val status = when {
            percentOfMedian == null -> SalaryStatus.AT_OR_ABOVE
            percentOfMedian < 80.0 -> SalaryStatus.BELOW_80
            percentOfMedian < 100.0 -> SalaryStatus.BETWEEN_80_100
            else -> SalaryStatus.AT_OR_ABOVE
        }

        result = CoachResult(adjMin, adjMedian, adjMax, userSalary, percentOfMedian, status)
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .verticalScroll(scrollState)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        SectionHeader(title = "MAAŞ KOÇU", icon = Icons.Default.TrendingUp)

        // Info card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardGray),
            elevation = CardDefaults.cardElevation(0.dp)
        ) {
            Row(
                modifier = Modifier.padding(14.dp),
                verticalAlignment = Alignment.Top
            ) {
                Text("💼", fontSize = 18.sp)
                Spacer(Modifier.width(10.dp))
                Text(
                    "Sektörünüzde adil bir maaş alıp almadığınızı öğrenin ve müzakere stratejinizi belirleyin.",
                    fontSize = 13.sp,
                    color = colors.textSecondary,
                    lineHeight = 19.sp
                )
            }
        }

        // Job Category Dropdown
        ExposedDropdownMenuBox(
            expanded = jobExpanded,
            onExpandedChange = { jobExpanded = it }
        ) {
            OutlinedTextField(
                value = selectedJob,
                onValueChange = {},
                readOnly = true,
                label = { Text("Meslek / Sektör", fontSize = 13.sp) },
                trailingIcon = {
                    Icon(
                        if (jobExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = null,
                        tint = PurplePrimary
                    )
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(),
                shape = RoundedCornerShape(14.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = PurplePrimary,
                    unfocusedBorderColor = PurplePrimary.copy(alpha = 0.3f),
                    focusedContainerColor = colors.cardBg,
                    unfocusedContainerColor = colors.cardBg,
                    focusedTextColor = colors.textPrimary,
                    unfocusedTextColor = colors.textPrimary,
                    focusedLabelColor = PurplePrimary,
                    unfocusedLabelColor = colors.textSecondary
                )
            )
            ExposedDropdownMenu(
                expanded = jobExpanded,
                onDismissRequest = { jobExpanded = false },
                modifier = Modifier.background(colors.cardBg)
            ) {
                jobCategories.forEach { job ->
                    DropdownMenuItem(
                        text = {
                            Text(
                                job,
                                color = if (job == selectedJob) PurplePrimary else colors.textPrimary,
                                fontWeight = if (job == selectedJob) FontWeight.SemiBold else FontWeight.Normal,
                                fontSize = 14.sp
                            )
                        },
                        onClick = {
                            selectedJob = job
                            jobExpanded = false
                            result = null
                        },
                        contentPadding = ExposedDropdownMenuDefaults.ItemContentPadding
                    )
                }
            }
        }

        // City Dropdown
        ExposedDropdownMenuBox(
            expanded = cityExpanded,
            onExpandedChange = { cityExpanded = it }
        ) {
            OutlinedTextField(
                value = selectedCity,
                onValueChange = {},
                readOnly = true,
                label = { Text("Şehir Tipi", fontSize = 13.sp) },
                trailingIcon = {
                    Icon(
                        if (cityExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = null,
                        tint = PurplePrimary
                    )
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(),
                shape = RoundedCornerShape(14.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = PurplePrimary,
                    unfocusedBorderColor = PurplePrimary.copy(alpha = 0.3f),
                    focusedContainerColor = colors.cardBg,
                    unfocusedContainerColor = colors.cardBg,
                    focusedTextColor = colors.textPrimary,
                    unfocusedTextColor = colors.textPrimary,
                    focusedLabelColor = PurplePrimary,
                    unfocusedLabelColor = colors.textSecondary
                )
            )
            ExposedDropdownMenu(
                expanded = cityExpanded,
                onDismissRequest = { cityExpanded = false },
                modifier = Modifier.background(colors.cardBg)
            ) {
                cityOptions.forEach { city ->
                    DropdownMenuItem(
                        text = {
                            Text(
                                city,
                                color = if (city == selectedCity) PurplePrimary else colors.textPrimary,
                                fontWeight = if (city == selectedCity) FontWeight.SemiBold else FontWeight.Normal,
                                fontSize = 14.sp
                            )
                        },
                        onClick = {
                            selectedCity = city
                            cityExpanded = false
                            result = null
                        },
                        contentPadding = ExposedDropdownMenuDefaults.ItemContentPadding
                    )
                }
            }
        }

        // Experience Dropdown
        ExposedDropdownMenuBox(
            expanded = expExpanded,
            onExpandedChange = { expExpanded = it }
        ) {
            OutlinedTextField(
                value = selectedExperience,
                onValueChange = {},
                readOnly = true,
                label = { Text("Deneyim", fontSize = 13.sp) },
                trailingIcon = {
                    Icon(
                        if (expExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = null,
                        tint = PurplePrimary
                    )
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(),
                shape = RoundedCornerShape(14.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = PurplePrimary,
                    unfocusedBorderColor = PurplePrimary.copy(alpha = 0.3f),
                    focusedContainerColor = colors.cardBg,
                    unfocusedContainerColor = colors.cardBg,
                    focusedTextColor = colors.textPrimary,
                    unfocusedTextColor = colors.textPrimary,
                    focusedLabelColor = PurplePrimary,
                    unfocusedLabelColor = colors.textSecondary
                )
            )
            ExposedDropdownMenu(
                expanded = expExpanded,
                onDismissRequest = { expExpanded = false },
                modifier = Modifier.background(colors.cardBg)
            ) {
                experienceOptions.forEach { exp ->
                    DropdownMenuItem(
                        text = {
                            Text(
                                exp,
                                color = if (exp == selectedExperience) PurplePrimary else colors.textPrimary,
                                fontWeight = if (exp == selectedExperience) FontWeight.SemiBold else FontWeight.Normal,
                                fontSize = 14.sp
                            )
                        },
                        onClick = {
                            selectedExperience = exp
                            expExpanded = false
                            result = null
                        },
                        contentPadding = ExposedDropdownMenuDefaults.ItemContentPadding
                    )
                }
            }
        }

        // Current salary input (optional)
        OutlinedTextField(
            value = currentSalaryInput,
            onValueChange = { v ->
                if (v.isEmpty() || v.matches(Regex("^\\d*\\.?\\d{0,2}$"))) {
                    currentSalaryInput = v
                    result = null
                }
            },
            label = { Text("Mevcut Brüt Maaşınız (opsiyonel)", fontSize = 13.sp) },
            placeholder = { Text("Örn: 45000", color = colors.textSecondary, fontSize = 13.sp) },
            leadingIcon = {
                Box(
                    modifier = Modifier
                        .size(36.dp)
                        .background(GradientButton, RoundedCornerShape(10.dp)),
                    contentAlignment = Alignment.Center
                ) {
                    Text("₺", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = Color.White)
                }
            },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            shape = RoundedCornerShape(14.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = PurplePrimary,
                unfocusedBorderColor = PurplePrimary.copy(alpha = 0.3f),
                focusedContainerColor = colors.cardBg,
                unfocusedContainerColor = colors.cardBg,
                focusedTextColor = colors.textPrimary,
                unfocusedTextColor = colors.textPrimary,
                focusedLabelColor = PurplePrimary,
                unfocusedLabelColor = colors.textSecondary
            )
        )

        // Analyze button
        Button(
            onClick = { analyze() },
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp),
            shape = RoundedCornerShape(14.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = PurplePrimary,
                contentColor = Color.White
            )
        ) {
            Icon(Icons.Default.School, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text(
                "ANALİZ ET",
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.sp
            )
        }

        // Result card
        AnimatedVisibility(
            visible = result != null,
            enter = fadeIn() + expandVertically(),
            exit = fadeOut() + shrinkVertically()
        ) {
            val r = result
            if (r != null) {
                ResultCoachCard(result = r)
            }
        }

        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun ResultCoachCard(result: CoachResult) {
    val colors = LocalAppColors.current

    val barColor: Color = when (result.salaryStatus) {
        SalaryStatus.AT_OR_ABOVE -> SuccessGreen
        SalaryStatus.BETWEEN_80_100 -> WarningOrange
        SalaryStatus.BELOW_80 -> ErrorRed
    }

    val statusEmoji = when (result.salaryStatus) {
        SalaryStatus.AT_OR_ABOVE -> "✅"
        SalaryStatus.BETWEEN_80_100 -> "⚠️"
        SalaryStatus.BELOW_80 -> "❌"
    }

    val tips: List<String> = when (result.salaryStatus) {
        SalaryStatus.BELOW_80 -> listOf(
            "Piyasa araştırmanızı somut rakamlarla belgeleyerek yöneticinize sunun. Sektör ortalamalarını karşılaştırın.",
            "Performans değerlendirme dönemini beklemeden önce, son 6 ayda katkılarınızın listesini hazırlayın.",
            "Maaş görüşmesinde \"hakkaniyetli ücretlendirme\" çerçevesini kullanın; kişisel ihtiyaçlar yerine piyasa verilerini ön plana çıkarın."
        )
        SalaryStatus.BETWEEN_80_100 -> listOf(
            "Medyana yaklaştığınız için konumunuz iyi; %100'e ulaşmak için ek sorumluluk talep etmeyi düşünün.",
            "Kısa vadeli hedefler belirleyip bunları yönetime sunarak zam için somut bir yol haritası oluşturun.",
            "Maaşınızı artırmak için eğitim, sertifika veya yeni beceriler eklemek güçlü bir argüman sağlar."
        )
        SalaryStatus.AT_OR_ABOVE -> listOf(
            "Sektör medyanının üzerinde olduğunuz için konumunuzu güçlendirmeye devam edin.",
            "Kariyer gelişimi için liderlik rolleri veya stratejik projelere yönelin.",
            "Uzmanlaşma, maaşınızı daha da yukarı taşıyabilir; niş beceriler kazanmaya odaklanın."
        )
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
        elevation = CardDefaults.cardElevation(6.dp)
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            // Header
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(32.dp)
                        .background(PurplePrimary.copy(alpha = 0.15f), RoundedCornerShape(10.dp)),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        Icons.Default.WorkOutline,
                        contentDescription = null,
                        tint = PurplePrimary,
                        modifier = Modifier.size(18.dp)
                    )
                }
                Spacer(Modifier.width(8.dp))
                Text(
                    "Piyasa Analizi",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                    color = colors.textPrimary
                )
            }

            HorizontalDivider(color = colors.cardGray)

            // Min / Median / Max boxes
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Min
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .background(ErrorRed.copy(alpha = 0.10f), RoundedCornerShape(12.dp))
                        .padding(10.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text("Min", fontSize = 11.sp, color = ErrorRed, fontWeight = FontWeight.Medium)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "₺${formatMoney(result.adjustedMin.toDouble())}",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                        color = ErrorRed
                    )
                }
                // Median
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .background(FuchsiaAccent.copy(alpha = 0.10f), RoundedCornerShape(12.dp))
                        .padding(10.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text("Medyan", fontSize = 11.sp, color = FuchsiaAccent, fontWeight = FontWeight.Medium)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "₺${formatMoney(result.adjustedMedian.toDouble())}",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                        color = FuchsiaAccent
                    )
                }
                // Max
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .background(SuccessGreen.copy(alpha = 0.10f), RoundedCornerShape(12.dp))
                        .padding(10.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text("Maks", fontSize = 11.sp, color = SuccessGreen, fontWeight = FontWeight.Medium)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "₺${formatMoney(result.adjustedMax.toDouble())}",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                        color = SuccessGreen
                    )
                }
            }

            // Gradient range bar showing min→median→max track
            Column {
                Text(
                    "Maaş Aralığı",
                    fontSize = 12.sp,
                    color = colors.textSecondary,
                    fontWeight = FontWeight.Medium
                )
                Spacer(Modifier.height(6.dp))
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(12.dp)
                        .clip(RoundedCornerShape(6.dp))
                ) {
                    // Background gradient track: red → fuchsia → green
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(12.dp)
                            .background(
                                androidx.compose.ui.graphics.Brush.horizontalGradient(
                                    listOf(
                                        ErrorRed.copy(alpha = 0.25f),
                                        FuchsiaAccent.copy(alpha = 0.25f),
                                        SuccessGreen.copy(alpha = 0.25f)
                                    )
                                )
                            )
                    )
                    // User salary marker
                    if (result.userSalary != null && result.adjustedMax > result.adjustedMin) {
                        val range = (result.adjustedMax - result.adjustedMin).toFloat()
                        val clampedSalary = result.userSalary.toFloat()
                            .coerceIn(result.adjustedMin.toFloat(), result.adjustedMax.toFloat())
                        val fraction = (clampedSalary - result.adjustedMin) / range
                        Box(
                            modifier = Modifier
                                .fillMaxWidth(fraction.coerceIn(0f, 1f))
                                .height(12.dp)
                                .background(
                                    androidx.compose.ui.graphics.Brush.horizontalGradient(
                                        listOf(ErrorRed, FuchsiaAccent, barColor)
                                    )
                                )
                        )
                    }
                }
                Spacer(Modifier.height(4.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("₺${formatMoney(result.adjustedMin.toDouble())}", fontSize = 10.sp, color = colors.textSecondary)
                    Text("₺${formatMoney(result.adjustedMax.toDouble())}", fontSize = 10.sp, color = colors.textSecondary)
                }
            }

            // Comparison text (only if user entered salary)
            if (result.userSalary != null && result.percentOfMedian != null) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = barColor.copy(alpha = 0.10f)),
                    elevation = CardDefaults.cardElevation(0.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(statusEmoji, fontSize = 18.sp)
                        Spacer(Modifier.width(10.dp))
                        Column {
                            Text(
                                "Maaşın sektör medyanının %${"%.0f".format(result.percentOfMedian)}'i seviyesinde",
                                fontSize = 13.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = barColor
                            )
                            Text(
                                "Mevcut: ₺${formatMoney(result.userSalary)} → Medyan: ₺${formatMoney(result.adjustedMedian.toDouble())}",
                                fontSize = 11.sp,
                                color = colors.textSecondary
                            )
                        }
                    }
                }
            }

            HorizontalDivider(color = colors.cardGray)

            // Tips
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    "💡 Müzakere Tüyoları",
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    color = colors.textPrimary
                )
                tips.forEachIndexed { index, tip ->
                    Row(
                        verticalAlignment = Alignment.Top,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(22.dp)
                                .background(IndigoDeep.copy(alpha = 0.15f), RoundedCornerShape(6.dp)),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                "${index + 1}",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = IndigoDeep
                            )
                        }
                        Text(
                            tip,
                            fontSize = 13.sp,
                            color = colors.textSecondary,
                            lineHeight = 19.sp,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
            }

            // Disclaimer
            Text(
                "⚠️ Veriler 2024/2025 piyasa araştırmalarına dayanmaktadır. Kesin rakamlar için sektör raporlarına ve şirket politikalarına başvurunuz.",
                fontSize = 11.sp,
                color = colors.textSecondary,
                lineHeight = 15.sp
            )
        }
    }
}
