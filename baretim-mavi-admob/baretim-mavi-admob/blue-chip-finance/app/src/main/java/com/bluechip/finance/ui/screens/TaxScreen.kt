package com.bluechip.finance.ui.screens

import android.content.Intent
import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.ui.components.*
import com.bluechip.finance.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.URL
import java.util.*

data class TaxBracket(val limit: Double, val rate: Double)

@Composable
fun TaxScreen() {
    val context = LocalContext.current
    val colors = LocalAppColors.current
    val scrollState = rememberScrollState()
    val scope = rememberCoroutineScope()

    var salary by remember { mutableStateOf("") }
    var selectedMonth by remember { mutableIntStateOf(Calendar.getInstance().get(Calendar.MONTH)) }
    var showResult by remember { mutableStateOf(false) }
    var showMonthDialog by remember { mutableStateOf(false) }
    var showInfoDialog by remember { mutableStateOf(false) }

    var minWageGross by remember { mutableDoubleStateOf(33030.0) }
    var sgkRate by remember { mutableDoubleStateOf(0.14) }
    var unemploymentRate by remember { mutableDoubleStateOf(0.01) }
    var stampTaxRate by remember { mutableDoubleStateOf(0.00759) }
    var taxBrackets by remember { mutableStateOf(listOf(
        TaxBracket(190000.0, 0.15), TaxBracket(550000.0, 0.20),
        TaxBracket(1900000.0, 0.27), TaxBracket(6600000.0, 0.35), TaxBracket(999999999.0, 0.40)
    )) }
    var lastUpdate by remember { mutableStateOf("2026-02-02") }

    // DÜZELTME: Aralık dahil 12 ay
    val months = remember { listOf("Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık") }

    var rGross by remember { mutableStateOf("") }
    var rSgk by remember { mutableStateOf("") }
    var rUnemp by remember { mutableStateOf("") }
    var rBase by remember { mutableStateOf("") }
    var rExempt by remember { mutableStateOf("") }
    var rTaxable by remember { mutableStateOf("") }
    var rCumul by remember { mutableStateOf("") }
    var rMonthInfo by remember { mutableStateOf("") }
    var rBracket by remember { mutableStateOf("") }
    var rBracketInfo by remember { mutableStateOf("") }
    var rIncome by remember { mutableStateOf("") }
    var rStamp by remember { mutableStateOf("") }
    var rNet by remember { mutableStateOf("") }

    fun fetchParams() {
        scope.launch {
            withContext(Dispatchers.IO) {
                try {
                    val json = URL("https://raw.githubusercontent.com/hakanerbasss/baretim-mavi/main/tax_parameters.json?t=${System.currentTimeMillis()}").readText()
                    val obj = JSONObject(json)
                    lastUpdate = obj.getString("last_update")
                    minWageGross = obj.getDouble("min_wage_gross")
                    sgkRate = obj.getDouble("sgk_employee_rate")
                    unemploymentRate = obj.getDouble("unemployment_rate")
                    stampTaxRate = obj.getDouble("stamp_tax_rate")
                    val arr = obj.getJSONArray("tax_brackets")
                    val list = mutableListOf<TaxBracket>()
                    for (i in 0 until arr.length()) { val b = arr.getJSONObject(i); list.add(TaxBracket(b.getDouble("limit"), b.getDouble("rate"))) }
                    taxBrackets = list
                } catch (_: Exception) {}
            }
        }
    }

    LaunchedEffect(Unit) { fetchParams() }

    fun calculate() {
        val gross = salary.toDoubleOrNull() ?: return
        val monthIdx = selectedMonth + 1
        val sgk = gross * sgkRate; val unemp = gross * unemploymentRate
        val baseMatrah = gross - sgk - unemp
        val exempt = minOf(baseMatrah, minWageGross - (minWageGross * sgkRate) - (minWageGross * unemploymentRate))
        val taxable = maxOf(0.0, baseMatrah - exempt)
        val cumul = taxable * monthIdx
        var bRate = 0.15; var bInfo = ""
        for (i in taxBrackets.indices) {
            if (cumul <= taxBrackets[i].limit) {
                bRate = taxBrackets[i].rate; val lower = if (i == 0) 0.0 else taxBrackets[i-1].limit
                bInfo = "${formatMoney(lower)} - ${formatMoney(taxBrackets[i].limit)} arası"; break
            }
        }
        val incomeTax = taxable * bRate; val stampTax = gross * stampTaxRate
        val net = gross - sgk - unemp - incomeTax - stampTax

        rGross = "${formatMoney(gross)}₺"; rSgk = "-${formatMoney(sgk)}₺"
        rUnemp = "-${formatMoney(unemp)}₺"; rBase = "${formatMoney(baseMatrah)}₺"
        rExempt = "-${formatMoney(exempt)}₺"; rTaxable = "${formatMoney(taxable)}₺"
        rCumul = "${formatMoney(cumul)}₺"; rMonthInfo = "$monthIdx aylık toplam"
        rBracket = "%${(bRate*100).toInt()}"; rBracketInfo = "($bInfo)"
        rIncome = "-${formatMoney(incomeTax)}₺"; rStamp = "-${formatMoney(stampTax)}₺"
        rNet = "${formatMoney(net)}₺"
        showResult = true
        scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        SectionHeader("VERGİ DİLİMİ HESAPLAMA", Icons.Default.Receipt, onInfoClick = { showInfoDialog = true })
        UpdateStatusBar(lastUpdate) {
            fetchParams()
            Toast.makeText(context, "Güncelleniyor...", Toast.LENGTH_SHORT).show()
        }
        CurrencyField(value = salary, onValueChange = { salary = it }, label = "Brüt Maaş (₺)")
        SelectorButton("Ay: ${months[selectedMonth]}") { showMonthDialog = true }
        ActionButtons(onCalculate = { calculate() }, onReset = {
            salary = ""; selectedMonth = Calendar.getInstance().get(Calendar.MONTH); showResult = false
        })
        ResultCard(visible = showResult) {
            Text("SONUÇ", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)
            Spacer(Modifier.height(8.dp))
            Text("Brüt Maaş: $rGross", fontWeight = FontWeight.Bold, color = colors.textPrimary)
            Text("SGK (%${(sgkRate*100).toInt()}): $rSgk", color = colors.error)
            Text("İşsizlik (%${(unemploymentRate*100).toInt()}): $rUnemp", color = colors.error)
            HorizontalDivider(Modifier.padding(vertical = 6.dp))
            Text("Matrah: $rBase", color = colors.textPrimary)
            Text("Muafiyet: $rExempt", color = colors.success)
            Text("Vergiye Tabi: $rTaxable", fontWeight = FontWeight.Bold, color = colors.textPrimary)
            HorizontalDivider(Modifier.padding(vertical = 6.dp))
            Text("Kümülatif: $rCumul", color = colors.textPrimary)
            Text("ℹ️ $rMonthInfo", fontSize = 12.sp, color = colors.textSecondary)
            Text("🎯 Vergi Dilimi: $rBracket", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            Text(rBracketInfo, fontSize = 12.sp, color = colors.textSecondary)
            HorizontalDivider(Modifier.padding(vertical = 6.dp))
            Text("Gelir Vergisi: $rIncome", color = colors.error)
            Text("Damga Vergisi: $rStamp", color = colors.error)
            Spacer(Modifier.height(8.dp))
            BigResult("NET MAAŞ", "💰 $rNet")
            ShareButton {
                val text = "💰 VERGİ\nBrüt: $rGross\nSGK: $rSgk\nDilim: $rBracket\nNet: $rNet\n📱 Baretim Mavi"
                context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text) }, "Paylaş"))
            }
        }
    }

    // DÜZELTME: Aralık görünen ay seçim dialogu
    if (showMonthDialog) {
        AlertDialog(onDismissRequest = { showMonthDialog = false }, title = { Text("Ay Seçin") }, text = {
            Column {
                months.forEachIndexed { i, m ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                        RadioButton(selected = selectedMonth == i, onClick = { selectedMonth = i; showMonthDialog = false })
                        Spacer(Modifier.width(8.dp))
                        Text(m, fontSize = 14.sp)
                    }
                }
            }
        }, confirmButton = { TextButton(onClick = { showMonthDialog = false }) { Text("Kapat") } })
    }

    if (showInfoDialog) {
        AlertDialog(onDismissRequest = { showInfoDialog = false }, title = { Text("Vergi Dilimi Rehberi") }, text = {
            Text(buildString {
                append("📊 $lastUpdate Vergi Dilimleri:\n\n")
                var prev = 0.0
                taxBrackets.forEach { b -> val lim = if (b.limit >= 999999999) "+" else formatMoney(b.limit)
                    append("${formatMoney(prev)} - ${lim}₺ → %${(b.rate*100).toInt()}\n"); prev = b.limit }
                append("\n❌ Asgari ücretliler muaf (${formatMoney(minWageGross)}₺ altı)")
            }, fontSize = 13.sp)
        }, confirmButton = { TextButton(onClick = { showInfoDialog = false }) { Text("Tamam") } })
    }
}
