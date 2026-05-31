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
import com.bluechip.finance.UnityAdsManager
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

data class TaxBracket(val limit: Double, val rate: Double)

@Composable
fun TaxScreen() {
    val context = LocalContext.current; val colors = LocalAppColors.current
    val activity = context as? android.app.Activity
    val scrollState = rememberScrollState(); val scope = rememberCoroutineScope()
    val profileManager = remember { ProfileManager(context) }
    var salary by remember { mutableStateOf("") }
    var profileLoaded by remember { mutableStateOf(false) }
    var selectedMonth by remember { mutableIntStateOf(Calendar.getInstance().get(Calendar.MONTH)) }
    var showResult by remember { mutableStateOf(false) }; var showMonthDialog by remember { mutableStateOf(false) }; var showInfoDialog by remember { mutableStateOf(false) }
    var minWageGross by remember { mutableDoubleStateOf(33030.0) }; var sgkRate by remember { mutableDoubleStateOf(0.14) }
    var unemploymentRate by remember { mutableDoubleStateOf(0.01) }; var stampTaxRate by remember { mutableDoubleStateOf(0.00759) }
    var taxBrackets by remember { mutableStateOf(listOf(TaxBracket(190000.0,0.15),TaxBracket(550000.0,0.20),TaxBracket(1900000.0,0.27),TaxBracket(6600000.0,0.35),TaxBracket(999999999.0,0.40))) }
    var lastUpdate by remember { mutableStateOf("2026-02-02") }
    val months = remember { listOf("Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık") }
    var isNetMode by remember { mutableStateOf(false) }
    val prefs = androidx.compose.ui.platform.LocalContext.current.getSharedPreferences("app_prefs", android.content.Context.MODE_PRIVATE)
    var isSimpleMode by remember { mutableStateOf(prefs.getBoolean("tax_simple_mode", false)) }
    var rGross by remember { mutableStateOf("") }; var rSgk by remember { mutableStateOf("") }; var rUnemp by remember { mutableStateOf("") }
    var rBase by remember { mutableStateOf("") }; var rExempt by remember { mutableStateOf("") }; var rTaxable by remember { mutableStateOf("") }
    var rCumul by remember { mutableStateOf("") }; var rMonthInfo by remember { mutableStateOf("") }; var rBracket by remember { mutableStateOf("") }
    var rBracketInfo by remember { mutableStateOf("") }; var rIncome by remember { mutableStateOf("") }; var rStamp by remember { mutableStateOf("") }
    var rNet by remember { mutableStateOf("") }; var rAgiInfo by remember { mutableStateOf("") }; var rEmployerCost by remember { mutableStateOf("") }

    // Profil yükle
    LaunchedEffect(Unit) {
        val taxPrefs = context.getSharedPreferences("app_prefs", android.content.Context.MODE_PRIVATE)
        val netForTax = taxPrefs.getString("net_salary_for_tax", null)
        val openNetMode = taxPrefs.getBoolean("tax_open_net_mode", false)
        if (openNetMode && !netForTax.isNullOrBlank()) {
            salary = netForTax
            isNetMode = true
            profileLoaded = true
            taxPrefs.edit().remove("net_salary_for_tax").remove("tax_open_net_mode").apply()
        } else {
            val p = profileManager.load()
            if (p.isLoggedIn && p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileLoaded = true }
        }
    }

    fun fetchParams() { scope.launch { withContext(Dispatchers.IO) { try {
        val json = URL("https://raw.githubusercontent.com/hakanerbasss/baretim-mavi/main/tax_parameters.json?t=${System.currentTimeMillis()}").readText()
        val obj = JSONObject(json); lastUpdate = obj.getString("last_update"); minWageGross = obj.getDouble("min_wage_gross")
        sgkRate = obj.getDouble("sgk_employee_rate"); unemploymentRate = obj.getDouble("unemployment_rate"); stampTaxRate = obj.getDouble("stamp_tax_rate")
        val arr = obj.getJSONArray("tax_brackets"); val list = mutableListOf<TaxBracket>()
        for (i in 0 until arr.length()) { val b = arr.getJSONObject(i); list.add(TaxBracket(b.getDouble("limit"), b.getDouble("rate"))) }; taxBrackets = list
    } catch (_: Exception) {} } } }
    LaunchedEffect(Unit) { fetchParams() }

    fun calcBrutToNet(gross: Double, monthIdx: Int): Triple<Double, Double, String> {
        val sgk = gross * sgkRate; val unemp = gross * unemploymentRate; val baseMatrah = gross - sgk - unemp
        val minWageBase = minWageGross - (minWageGross * sgkRate) - (minWageGross * unemploymentRate)
        val exempt = minOf(baseMatrah, minWageBase); val taxable = maxOf(0.0, baseMatrah - exempt)
        val cumul = taxable * monthIdx
        var bRate = 0.15; var bInfo = ""
        for (i in taxBrackets.indices) { if (cumul <= taxBrackets[i].limit) { bRate = taxBrackets[i].rate; val lower = if (i == 0) 0.0 else taxBrackets[i-1].limit; bInfo = "${formatMoney(lower)} - ${formatMoney(taxBrackets[i].limit)} arası"; break } }
        val bracketPairs = taxBrackets.map { Pair(it.limit, it.rate) }
        val incomeTax = TaxCalculator.monthlyIncomeTax(taxable, monthIdx, bracketPairs)
        val minWageStamp = minWageGross * stampTaxRate; val fullStamp = gross * stampTaxRate; val stampTax = maxOf(0.0, fullStamp - minWageStamp)
        val net = gross - sgk - unemp - incomeTax - stampTax
        rGross = "${formatMoney(gross)}₺"; rSgk = "-${formatMoney(sgk)}₺"; rUnemp = "-${formatMoney(unemp)}₺"
        rBase = "${formatMoney(baseMatrah)}₺"; rExempt = "-${formatMoney(exempt)}₺"; rTaxable = "${formatMoney(taxable)}₺"
        rCumul = "${formatMoney(cumul)}₺"; rMonthInfo = "$monthIdx aylık toplam"
        rBracket = "%${(bRate*100).toInt()}"; rBracketInfo = "($bInfo)"; rIncome = "-${formatMoney(incomeTax)}₺"; rStamp = "-${formatMoney(stampTax)}₺"; rNet = "${formatMoney(net)}₺"
        val agiGelir = exempt * bRate; rAgiInfo = "💡 AGİ: ${formatMoney(agiGelir + minWageStamp)}₺"
        rEmployerCost = "${formatMoney(gross * 1.225)}₺"
        return Triple(net, bRate, bInfo)
    }

    fun calculateBrutToNet() {
            if (salary.isBlank()) { android.widget.Toast.makeText(context, "Lutfen maas giriniz", android.widget.Toast.LENGTH_SHORT).show(); return }
            val gross = salary.toDoubleOrNull() ?: run { android.widget.Toast.makeText(context, "Gecersiz deger", android.widget.Toast.LENGTH_SHORT).show(); return }
            calcBrutToNet(gross, selectedMonth + 1)
            activity?.let { act ->
                UnityAdsManager.showInterstitial(act) {
                    showResult = true
                    scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
                }
            } ?: run {
                showResult = true
                scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
            }
            HistoryManager.save(context, HistoryEntry(
                screenId = "tax", timestamp = System.currentTimeMillis(),
                label = "${months[selectedMonth]} — ${formatMoney(gross)}₺ brüt",
                resultSummary = "Net: $rNet",
                salary = salary
            ))
        }
    fun calculateNetToBrut() {
        val targetNet = salary.toDoubleOrNull() ?: return; val monthIdx = selectedMonth + 1
        var low = targetNet; var high = targetNet * 3.0
        repeat(50) { val mid = (low + high) / 2.0; val (calcNet, _, _) = calcBrutToNet(mid, monthIdx); if (calcNet < targetNet) low = mid else high = mid }
        calcBrutToNet((low + high) / 2.0, monthIdx)
        activity?.let { act ->
            UnityAdsManager.showInterstitial(act) {
                showResult = true
                scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
            }
        } ?: run {
            showResult = true
            scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
        }
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        androidx.compose.animation.AnimatedVisibility(
            visible = !showResult,
            enter = androidx.compose.animation.expandVertically(),
            exit = androidx.compose.animation.shrinkVertically()
        ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        SectionHeader("VERGİ DİLİMİ HESAPLAMA", Icons.Default.Receipt) { showInfoDialog = true }
        UpdateStatusBar(lastUpdate) { fetchParams(); Toast.makeText(context, "Güncelleniyor...", Toast.LENGTH_SHORT).show() }
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = !isNetMode, onClick = { isNetMode = false; showResult = false }, label = { Text("Brüt → Net", fontSize = 13.sp) },
                leadingIcon = if (!isNetMode) {{ Icon(Icons.Default.Check, null, Modifier.size(16.dp)) }} else null, modifier = Modifier.weight(1f))
            FilterChip(selected = isNetMode, onClick = { isNetMode = true; showResult = false }, label = { Text("Net → Brüt", fontSize = 13.sp) },
                leadingIcon = if (isNetMode) {{ Icon(Icons.Default.Check, null, Modifier.size(16.dp)) }} else null, modifier = Modifier.weight(1f))
        }
        CurrencyField(value = salary, onValueChange = { salary = it; profileLoaded = false }, label = if (isNetMode) "İstediğiniz Net Maaş (₺)" else "Brüt Maaş (₺)")
        if (profileLoaded && !isNetMode) ProfileAutoFillNote()
        SelectorButton("Ay: ${months[selectedMonth]}") { showMonthDialog = true }
        HistoryCard(screenId = "tax") { restored -> salary = restored; profileLoaded = false }
        if (!isNetMode) ProfileFillButton {
            val p = profileManager.load()
            if (p.isLoggedIn && p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileLoaded = true }
        }
        ActionButtons(onCalculate = { if (isNetMode) calculateNetToBrut() else calculateBrutToNet() },
            onReset = { salary = ""; selectedMonth = Calendar.getInstance().get(Calendar.MONTH); showResult = false; profileLoaded = false })
        } // inputs column
        } // AnimatedVisibility
        ResultCard(visible = showResult) {
            // Basit / Detayli toggle
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
            ) {
                Text(if (isNetMode) "NETTEN BRÜTE SONUÇ" else "SONUÇ", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(
                        selected = isSimpleMode,
                        onClick = { isSimpleMode = true; prefs.edit().putBoolean("tax_simple_mode", true).apply() },
                        label = { Text("Özet", fontSize = 11.sp) },
                        leadingIcon = if (isSimpleMode) {{ Icon(Icons.Default.Check, null, Modifier.size(14.dp)) }} else null
                    )
                    FilterChip(
                        selected = !isSimpleMode,
                        onClick = { isSimpleMode = false; prefs.edit().putBoolean("tax_simple_mode", false).apply() },
                        label = { Text("Detay", fontSize = 11.sp) },
                        leadingIcon = if (!isSimpleMode) {{ Icon(Icons.Default.Check, null, Modifier.size(14.dp)) }} else null
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            if (isNetMode) { ResultLine("Hedef Net", "${formatMoney(salary.toDoubleOrNull() ?: 0.0)}₺", MaterialTheme.colorScheme.primary, true); HorizontalDivider(Modifier.padding(vertical = 6.dp)) }
            ResultLine("Brüt Maaş", rGross, colors.textPrimary, true)
            if (!isSimpleMode) {
                ResultLine("SGK (%${(sgkRate*100).toInt()})", rSgk, colors.error)
                ResultLine("İşsizlik (%${(unemploymentRate*100).toInt()})", rUnemp, colors.error)
                HorizontalDivider(Modifier.padding(vertical = 6.dp))
                ResultLine("Matrah", rBase)
                ResultLine("AGİ Muafiyet", rExempt, colors.success)
                ResultLine("Vergiye Tabi", rTaxable, colors.textPrimary, true)
                HorizontalDivider(Modifier.padding(vertical = 6.dp))
                ResultLine("Kümülatif", rCumul)
                Text("ℹ️ $rMonthInfo", fontSize = 11.sp, color = colors.textSecondary)
            }
            ResultLine("Vergi Dilimi", "$rBracket $rBracketInfo", MaterialTheme.colorScheme.primary, true)
            if (!isSimpleMode) {
                HorizontalDivider(Modifier.padding(vertical = 6.dp))
                ResultLine("Gelir Vergisi", rIncome, colors.error)
                ResultLine("Damga Vergisi", rStamp, colors.error)
                Text(rAgiInfo, fontSize = 11.sp, color = colors.success)
                Spacer(Modifier.height(4.dp))
            }
            BigResult("NET MAAŞ", "💰 $rNet")
            if (isNetMode && !isSimpleMode) { HorizontalDivider(Modifier.padding(vertical = 6.dp)); ResultLine("İşveren Maliyeti", rEmployerCost, colors.warning, true) }
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
                DisclaimerText()
            ShareButton { val t = if (isNetMode) "💼 NETTEN BRÜTE\nBrüt: $rGross\nNet: $rNet\nİşveren: $rEmployerCost" else "💰 VERGİ\nBrüt: $rGross\nDilim: $rBracket\nNet: $rNet"
                context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, "$t\n📱 Baretim Mavi") }, "Paylaş")) }
        }
        SupportUsCard(visible = showResult)
    }
    if (showMonthDialog) MonthPickerDialog(selectedMonth, onSelect = { selectedMonth = it; showMonthDialog = false }, onDismiss = { showMonthDialog = false })
    if (showInfoDialog) { AlertDialog(onDismissRequest = { showInfoDialog = false }, title = { Text("Vergi & AGİ Rehberi") }, text = {
        Text(buildString { append("📊 $lastUpdate Vergi Dilimleri:\n\n"); var prev = 0.0; taxBrackets.forEach { b -> val lim = if (b.limit >= 999999999) "+" else formatMoney(b.limit); append("${formatMoney(prev)} - ${lim}₺ → %${(b.rate*100).toInt()}\n"); prev = b.limit }
            append("\n💡 AGİ: Asgari ücretin vergisi kadar istisna\nAsgari Brüt: ${formatMoney(minWageGross)}₺") }, fontSize = 13.sp)
    }, confirmButton = { TextButton(onClick = { showInfoDialog = false }) { Text("Tamam") } }) }
}
