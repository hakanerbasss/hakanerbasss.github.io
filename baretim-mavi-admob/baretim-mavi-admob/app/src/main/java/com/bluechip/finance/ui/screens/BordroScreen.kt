package com.bluechip.finance.ui.screens

import android.content.Intent
import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
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
import com.bluechip.finance.data.HistoryEntry
import com.bluechip.finance.data.HistoryManager
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.ui.components.*
import com.bluechip.finance.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.URL
import java.util.*
import com.bluechip.finance.util.TaxCalculator

@Composable
fun BordroScreen() {
    val context = LocalContext.current; val colors = LocalAppColors.current
    val scrollState = rememberScrollState(); val scope = rememberCoroutineScope()
    val profileManager = remember { ProfileManager(context) }
    var salary by remember { mutableStateOf("") }; var profileLoaded by remember { mutableStateOf(false) }
    var selectedMonth by remember { mutableIntStateOf(Calendar.getInstance().get(Calendar.MONTH)) }
    var overtimeHours by remember { mutableStateOf("") }
    var showResult by remember { mutableStateOf(false) }; var showMonthDialog by remember { mutableStateOf(false) }
    val prefs = androidx.compose.ui.platform.LocalContext.current.getSharedPreferences("app_prefs", android.content.Context.MODE_PRIVATE)
    var isSimpleMode by remember { mutableStateOf(prefs.getBoolean("bordro_simple_mode", false)) }
    var minWageGross by remember { mutableDoubleStateOf(33030.0) }; var sgkRate by remember { mutableDoubleStateOf(0.14) }
    var unemploymentRate by remember { mutableDoubleStateOf(0.01) }; var stampTaxRate by remember { mutableDoubleStateOf(0.00759) }
    var taxBrackets by remember { mutableStateOf(listOf(Pair(190000.0,0.15), Pair(550000.0,0.20), Pair(1900000.0,0.27), Pair(6600000.0,0.35), Pair(999999999.0,0.40))) }
    val months = remember { listOf("Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık") }

    // Sonuç state
    var bGross by remember { mutableDoubleStateOf(0.0) }; var bOt by remember { mutableDoubleStateOf(0.0) }; var bTotalGross by remember { mutableDoubleStateOf(0.0) }
    var bSgk by remember { mutableDoubleStateOf(0.0) }; var bUnemp by remember { mutableDoubleStateOf(0.0) }; var bIncome by remember { mutableDoubleStateOf(0.0) }
    var bStamp by remember { mutableDoubleStateOf(0.0) }; var bAgi by remember { mutableDoubleStateOf(0.0) }; var bNet by remember { mutableDoubleStateOf(0.0) }
    var bEmpSgk by remember { mutableDoubleStateOf(0.0) }; var bEmpUnemp by remember { mutableDoubleStateOf(0.0) }; var bEmpTotal by remember { mutableDoubleStateOf(0.0) }
    var bBracketPct by remember { mutableStateOf("") }; var bCumul by remember { mutableDoubleStateOf(0.0) }

    LaunchedEffect(Unit) { val p = profileManager.load(); if (p.isLoggedIn && p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileLoaded = true } }

    fun fetchParams() { scope.launch { withContext(Dispatchers.IO) { try {
        val json = URL("https://raw.githubusercontent.com/hakanerbasss/baretim-mavi/main/tax_parameters.json?t=${System.currentTimeMillis()}").readText()
        val obj = JSONObject(json); minWageGross = obj.getDouble("min_wage_gross"); sgkRate = obj.getDouble("sgk_employee_rate")
        unemploymentRate = obj.getDouble("unemployment_rate"); stampTaxRate = obj.getDouble("stamp_tax_rate")
        val arr = obj.getJSONArray("tax_brackets"); val list = mutableListOf<Pair<Double,Double>>()
        for (i in 0 until arr.length()) { val b = arr.getJSONObject(i); list.add(Pair(b.getDouble("limit"), b.getDouble("rate"))) }; taxBrackets = list
    } catch (_: Exception) {} } } }
    LaunchedEffect(Unit) { fetchParams() }

    fun calculate() {
        if (salary.isBlank()) { android.widget.Toast.makeText(context, "Lutfen maas giriniz", android.widget.Toast.LENGTH_SHORT).show(); return }
        val gross = salary.toDoubleOrNull() ?: run { android.widget.Toast.makeText(context, "Gecersiz deger", android.widget.Toast.LENGTH_SHORT).show(); return }
        val monthIdx = selectedMonth + 1; val ot = overtimeHours.toDoubleOrNull() ?: 0.0
        val otGross = if (ot > 0) (gross / 225.0) * 1.5 * ot else 0.0; val totalGross = gross + otGross
        val sgkW = totalGross * sgkRate; val unempW = totalGross * unemploymentRate; val baseMatrah = totalGross - sgkW - unempW
        val minWageBase = minWageGross - (minWageGross * sgkRate) - (minWageGross * unemploymentRate)
        val exempt = minOf(baseMatrah, minWageBase); val taxable = maxOf(0.0, baseMatrah - exempt); val cumul = taxable * monthIdx
        val incomeTax = TaxCalculator.monthlyIncomeTax(taxable, monthIdx, taxBrackets)
        var bRate = 0.15; for ((lim, rate) in taxBrackets) { if (cumul <= lim) { bRate = rate; break } }
        val minWageStamp = minWageGross * stampTaxRate
        val stampTax = maxOf(0.0, totalGross * stampTaxRate - minWageStamp); val agiAmount = exempt * bRate + minWageStamp
        val sgkEmp = totalGross * 0.205; val unempEmp = totalGross * 0.02
        bGross = gross; bOt = otGross; bTotalGross = totalGross; bSgk = sgkW; bUnemp = unempW; bIncome = incomeTax; bStamp = stampTax; bAgi = agiAmount
        bNet = totalGross - sgkW - unempW - incomeTax - stampTax; bEmpSgk = sgkEmp; bEmpUnemp = unempEmp; bEmpTotal = totalGross + sgkEmp + unempEmp
        bBracketPct = "%${(bRate*100).toInt()}"; bCumul = cumul
        showResult = true
        scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
        HistoryManager.save(context, HistoryEntry(
            screenId = "bordro", timestamp = System.currentTimeMillis(),
            label = "${months[selectedMonth]} — ${formatMoney(gross)}₺ brüt",
            resultSummary = "Net: ${formatMoney(bNet)}₺",
            salary = salary
        ))
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        androidx.compose.animation.AnimatedVisibility(
            visible = !showResult,
            enter = androidx.compose.animation.expandVertically(),
            exit = androidx.compose.animation.shrinkVertically()
        ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        SectionHeader("BORDRO SİMÜLATÖRÜ", Icons.Default.Description)
        CurrencyField(value = salary, onValueChange = { salary = it; profileLoaded = false }, label = "Brüt Maaş (₺)")
        if (profileLoaded) ProfileAutoFillNote()
        NumberField(value = overtimeHours, onValueChange = { overtimeHours = it }, label = "Fazla Mesai Saati (opsiyonel)")
        SelectorButton("Ay: ${months[selectedMonth]}") { showMonthDialog = true }
        HistoryCard(screenId = "bordro") { restored -> salary = restored; profileLoaded = false }
        ProfileFillButton {
            val p = profileManager.load()
            if (p.isLoggedIn && p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileLoaded = true }
        }
        ActionButtons(onCalculate = { calculate() }, onReset = { salary = ""; overtimeHours = ""; showResult = false; profileLoaded = false })
        } // inputs column
        } // AnimatedVisibility
        ResultCard(visible = showResult) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
            ) {
                Text("BORDRO - ${months[selectedMonth].uppercase()}", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = MaterialTheme.colorScheme.primary)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(
                        selected = isSimpleMode,
                        onClick = { isSimpleMode = true; prefs.edit().putBoolean("bordro_simple_mode", true).apply() },
                        label = { Text("Özet", fontSize = 11.sp) },
                        leadingIcon = if (isSimpleMode) {{ Icon(Icons.Default.Check, null, Modifier.size(14.dp)) }} else null
                    )
                    FilterChip(
                        selected = !isSimpleMode,
                        onClick = { isSimpleMode = false; prefs.edit().putBoolean("bordro_simple_mode", false).apply() },
                        label = { Text("Detay", fontSize = 11.sp) },
                        leadingIcon = if (!isSimpleMode) {{ Icon(Icons.Default.Check, null, Modifier.size(14.dp)) }} else null
                    )
                }
            }
            Spacer(Modifier.height(12.dp))
            if (!isSimpleMode) Text("KAZANÇLAR", fontWeight = FontWeight.Bold, fontSize = 13.sp, color = colors.textSecondary)
            ResultLine("Brüt Maaş", "${formatMoney(bGross)}₺")
            if (bOt > 0) ResultLine("Fazla Mesai", "${formatMoney(bOt)}₺")
            ResultLine("TOPLAM BRÜT", "${formatMoney(bTotalGross)}₺", colors.textPrimary, true)
            if (!isSimpleMode) {
                HorizontalDivider(Modifier.padding(vertical = 8.dp))
                Text("İŞÇİ KESİNTİLERİ", fontWeight = FontWeight.Bold, fontSize = 13.sp, color = colors.textSecondary)
                ResultLine("SGK (%14)", "-${formatMoney(bSgk)}₺", colors.error)
                ResultLine("İşsizlik (%1)", "-${formatMoney(bUnemp)}₺", colors.error)
                ResultLine("Gelir Vergisi", "-${formatMoney(bIncome)}₺", colors.error)
                ResultLine("Damga Vergisi", "-${formatMoney(bStamp)}₺", colors.error)
                ResultLine("AGİ İstisnası", "+${formatMoney(bAgi)}₺", colors.success)
            }
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            BigResult("NET MAAŞ", "${formatMoney(bNet)}₺")
            if (!isSimpleMode) {
                HorizontalDivider(Modifier.padding(vertical = 8.dp))
                Text("İŞVEREN MALİYETİ", fontWeight = FontWeight.Bold, fontSize = 13.sp, color = colors.textSecondary)
                ResultLine("İşveren SGK (%20.5)", "${formatMoney(bEmpSgk)}₺")
                ResultLine("İşveren İşsizlik (%2)", "${formatMoney(bEmpUnemp)}₺")
                ResultLine("TOPLAM MALİYET", "${formatMoney(bEmpTotal)}₺", colors.warning, true)
                Spacer(Modifier.height(4.dp))
                Text("Vergi Dilimi: $bBracketPct (Küm: ${formatMoney(bCumul)}₺)", fontSize = 11.sp, color = colors.textSecondary)
            }
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
            ShareButton {
                val t = "📄 BORDRO ${months[selectedMonth]}\nBrüt: ${formatMoney(bTotalGross)}₺\nNet: ${formatMoney(bNet)}₺\nİşveren: ${formatMoney(bEmpTotal)}₺\n📱 Baretim Mavi"
                context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, t) }, "Paylaş"))
            }
        }
    }
    if (showMonthDialog) MonthPickerDialog(selectedMonth, onSelect = { selectedMonth = it; showMonthDialog = false }, onDismiss = { showMonthDialog = false })
}
