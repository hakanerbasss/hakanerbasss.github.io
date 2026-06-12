package com.bluechip.finance.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountBalance
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.Security
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.data.PaymentCategory
import com.bluechip.finance.data.PaymentManager
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.ui.components.CurrencyField
import com.bluechip.finance.ui.components.SectionHeader
import com.bluechip.finance.ui.components.formatMoney
import com.bluechip.finance.ui.theme.GradientPrimary
import com.bluechip.finance.ui.theme.IndigoDeep
import com.bluechip.finance.ui.theme.LocalAppColors

@Composable
fun BudgetScreen() {
    val context = LocalContext.current
    val colors = LocalAppColors.current

    var incomeText    by remember { mutableStateOf("") }
    var rentText      by remember { mutableStateOf("") }
    var foodText      by remember { mutableStateOf("") }
    var billsText     by remember { mutableStateOf("") }
    var transportText by remember { mutableStateOf("") }
    var savingsText   by remember { mutableStateOf("") }
    var autoFilledFields by remember { mutableStateOf(emptyList<String>()) }

    // Auto-fill net salary from profile and payments from PaymentManager
    LaunchedEffect(Unit) {
        val profile = ProfileManager(context).load()
        if (profile.netSalary > 0) {
            incomeText = profile.netSalary.toLong().toString()
        }
        val payments = PaymentManager.getPayments(context).filter { it.isActive }
        val filled = mutableListOf<String>()
        // KIRA category → rentText
        payments.filter { it.category == PaymentCategory.KIRA }
            .sumOf { it.amount }.let { if (it > 0) { rentText = it.toLong().toString(); filled.add("kira") } }
        // FATURA + ABONELIK + SIGORTA + DIGER → billsText
        payments.filter { it.category == PaymentCategory.FATURA || it.category == PaymentCategory.ABONELIK || it.category == PaymentCategory.SIGORTA || it.category == PaymentCategory.DIGER }
            .sumOf { it.amount }.let { if (it > 0) { billsText = it.toLong().toString(); filled.add("fatura") } }
        autoFilledFields = filled
    }

    val income        = incomeText.toDoubleOrNull() ?: 0.0
    val rent          = rentText.toDoubleOrNull() ?: 0.0
    val food          = foodText.toDoubleOrNull() ?: 0.0
    val bills         = billsText.toDoubleOrNull() ?: 0.0
    val transport     = transportText.toDoubleOrNull() ?: 0.0
    val totalExpenses = rent + food + bills + transport
    val remaining     = income - totalExpenses
    val savingsRate   = if (income > 0) ((income - totalExpenses) / income * 100.0) else 0.0

    val currentSavings   = savingsText.toDoubleOrNull() ?: 0.0
    val emergencyTarget  = totalExpenses * 6.0
    val monthsCovered    = if (totalExpenses > 0) currentSavings / totalExpenses else 0.0
    val progressFraction = if (emergencyTarget > 0) (currentSavings / emergencyTarget).coerceIn(0.0, 1.0) else 0.0

    // Financial health score (0–100)
    var score = 0
    if (savingsRate >= 20.0)                   score += 30
    if (currentSavings > 0)                    score += 20
    if (monthsCovered >= 3.0)                  score += 20
    if (monthsCovered >= 6.0)                  score += 10
    if (income > 0 && totalExpenses <= income) score += 20

    val scrollState = rememberScrollState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(bottom = 32.dp)
    ) {
        // ── Header gradient banner ──────────────────────────────────────
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(GradientPrimary)
                .padding(horizontal = 20.dp, vertical = 24.dp)
        ) {
            Column {
                Text(
                    text = "Bütçe & Acil Fon",
                    color = Color.White,
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "50/30/20 kuralıyla finansal dengenizi kurun",
                    color = Color.White.copy(alpha = 0.85f),
                    fontSize = 13.sp,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // ── Section 1: Gelir Girişi ────────────────────────────────────
        SectionHeader(title = "GELİR GİRİŞİ", icon = Icons.Default.AccountBalance)

        Column(modifier = Modifier.padding(horizontal = 16.dp)) {
            CurrencyField(
                value = incomeText,
                onValueChange = { incomeText = it },
                label = "Aylık Net Gelirim (₺)"
            )
            if (income > 0) {
                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = "✓ Profilden yüklendi: ${formatMoney(income)} ₺",
                    fontSize = 12.sp,
                    color = colors.success
                )
            }
            if (autoFilledFields.isNotEmpty()) {
                Spacer(modifier = Modifier.height(8.dp))
                Surface(
                    shape = RoundedCornerShape(20.dp),
                    color = IndigoDeep.copy(alpha = 0.10f)
                ) {
                    Text(
                        text = "Ödeme takibinden otomatik dolduruldu",
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                        fontSize = 12.sp,
                        color = IndigoDeep
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        // ── Section 2: 50/30/20 Kuralı ────────────────────────────────
        SectionHeader(title = "50/30/20 KURALI", icon = Icons.Default.PieChart)

        AnimatedVisibility(visible = income > 0) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                AllocationCard(
                    modifier     = Modifier.weight(1f),
                    topColor     = colors.success,
                    title        = "İhtiyaçlar",
                    percent      = "%50",
                    amount       = formatMoney(income * 0.50),
                    description  = "Kira, fatura, yemek",
                    textPrimary  = colors.textPrimary,
                    textSecondary= colors.textSecondary,
                    cardBg       = colors.cardBg
                )
                AllocationCard(
                    modifier     = Modifier.weight(1f),
                    topColor     = colors.info,
                    title        = "İstekler",
                    percent      = "%30",
                    amount       = formatMoney(income * 0.30),
                    description  = "Eğlence, giyim, dışarı",
                    textPrimary  = colors.textPrimary,
                    textSecondary= colors.textSecondary,
                    cardBg       = colors.cardBg
                )
                AllocationCard(
                    modifier     = Modifier.weight(1f),
                    topColor     = colors.warning,
                    title        = "Birikim",
                    percent      = "%20",
                    amount       = formatMoney(income * 0.20),
                    description  = "Tasarruf, yatırım",
                    textPrimary  = colors.textPrimary,
                    textSecondary= colors.textSecondary,
                    cardBg       = colors.cardBg
                )
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        // ── Section 3: Aylık Gider Detayı ─────────────────────────────
        SectionHeader(title = "AYLIK GİDER DETAYI", icon = Icons.Default.Receipt)

        Column(
            modifier = Modifier
                .padding(horizontal = 16.dp)
                .fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            CurrencyField(
                value = rentText,
                onValueChange = { rentText = it },
                label = "Kira / Konut (ev kirası veya mortgage)"
            )
            CurrencyField(
                value = foodText,
                onValueChange = { foodText = it },
                label = "Yiyecek & Market"
            )
            CurrencyField(
                value = billsText,
                onValueChange = { billsText = it },
                label = "Fatura & Abonelik"
            )
            CurrencyField(
                value = transportText,
                onValueChange = { transportText = it },
                label = "Ulaşım"
            )
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Remaining + savings rate summary card
        AnimatedVisibility(visible = income > 0 || totalExpenses > 0) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                text = "Toplam Gider",
                                fontSize = 12.sp,
                                color = colors.textSecondary
                            )
                            Text(
                                text = formatMoney(totalExpenses),
                                fontSize = 16.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = colors.textPrimary
                            )
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text(
                                text = "Kalan",
                                fontSize = 12.sp,
                                color = colors.textSecondary
                            )
                            Text(
                                text = "₺${formatMoney(remaining)}",
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (remaining >= 0) colors.success else colors.error
                            )
                        }
                    }
                    if (income > 0) {
                        Spacer(modifier = Modifier.height(10.dp))
                        HorizontalDivider(color = colors.cardGray.copy(alpha = 0.4f))
                        Spacer(modifier = Modifier.height(10.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                text = "Birikim Oranı: ",
                                fontSize = 13.sp,
                                color = colors.textSecondary
                            )
                            SavingsRateChip(
                                rate         = savingsRate,
                                successColor = colors.success,
                                warningColor = colors.warning,
                                errorColor   = colors.error
                            )
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        // ── Section 4: Acil Fon Hesaplayıcı ───────────────────────────
        SectionHeader(title = "ACİL FON HESAPLAYICI", icon = Icons.Default.Security)

        Column(modifier = Modifier.padding(horizontal = 16.dp)) {
            CurrencyField(
                value = savingsText,
                onValueChange = { savingsText = it },
                label = "Mevcut Birikimim (₺)"
            )

            Spacer(modifier = Modifier.height(12.dp))

            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Hedef (6 aylık gider)",
                            fontSize = 13.sp,
                            color = colors.textSecondary
                        )
                        Text(
                            text = formatMoney(emergencyTarget),
                            fontSize = 14.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = colors.textPrimary
                        )
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    LinearProgressIndicator(
                        progress = { progressFraction.toFloat() },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(10.dp)
                            .clip(RoundedCornerShape(5.dp)),
                        color = when {
                            monthsCovered >= 6.0 -> colors.success
                            monthsCovered >= 3.0 -> colors.info
                            monthsCovered >= 1.0 -> colors.warning
                            else                 -> colors.error
                        },
                        trackColor = colors.cardGray.copy(alpha = 0.3f)
                    )

                    Spacer(modifier = Modifier.height(4.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(text = "₺0", fontSize = 11.sp, color = colors.textSecondary)
                        Text(text = formatMoney(emergencyTarget), fontSize = 11.sp, color = colors.textSecondary)
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    val (badgeText, badgeColor) = when {
                        totalExpenses <= 0   -> Pair("Gider bilgisi girin", colors.textSecondary)
                        monthsCovered >= 6.0 -> Pair("✅ Hedefine ulaştın!", colors.success)
                        monthsCovered >= 3.0 -> Pair("👍 İyi yolda (${String.format("%.1f", monthsCovered)} ay)", colors.info)
                        monthsCovered >= 1.0 -> Pair("⚡ Az (${String.format("%.1f", monthsCovered)} ay)", colors.warning)
                        else                 -> Pair("⚠️ Acil fon yok", colors.error)
                    }

                    Surface(
                        shape = RoundedCornerShape(20.dp),
                        color = badgeColor.copy(alpha = 0.15f)
                    ) {
                        Text(
                            text = badgeText,
                            modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp),
                            fontSize = 13.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = badgeColor
                        )
                    }

                    if (totalExpenses > 0 && currentSavings >= 0) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Mevcut birikim: ${String.format("%.1f", monthsCovered)} aylık gideri karşılar",
                            fontSize = 12.sp,
                            color = colors.textSecondary
                        )
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        // ── Section 5: Finansal Sağlık Skoru ──────────────────────────
        SectionHeader(title = "FİNANSAL SAĞLIK SKORU", icon = Icons.Default.Favorite)

        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(20.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                val (scoreLabel, scoreColor) = when {
                    score >= 80 -> Pair("İyi",    colors.success)
                    score >= 60 -> Pair("Orta",   colors.warning)
                    score >= 40 -> Pair("Dikkat", Color(0xFFFF8C00))
                    else        -> Pair("Kritik", colors.error)
                }

                Box(
                    contentAlignment = Alignment.Center,
                    modifier = Modifier.size(140.dp)
                ) {
                    Canvas(modifier = Modifier.size(140.dp)) {
                        val strokeWidth = 14.dp.toPx()
                        val inset   = strokeWidth / 2
                        val arcRect = Size(size.width - strokeWidth, size.height - strokeWidth)
                        val topLeft = Offset(inset, inset)

                        // Track arc
                        drawArc(
                            color      = Color.Gray.copy(alpha = 0.2f),
                            startAngle = 135f,
                            sweepAngle = 270f,
                            useCenter  = false,
                            topLeft    = topLeft,
                            size       = arcRect,
                            style      = Stroke(width = strokeWidth, cap = StrokeCap.Round)
                        )

                        // Score arc
                        val sweep = (score / 100f * 270f).coerceIn(0f, 270f)
                        drawArc(
                            brush      = Brush.sweepGradient(listOf(scoreColor.copy(alpha = 0.7f), scoreColor)),
                            startAngle = 135f,
                            sweepAngle = sweep,
                            useCenter  = false,
                            topLeft    = topLeft,
                            size       = arcRect,
                            style      = Stroke(width = strokeWidth, cap = StrokeCap.Round)
                        )
                    }

                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text       = "$score",
                            fontSize   = 36.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color      = scoreColor
                        )
                        Text(
                            text       = scoreLabel,
                            fontSize   = 14.sp,
                            fontWeight = FontWeight.SemiBold,
                            color      = scoreColor
                        )
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Score breakdown rows
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    ScoreRow(
                        label        = "Birikim oranı ≥ %20",
                        points       = 30,
                        achieved     = savingsRate >= 20.0,
                        successColor = colors.success,
                        errorColor   = colors.error,
                        textSecondary= colors.textSecondary
                    )
                    ScoreRow(
                        label        = "Acil fon mevcut",
                        points       = 20,
                        achieved     = currentSavings > 0,
                        successColor = colors.success,
                        errorColor   = colors.error,
                        textSecondary= colors.textSecondary
                    )
                    ScoreRow(
                        label        = "Acil fon ≥ 3 ay",
                        points       = 20,
                        achieved     = monthsCovered >= 3.0,
                        successColor = colors.success,
                        errorColor   = colors.error,
                        textSecondary= colors.textSecondary
                    )
                    ScoreRow(
                        label        = "Acil fon ≥ 6 ay",
                        points       = 10,
                        achieved     = monthsCovered >= 6.0,
                        successColor = colors.success,
                        errorColor   = colors.error,
                        textSecondary= colors.textSecondary
                    )
                    ScoreRow(
                        label        = "Giderler geliri aşmıyor",
                        points       = 20,
                        achieved     = income > 0 && totalExpenses <= income,
                        successColor = colors.success,
                        errorColor   = colors.error,
                        textSecondary= colors.textSecondary
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        // Disclaimer
        Text(
            text = "Bu hesaplama bilgilendirme amaçlıdır.",
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp),
            textAlign = TextAlign.Center,
            fontSize   = 12.sp,
            color      = colors.textSecondary
        )

        Spacer(modifier = Modifier.height(16.dp))
    }
}

// ── Private composables ───────────────────────────────────────────────────

@Composable
private fun AllocationCard(
    modifier      : Modifier = Modifier,
    topColor      : Color,
    title         : String,
    percent       : String,
    amount        : String,
    description   : String,
    textPrimary   : Color,
    textSecondary : Color,
    cardBg        : Color
) {
    Card(
        modifier  = modifier,
        shape     = RoundedCornerShape(12.dp),
        colors    = CardDefaults.cardColors(containerColor = cardBg),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(4.dp)
                    .background(topColor)
            )
            Column(modifier = Modifier.padding(10.dp)) {
                Text(
                    text       = percent,
                    fontSize   = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color      = topColor
                )
                Text(
                    text       = title,
                    fontSize   = 11.sp,
                    fontWeight = FontWeight.SemiBold,
                    color      = textPrimary
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text       = amount,
                    fontSize   = 13.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color      = textPrimary
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text       = description,
                    fontSize   = 10.sp,
                    color      = textSecondary,
                    lineHeight = 13.sp
                )
            }
        }
    }
}

@Composable
private fun SavingsRateChip(
    rate         : Double,
    successColor : Color,
    warningColor : Color,
    errorColor   : Color
) {
    val (label, color) = when {
        rate >= 20.0 -> Pair("%${String.format("%.0f", rate)} ✅", successColor)
        rate > 0.0   -> Pair("%${String.format("%.0f", rate)} ⚠️", warningColor)
        else         -> Pair("%0 ❌", errorColor)
    }
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = color.copy(alpha = 0.15f)
    ) {
        Text(
            text       = label,
            modifier   = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            fontSize   = 12.sp,
            fontWeight = FontWeight.SemiBold,
            color      = color
        )
    }
}

@Composable
private fun ScoreRow(
    label        : String,
    points       : Int,
    achieved     : Boolean,
    successColor : Color,
    errorColor   : Color,
    textSecondary: Color
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment     = Alignment.CenterVertically
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(if (achieved) successColor else errorColor.copy(alpha = 0.4f))
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text     = label,
                fontSize = 12.sp,
                color    = textSecondary
            )
        }
        Text(
            text       = if (achieved) "+$points" else "+0",
            fontSize   = 12.sp,
            fontWeight = FontWeight.SemiBold,
            color      = if (achieved) successColor else errorColor.copy(alpha = 0.5f)
        )
    }
}
