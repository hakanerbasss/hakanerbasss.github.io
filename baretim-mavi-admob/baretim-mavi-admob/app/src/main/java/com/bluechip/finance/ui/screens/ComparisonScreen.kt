package com.bluechip.finance.ui.screens

import android.content.Intent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.ui.components.*
import com.bluechip.finance.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun ComparisonScreen() {
    val context = LocalContext.current; val colors = LocalAppColors.current
    val scrollState = rememberScrollState(); val scope = rememberCoroutineScope()
    val profileManager = remember { ProfileManager(context) }
    var salary1 by remember { mutableStateOf("") }; var salary2 by remember { mutableStateOf("") }
    var showResult by remember { mutableStateOf(false) }; var profileLoaded by remember { mutableStateOf(false) }

    val sgkRate = 0.14; val unempRate = 0.01; val stampRate = 0.00759; val minWageGross = 33030.0

    var n1 by remember { mutableDoubleStateOf(0.0) }; var n2 by remember { mutableDoubleStateOf(0.0) }
    var g1 by remember { mutableDoubleStateOf(0.0) }; var g2 by remember { mutableDoubleStateOf(0.0) }
    var e1 by remember { mutableDoubleStateOf(0.0) }; var e2 by remember { mutableDoubleStateOf(0.0) }
    var diff by remember { mutableDoubleStateOf(0.0) }; var pct by remember { mutableDoubleStateOf(0.0) }

    LaunchedEffect(Unit) { val p = profileManager.load(); if (p.isLoggedIn && p.grossSalary > 0) { salary1 = p.grossSalary.toInt().toString(); profileLoaded = true } }

    fun calcNet(gross: Double): Double {
        val sgk = gross * sgkRate; val unemp = gross * unempRate; val base = gross - sgk - unemp
        val minBase = minWageGross - (minWageGross * sgkRate) - (minWageGross * unempRate)
        val exempt = minOf(base, minBase); val taxable = maxOf(0.0, base - exempt)
        val tax = taxable * 0.15; val stamp = maxOf(0.0, gross * stampRate - minWageGross * stampRate)
        return gross - sgk - unemp - tax - stamp
    }

    fun calculate() {
        if (salary1.isBlank()) { android.widget.Toast.makeText(context, "Lutfen mevcut maasi giriniz", android.widget.Toast.LENGTH_SHORT).show(); return }
        if (salary2.isBlank()) { android.widget.Toast.makeText(context, "Lutfen yeni teklifi giriniz", android.widget.Toast.LENGTH_SHORT).show(); return }
        g1 = salary1.toDoubleOrNull() ?: run { android.widget.Toast.makeText(context, "Gecersiz deger", android.widget.Toast.LENGTH_SHORT).show(); return }
        g2 = salary2.toDoubleOrNull() ?: run { android.widget.Toast.makeText(context, "Gecersiz deger", android.widget.Toast.LENGTH_SHORT).show(); return }
        n1 = calcNet(g1); n2 = calcNet(g2); e1 = g1 * 1.225; e2 = g2 * 1.225
        diff = n2 - n1; pct = if (n1 > 0) (diff / n1 * 100) else 0.0
        showResult = true; scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        androidx.compose.animation.AnimatedVisibility(
            visible = !showResult,
            enter = androidx.compose.animation.expandVertically(),
            exit = androidx.compose.animation.shrinkVertically()
        ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        SectionHeader("MAAŞ KARŞILAŞTIRMA", Icons.Default.CompareArrows)
        Text("1️⃣ Mevcut İş", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary)
        CurrencyField(value = salary1, onValueChange = { salary1 = it; profileLoaded = false }, label = "Mevcut Brüt Maaş (₺)")
        if (profileLoaded) ProfileAutoFillNote()
        Text("2️⃣ Yeni Teklif", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary)
        CurrencyField(value = salary2, onValueChange = { salary2 = it }, label = "Yeni Teklif Brüt Maaş (₺)")
        ActionButtons(onCalculate = { calculate() }, onReset = { salary1 = ""; salary2 = ""; showResult = false; profileLoaded = false })
        } // inputs column
        } // AnimatedVisibility

        ResultCard(visible = showResult) {
            Text("KARŞILAŞTIRMA", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)
            Spacer(Modifier.height(12.dp))

            // Başlık satırı
            Row(Modifier.fillMaxWidth()) {
                Spacer(Modifier.weight(1f))
                Text("Mevcut", fontWeight = FontWeight.Bold, fontSize = 12.sp, color = colors.textSecondary, modifier = Modifier.weight(1f), textAlign = TextAlign.End)
                Text("Yeni", fontWeight = FontWeight.Bold, fontSize = 12.sp, color = colors.textSecondary, modifier = Modifier.weight(1f), textAlign = TextAlign.End)
            }
            HorizontalDivider(Modifier.padding(vertical = 4.dp))

            // Brüt satırı
            Row(Modifier.fillMaxWidth()) {
                Text("Brüt", fontSize = 13.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                Text("${formatMoney(g1)}₺", fontSize = 13.sp, color = colors.textPrimary, modifier = Modifier.weight(1f), textAlign = TextAlign.End)
                Text("${formatMoney(g2)}₺", fontSize = 13.sp, color = colors.textPrimary, modifier = Modifier.weight(1f), textAlign = TextAlign.End)
            }
            Spacer(Modifier.height(4.dp))

            // Net satırı
            Row(Modifier.fillMaxWidth()) {
                Text("Net", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary, modifier = Modifier.weight(1f))
                Text("${formatMoney(n1)}₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary, modifier = Modifier.weight(1f), textAlign = TextAlign.End)
                Text("${formatMoney(n2)}₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary, modifier = Modifier.weight(1f), textAlign = TextAlign.End)
            }
            Spacer(Modifier.height(4.dp))

            // İşveren satırı
            Row(Modifier.fillMaxWidth()) {
                Text("İşveren", fontSize = 13.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
                Text("${formatMoney(e1)}₺", fontSize = 13.sp, color = colors.textSecondary, modifier = Modifier.weight(1f), textAlign = TextAlign.End)
                Text("${formatMoney(e2)}₺", fontSize = 13.sp, color = colors.textSecondary, modifier = Modifier.weight(1f), textAlign = TextAlign.End)
            }

            HorizontalDivider(Modifier.padding(vertical = 8.dp))

            // Fark
            val diffColor = if (diff >= 0) colors.success else colors.error
            val arrow = if (diff >= 0) "📈" else "📉"
            BigResult("Aylık Net Fark", "$arrow ${if (diff >= 0) "+" else ""}${formatMoney(diff)}₺", diffColor)
            Text("${if (pct >= 0) "+" else ""}${String.format("%.1f", pct)}%", fontSize = 13.sp, color = diffColor, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())

            Spacer(Modifier.height(4.dp))
            ResultLine("Yıllık Fark", "${if (diff >= 0) "+" else ""}${formatMoney(diff * 12)}₺", diffColor, true)

            Spacer(Modifier.height(8.dp))
            val verdict = when { diff > 0 -> "✅ Yeni teklif aylık ${formatMoney(diff)}₺ daha avantajlı."; diff < 0 -> "⚠️ Yeni teklif aylık ${formatMoney(-diff)}₺ daha düşük."; else -> "↔️ İki maaş eşit." }
            Text(verdict, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = diffColor)

                Spacer(Modifier.height(4.dp))
            OutlinedButton(
                onClick = { showResult = false },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp)
            ) {
                Icon(Icons.Default.Edit, null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Yeniden Hesapla")
            }
            DisclaimerText(); Spacer(Modifier.height(8.dp))
            ShareButton { context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, "⚖️ KARŞILAŞTIRMA\nMevcut Net: ${formatMoney(n1)}₺\nYeni Net: ${formatMoney(n2)}₺\nFark: ${if (diff >= 0) "+" else ""}${formatMoney(diff)}₺/ay\n📱 Baretim Mavi") }, "Paylaş")) }
        }
    }
}
