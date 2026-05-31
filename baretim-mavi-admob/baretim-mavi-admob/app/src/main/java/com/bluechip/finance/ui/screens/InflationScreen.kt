package com.bluechip.finance.ui.screens

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.ui.graphics.asAndroidBitmap
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
import com.bluechip.finance.ui.components.*
import com.bluechip.finance.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.URL
import java.util.Calendar

data class InflationRow(
    val year: Int,
    val rate: Double,
    val isEstimate: Boolean,
    val yearlyValue: Double,
    val cumulativeValue: Double,
    val cumulativeRate: Double   // o yildan buyana toplam erime/artis %
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InflationScreen() {
    val context       = LocalContext.current
    val colors        = LocalAppColors.current
    val scrollState   = rememberScrollState()
    val scope         = rememberCoroutineScope()
    val currentYear   = Calendar.getInstance().get(Calendar.YEAR)

    var amount        by remember { mutableStateOf("") }
    var targetYear    by remember { mutableIntStateOf(currentYear - 5) }
    var showResult    by remember { mutableStateOf(false) }
    var showInfoDialog by remember { mutableStateOf(false) }
    var isLoading     by remember { mutableStateOf(false) }
    var loadError     by remember { mutableStateOf("") }
    var isPast        by remember { mutableStateOf(true) }  // gecmis mi gelecek mi

    var ratesMap      by remember { mutableStateOf<Map<Int, Double>>(emptyMap()) }
    var estimateMap   by remember { mutableStateOf<Map<Int, Double>>(emptyMap()) }

    var manualRate    by remember { mutableStateOf("") }
    var useManual     by remember { mutableStateOf(false) }

    var resultRows    by remember { mutableStateOf<List<InflationRow>>(emptyList()) }
    var equivalentAmt by remember { mutableStateOf(0.0) }
    var hasEstimates  by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        isLoading = true
        withContext(Dispatchers.IO) {
            try {
                val json = URL("https://raw.githubusercontent.com/hakanerbasss/baretim-mavi/main/inflation_rates.json?t=${System.currentTimeMillis()}").readText()
                val obj  = JSONObject(json)
                val rm   = mutableMapOf<Int, Double>()
                val em   = mutableMapOf<Int, Double>()
                val rObj = obj.getJSONObject("rates")
                val eObj = obj.getJSONObject("estimates")
                rObj.keys().forEach { k -> rm[k.toInt()] = rObj.getDouble(k) }
                eObj.keys().forEach { k -> em[k.toInt()] = eObj.getDouble(k) }
                ratesMap    = rm
                estimateMap = em
            } catch (e: Exception) {
                loadError = "Veriler yuklenemedi. Varsayilan oranlar kullanilir."
                // Varsayilan oranlar - JSON yuklenemezse
                ratesMap = mapOf(
                    2000 to 54.9, 2001 to 54.4, 2002 to 45.0, 2003 to 25.3, 2004 to 10.6,
                    2005 to 8.2,  2006 to 9.6,  2007 to 8.4,  2008 to 10.1, 2009 to 6.5,
                    2010 to 6.4,  2011 to 10.5, 2012 to 6.2,  2013 to 7.4,  2014 to 8.2,
                    2015 to 8.8,  2016 to 8.5,  2017 to 11.9, 2018 to 20.3, 2019 to 11.8,
                    2020 to 14.6, 2021 to 19.6, 2022 to 72.3, 2023 to 64.8, 2024 to 44.4
                )
                estimateMap = mapOf(2025 to 30.0, 2026 to 22.0, 2027 to 18.0, 2028 to 15.0, 2029 to 12.0, 2030 to 10.0)
            }
        }
        isLoading = false
    }

    fun calculate() {
        val amt = amount.toDoubleOrNull() ?: return
        val rows = mutableListOf<InflationRow>()
        var hasEst = false

        fun getRate(y: Int): Pair<Double, Boolean> {
            if (useManual && manualRate.isNotBlank())
                return Pair(manualRate.toDoubleOrNull() ?: 20.0, false)
            val r = ratesMap[y] ?: estimateMap[y] ?: 20.0
            val est = !ratesMap.containsKey(y)
            if (est) hasEst = true
            return Pair(r, est)
        }

        if (isPast) {
            // GECMIS: bugunki tutarin her yila karsiligi
            // Yillar: targetYear+1 .. currentYear (hepsi geçmiş)
            val years = (targetYear + 1..currentYear).toList()

            // Kumulatif: tum yillarin zincirleme bolumu
            var cumVal = amt
            val cumulativeMap = mutableMapOf<Int, Double>()
            for (y in years) {
                val (rate, _) = getRate(y)
                cumVal /= (1.0 + rate / 100.0)
                cumulativeMap[y - 1] = cumVal
            }

            // Kumulatif oran map - her yil icin toplam erime %
            val cumulativeRateMap = mutableMapOf<Int, Double>()
            var cumRateVal = 1.0
            for (y in years) {
                val (rate, _) = getRate(y)
                cumRateVal /= (1.0 + rate / 100.0)
                cumulativeRateMap[y - 1] = (1.0 - cumRateVal) * 100.0
            }

            // Satirlari olustur
            for (y in years) {
                val (rate, isEst) = getRate(y)
                val yearlyVal  = amt / (1.0 + rate / 100.0)
                val cumulative = cumulativeMap[y - 1] ?: yearlyVal
                val cumRate    = cumulativeRateMap[y - 1] ?: (rate)
                rows.add(InflationRow(y - 1, rate, isEst, yearlyVal, cumulative, cumRate))
            }
            // En eski yil en uste (2021 once, 2025 sonda)
            rows.reverse()
            equivalentAmt = rows.firstOrNull()?.cumulativeValue ?: amt
        } else {
            // GELECEK: bugunki tutarin gelecekte kac TL ye esit olacagi
            val years = (currentYear + 1..targetYear).toList()

            // Kumulatif: tum yillarin zincirleme carpimi
            var cumVal = amt
            val cumulativeMap = mutableMapOf<Int, Double>()
            for (y in years) {
                val (rate, _) = getRate(y)
                cumVal *= (1.0 + rate / 100.0)
                cumulativeMap[y] = cumVal
            }

            // Kumulatif oran map - gelecek icin toplam artis %
            val cumulativeRateMap = mutableMapOf<Int, Double>()
            var cumRateVal = 1.0
            for (y in years) {
                val (rate, _) = getRate(y)
                cumRateVal *= (1.0 + rate / 100.0)
                cumulativeRateMap[y] = (cumRateVal - 1.0) * 100.0
            }

            for (y in years) {
                val (rate, isEst) = getRate(y)
                val yearlyVal  = amt * (1.0 + rate / 100.0)
                val cumulative = cumulativeMap[y] ?: yearlyVal
                val cumRate    = cumulativeRateMap[y] ?: rate
                rows.add(InflationRow(y, rate, isEst, yearlyVal, cumulative, cumRate))
            }
            equivalentAmt = rows.lastOrNull()?.cumulativeValue ?: amt
        }

        resultRows   = rows
        hasEstimates = hasEst
        showResult   = true
        scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        SectionHeader("ENFLASYON HESAPLAMA", Icons.Default.TrendingDown) { showInfoDialog = true }

        if (isLoading) {
            Card(shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = colors.cardBg)) {
                Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp, color = PurplePrimary)
                    Spacer(Modifier.width(10.dp))
                    Text("Enflasyon verileri yukleniyor...", fontSize = 13.sp, color = colors.textSecondary)
                }
            }
        }

        if (loadError.isNotBlank()) {
            Card(shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = colors.warning.copy(alpha = 0.1f))) {
                Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Warning, null, tint = colors.warning, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(loadError, fontSize = 12.sp, color = colors.warning)
                }
            }
        }

        androidx.compose.animation.AnimatedVisibility(
            visible = !showResult,
            enter = androidx.compose.animation.expandVertically(),
            exit  = androidx.compose.animation.shrinkVertically()
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {

                CurrencyField(value = amount, onValueChange = { amount = it }, label = "Bugunki Tutar (TL)")

                // Gecmis / Gelecek toggle
                Card(shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                    elevation = CardDefaults.cardElevation(2.dp)) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {

                        Row(modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf(true to "Gecmis", false to "Gelecek").forEach { (past, label) ->
                                FilterChip(
                                    selected = isPast == past,
                                    onClick = { isPast = past; showResult = false
                                        targetYear = if (past) currentYear - 5 else currentYear + 3 },
                                    label = { Text(label, fontSize = 13.sp) },
                                    leadingIcon = if (isPast == past) {{ Icon(Icons.Default.Check, null, Modifier.size(14.dp)) }} else null,
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }

                        Text(
                            if (isPast) "Bu tutar kac yil oncesine esit?"
                            else "Bu tutar gelecekte kac TL ye esit olacak?",
                            fontSize = 12.sp, color = colors.textSecondary
                        )

                        Row(verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text(
                                if (isPast) "Kac yil oncesi?" else "Hangi yil?",
                                fontSize = 13.sp, color = colors.textPrimary,
                                modifier = Modifier.weight(1f)
                            )
                            YearPicker(
                                value = targetYear,
                                minYear = if (isPast) 1975 else currentYear + 1,
                                maxYear = if (isPast) currentYear - 1 else currentYear + 10,
                                onValueChange = { targetYear = it; showResult = false }
                            )
                        }

                        // Sure ozeti
                        val diff = if (isPast) currentYear - targetYear else targetYear - currentYear
                        if (diff > 0) {
                            Row(modifier = Modifier.fillMaxWidth()
                                .background(PurplePrimary.copy(alpha = 0.07f), RoundedCornerShape(10.dp))
                                .padding(horizontal = 12.dp, vertical = 8.dp)) {
                                Text(
                                    if (isPast)
                                        "$diff yil oncesi ($targetYear) ile bugun ($currentYear) karsilastiriliyor"
                                    else
                                        "Bugun ($currentYear) ile $targetYear yili karsilastiriliyor ($diff yil)",
                                    fontSize = 12.sp, color = PurplePrimary
                                )
                            }
                        }
                    }
                }

                // Gelecek icin manuel oran secenegi
                if (!isPast) {
                    Card(shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                        elevation = CardDefaults.cardElevation(2.dp)) {
                        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Info, null, tint = colors.info, modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Oran Secimi", fontWeight = FontWeight.Medium, fontSize = 13.sp, color = colors.textPrimary)
                            }
                            Text("Otomatik: JSON'daki tahmini oranlar kullanilir.\nManuel: Tum yillar icin tek bir oran girebilirsiniz.",
                                fontSize = 11.sp, color = colors.textSecondary)
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked = useManual, onCheckedChange = { useManual = it },
                                    colors = CheckboxDefaults.colors(checkedColor = PurplePrimary))
                                Spacer(Modifier.width(6.dp))
                                Text("Manuel oran kullan", fontSize = 13.sp, color = colors.textPrimary)
                            }
                            if (useManual) {
                                NumberField(value = manualRate, onValueChange = { manualRate = it },
                                    label = "Yillik Enflasyon Orani (%)")
                            }
                        }
                    }
                }

                ActionButtons(
                    onCalculate = { calculate() },
                    onReset = {
                        amount = ""
                        targetYear = if (isPast) currentYear - 5 else currentYear + 3
                        manualRate = ""; useManual = false; showResult = false
                    }
                )
            }
        }

        // Sonuc
        val amt = amount.toDoubleOrNull() ?: 0.0
        ResultCard(visible = showResult) {
        Column(modifier = Modifier.fillMaxWidth()) {
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("SONUC", fontWeight = FontWeight.Bold, fontSize = 16.sp,
                    color = colors.textPrimary, modifier = Modifier.weight(1f))
                OutlinedButton(onClick = { showResult = false },
                    shape = RoundedCornerShape(10.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) {
                    Icon(Icons.Default.Edit, null, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Yeniden Hesapla", fontSize = 12.sp)
                }
            }

            Spacer(Modifier.height(10.dp))

            // Ana ozet
            Card(shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = PurplePrimary.copy(alpha = 0.08f))) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (isPast) {
                        Text("Bugun elindeki ${formatMoney(amt)} TL...", fontSize = 13.sp, color = colors.textSecondary)
                        Spacer(Modifier.height(2.dp))
                        Text("$targetYear yilinda ${formatMoney(equivalentAmt)} TL'ye esitti",
                            fontSize = 16.sp, fontWeight = FontWeight.Bold, color = PurplePrimary)
                        Spacer(Modifier.height(4.dp))
                        val ratio = amt / equivalentAmt
                        Text("Para ${"%.1f".format(ratio)} kat deger kaybetti",
                            fontSize = 13.sp, color = colors.error)
                        Text("Gercek alim gucu kaybi: -%${"%.1f".format((1 - equivalentAmt / amt) * 100)}",
                            fontSize = 13.sp, color = colors.error)
                    } else {
                        Text("Bugunki ${formatMoney(amt)} TL'nin alim gucunu korumak icin...", fontSize = 13.sp, color = colors.textSecondary)
                        Spacer(Modifier.height(2.dp))
                        Text("$targetYear yilinda ${formatMoney(equivalentAmt)} TL gerekecek",
                            fontSize = 16.sp, fontWeight = FontWeight.Bold, color = PurplePrimary)
                        Spacer(Modifier.height(4.dp))
                        val diff = equivalentAmt - amt
                        Text("Ek ${formatMoney(diff)} TL'ye ihtiyac duyulacak",
                            fontSize = 13.sp, color = colors.warning)
                    }
                }
            }

            if (hasEstimates) {
                Spacer(Modifier.height(6.dp))
                Row(modifier = Modifier.fillMaxWidth()
                    .background(colors.warning.copy(alpha = 0.1f), RoundedCornerShape(8.dp))
                    .padding(8.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Info, null, tint = colors.warning, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("* isaretli yillar tahmini oran icerir.",
                        fontSize = 11.sp, color = colors.warning)
                }
            }

            Spacer(Modifier.height(10.dp))

            // Tablo baslik
            Row(modifier = Modifier.fillMaxWidth()
                .background(PurplePrimary.copy(alpha = 0.12f), RoundedCornerShape(8.dp))
                .padding(horizontal = 10.dp, vertical = 6.dp)) {
                Text("Yil", fontWeight = FontWeight.Bold, fontSize = 12.sp,
                    color = colors.textPrimary, modifier = Modifier.width(52.dp))
                Text("Oran", fontWeight = FontWeight.Bold, fontSize = 12.sp,
                    color = colors.textPrimary, modifier = Modifier.width(56.dp), textAlign = TextAlign.End)
                Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.End) {
                    Text("Yalniz O Yil", fontWeight = FontWeight.Bold, fontSize = 10.sp,
                        color = colors.textSecondary, textAlign = TextAlign.End)
                    Text("Kumulatif Deger  (Oran%)", fontWeight = FontWeight.Bold, fontSize = 10.sp,
                        color = colors.textPrimary, textAlign = TextAlign.End)
                }
            }

            resultRows.forEach { row ->
                Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        row.year.toString() + if (row.isEstimate) "*" else "",
                        fontSize = 12.sp,
                        color = if (row.isEstimate) colors.warning else colors.textPrimary,
                        modifier = Modifier.width(52.dp)
                    )
                    Text(
                        "%${"%.1f".format(row.rate)}",
                        fontSize = 12.sp, color = colors.info,
                        modifier = Modifier.width(56.dp), textAlign = TextAlign.End
                    )
                    Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.End) {
                        Text(
                            "${formatMoney(row.yearlyValue)} TL",
                            fontSize = 10.sp, color = colors.textSecondary,
                            textAlign = TextAlign.End
                        )
                        Text(
                            "${formatMoney(row.cumulativeValue)} TL  (-%${"%.1f".format(row.cumulativeRate)})",
                            fontSize = 11.sp, fontWeight = FontWeight.Bold,
                            color = colors.textPrimary,
                            textAlign = TextAlign.End
                        )
                    }
                }
                HorizontalDivider(color = colors.cardGray)
            }

            Spacer(Modifier.height(8.dp))
            DisclaimerText()
            Spacer(Modifier.height(8.dp))
            }

            val shareText = buildString {
                append(if (isPast) "ENFLASYON - GECMIS KARSILIGI\n" else "ENFLASYON - GELECEK DEGERI\n")
                append("Bugunki tutar: ${formatMoney(amt)} TL\n")
                if (isPast) append("$targetYear yilindaki karsiligi: ${formatMoney(equivalentAmt)} TL\n")
                else append("$targetYear yilinda gereken tutar: ${formatMoney(equivalentAmt)} TL\n")
                append("\nYil bazinda:\n")
                resultRows.forEach { append("${it.year}: %${"%.1f".format(it.rate)} | O yila ozel: ${formatMoney(it.yearlyValue)} TL | Kumulatif: ${formatMoney(it.cumulativeValue)} TL\n") }
                append("\nBaretim Mavi")
            }
            ShareButton {
                context.startActivity(Intent.createChooser(
                    Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, shareText) },
                    "Paylas"
                ))
            }

        }
    }

    if (showInfoDialog) {
        AlertDialog(
            onDismissRequest = { showInfoDialog = false },
            title = { Text("Enflasyon Hesaplama") },
            text = { Text(
                "Bugunki paranizin gecmisteki veya gelecekteki degerini gosterir.\n\n" +
                "GECMIS: Bugun 40.000 TL var. Bu para 2020'de kac TL'ydi?\n" +
                "GELECEK: Bugun 40.000 TL var. 2028'de ayni alim gucunu korumak icin kac TL lazim?\n\n" +
                "Gercek oranlar: TUIK (1975-2024)\n" +
                "Tahmini oranlar: 2025 ve sonrasi (*)\n" +
                "Manuel oran: Kendi tahmin oraninizi girebilirsiniz.",
                fontSize = 13.sp
            ) },
            confirmButton = { TextButton(onClick = { showInfoDialog = false }) { Text("Tamam") } }
        )
    }
}

@Composable
private fun YearPicker(
    value: Int,
    minYear: Int,
    maxYear: Int,
    onValueChange: (Int) -> Unit
) {
    val colors = LocalAppColors.current
    Row(verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        IconButton(
            onClick = { if (value > minYear) onValueChange(value - 1) },
            modifier = Modifier.size(36.dp)
        ) {
            Icon(Icons.Default.RemoveCircleOutline, null,
                tint = if (value > minYear) PurplePrimary else colors.cardGray,
                modifier = Modifier.size(22.dp))
        }
        Text(value.toString(),
            fontWeight = FontWeight.Bold, fontSize = 16.sp,
            color = colors.textPrimary,
            modifier = Modifier.width(52.dp), textAlign = TextAlign.Center)
        IconButton(
            onClick = { if (value < maxYear) onValueChange(value + 1) },
            modifier = Modifier.size(36.dp)
        ) {
            Icon(Icons.Default.AddCircleOutline, null,
                tint = if (value < maxYear) PurplePrimary else colors.cardGray,
                modifier = Modifier.size(22.dp))
        }
    }
}
