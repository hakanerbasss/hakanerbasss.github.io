package com.bluechip.finance.ui.screens

import android.app.DatePickerDialog
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
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun SeveranceScreen() {
    val context = LocalContext.current
    val colors = LocalAppColors.current
    val scrollState = rememberScrollState()
    val scope = rememberCoroutineScope()
    val dateFormat = remember { SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()) }

    var startDate by remember { mutableStateOf<Calendar?>(null) }
    var endDate by remember { mutableStateOf<Calendar?>(null) }
    var startText by remember { mutableStateOf("Tarih Seç") }
    var endText by remember { mutableStateOf("Tarih Seç") }
    var salary by remember { mutableStateOf("") }
    var showResult by remember { mutableStateOf(false) }
    var showReasonDialog by remember { mutableStateOf(false) }
    var showNoticeDialog by remember { mutableStateOf(false) }
    var showInfoDialog by remember { mutableStateOf(false) }
    var noticeGiven by remember { mutableStateOf(false) }

    val reasons = listOf("İşveren Feshi", "İşçi Haklı Feshi", "Emeklilik", "Askerlik", "Evlilik (Kadın, 1 Yıl İçinde)", "İşçi Haksız Feshi", "Deneme Süresi Feshi")
    var selectedReason by remember { mutableStateOf(reasons[0]) }

    var severanceCeiling by remember { mutableDoubleStateOf(64948.77) }
    var stampTaxRate by remember { mutableDoubleStateOf(0.00759) }
    var lastUpdate by remember { mutableStateOf("2026-02-02") }

    var resultDuration by remember { mutableStateOf("") }
    var resultSevGross by remember { mutableStateOf("") }
    var resultSevTax by remember { mutableStateOf("") }
    var resultSevNet by remember { mutableStateOf("") }
    var resultNoticePeriod by remember { mutableStateOf("") }
    var resultNotGross by remember { mutableStateOf("") }
    var resultNotTax by remember { mutableStateOf("") }
    var resultNotNet by remember { mutableStateOf("") }
    var resultTotal by remember { mutableStateOf("") }
    var resultInfo by remember { mutableStateOf("") }

    fun fetchParams() {
        scope.launch {
            withContext(Dispatchers.IO) {
                try {
                    val json = URL("https://raw.githubusercontent.com/hakanerbasss/baretim-mavi/main/tax_parameters.json?t=${System.currentTimeMillis()}").readText()
                    val obj = JSONObject(json)
                    severanceCeiling = obj.getDouble("severance_ceiling")
                    stampTaxRate = obj.getDouble("stamp_tax_rate")
                    lastUpdate = obj.getString("last_update")
                } catch (_: Exception) {}
            }
        }
    }

    LaunchedEffect(Unit) { fetchParams() }

    fun showPicker(isStart: Boolean) {
        val cal = Calendar.getInstance()
        DatePickerDialog(context, { _, y, m, d ->
            val sel = Calendar.getInstance().apply { set(y, m, d) }
            if (isStart) { startDate = sel; startText = dateFormat.format(sel.time) }
            else { endDate = sel; endText = dateFormat.format(sel.time) }
        }, cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)).show()
    }

    fun calculate() {
        val sd = startDate ?: return; val ed = endDate ?: return; val sal = salary.toDoubleOrNull() ?: return
        val diffMillis = ed.timeInMillis - sd.timeInMillis + 86400000
        val totalDays = (diffMillis / 86400000).toInt()
        val years = totalDays / 365; val months = (totalDays % 365) / 30; val days = (totalDays % 365) % 30
        resultDuration = "$years yıl $months ay $days gün"
        val sevEligible = !selectedReason.contains("Haksız") && !selectedReason.contains("Deneme")
        var sevGross = 0.0; var sevTax = 0.0; var sevNet = 0.0
        if (sevEligible) { sevGross = minOf(sal, severanceCeiling) * (totalDays / 365.0); sevTax = sevGross * stampTaxRate; sevNet = sevGross - sevTax }
        resultSevGross = "${formatMoney(sevGross)}₺"; resultSevTax = "${formatMoney(sevTax)}₺"; resultSevNet = "${formatMoney(sevNet)}₺"
        val noticeDays = when { totalDays < 180 -> 14; totalDays < 547 -> 28; totalDays < 1095 -> 42; else -> 56 }
        var notGross = 0.0; var notTax = 0.0; var notNet = 0.0
        if (!noticeGiven) { notGross = (sal / 30.0) * noticeDays; notTax = notGross * stampTaxRate; notNet = notGross - notTax }
        resultNoticePeriod = "${noticeDays/7} hafta ($noticeDays gün)" + if (noticeGiven) " - Verildi" else ""
        resultNotGross = "${formatMoney(notGross)}₺"; resultNotTax = "${formatMoney(notTax)}₺"; resultNotNet = "${formatMoney(notNet)}₺"
        resultTotal = "${formatMoney(sevNet + notNet)}₺"
        resultInfo = buildString {
            if (!sevEligible) append("⚠️ $selectedReason durumunda kıdem hakkı yoktur.\n")
            else if (sal > severanceCeiling) append("ℹ️ Tavan üzerinden hesaplandı (${formatMoney(severanceCeiling)}₺)\n")
            if (noticeGiven) append("✓ İhbar verildiği için ihbar tazminatı yok.")
        }
        showResult = true
        scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        SectionHeader("KIDEM & İHBAR TAZMİNATI", Icons.Default.AccountBalance, onInfoClick = { showInfoDialog = true })
        UpdateStatusBar(lastUpdate) {
            fetchParams()
            Toast.makeText(context, "Güncelleniyor...", Toast.LENGTH_SHORT).show()
        }
        Text("İşe Giriş Tarihi", fontSize = 14.sp, color = colors.textPrimary)
        DatePickerButton(startText) { showPicker(true) }
        Text("İşten Çıkış Tarihi", fontSize = 14.sp, color = colors.textPrimary)
        DatePickerButton(endText) { showPicker(false) }
        CurrencyField(value = salary, onValueChange = { salary = it }, label = "Brüt Maaş (₺)")
        SelectorButton(selectedReason) { showReasonDialog = true }
        SelectorButton(if (noticeGiven) "Evet (İhbar verildi)" else "Hayır (İhbar verilmedi)") { showNoticeDialog = true }
        ActionButtons(onCalculate = { calculate() }, onReset = {
            startDate = null; endDate = null; startText = "Tarih Seç"; endText = "Tarih Seç"; salary = ""; selectedReason = reasons[0]; noticeGiven = false; showResult = false
        })
        ResultCard(visible = showResult) {
            Text("SONUÇ", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)
            Spacer(Modifier.height(8.dp))
            Text("Çalışma: $resultDuration", fontWeight = FontWeight.Bold, color = colors.textPrimary)
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("🎁 KIDEM TAZMİNATI", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            Text("Brüt: $resultSevGross", color = colors.textPrimary); Text("Damga: $resultSevTax", color = colors.textSecondary)
            Text("Net: $resultSevNet", fontWeight = FontWeight.Bold, color = colors.success)
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("⚖️ İHBAR TAZMİNATI", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            Text("Süre: $resultNoticePeriod", color = colors.textPrimary)
            Text("Brüt: $resultNotGross", color = colors.textPrimary); Text("Damga: $resultNotTax", color = colors.textSecondary)
            Text("Net: $resultNotNet", fontWeight = FontWeight.Bold, color = colors.success)
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            BigResult("TOPLAM NET", resultTotal)
            if (resultInfo.isNotEmpty()) Text(resultInfo, fontSize = 12.sp, color = colors.warning)
            Spacer(Modifier.height(8.dp))
            ShareButton {
                val text = "🎁 KIDEM & İHBAR\nSüre: $resultDuration\nKıdem Net: $resultSevNet\nİhbar Net: $resultNotNet\nTOPLAM: $resultTotal\n📱 Baretim Mavi"
                context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text) }, "Paylaş"))
            }
        }
    }

    if (showReasonDialog) {
        AlertDialog(onDismissRequest = { showReasonDialog = false }, title = { Text("Çıkış Nedeni") }, text = {
            Column { reasons.forEach { r -> Row(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                RadioButton(selected = selectedReason == r, onClick = { selectedReason = r; showReasonDialog = false })
                Spacer(Modifier.width(8.dp)); Text(r, fontSize = 14.sp) } } }
        }, confirmButton = { TextButton(onClick = { showReasonDialog = false }) { Text("Kapat") } })
    }
    if (showNoticeDialog) {
        AlertDialog(onDismissRequest = { showNoticeDialog = false }, title = { Text("İhbar Verildi mi?") }, text = {
            Column { listOf(false to "Hayır", true to "Evet").forEach { (v, l) -> Row(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                RadioButton(selected = noticeGiven == v, onClick = { noticeGiven = v; showNoticeDialog = false })
                Spacer(Modifier.width(8.dp)); Text(l) } } }
        }, confirmButton = { TextButton(onClick = { showNoticeDialog = false }) { Text("Kapat") } })
    }
    if (showInfoDialog) {
        AlertDialog(onDismissRequest = { showInfoDialog = false }, title = { Text("Kıdem & İhbar Nedir?") }, text = {
            Text("🎁 KIDEM: 1+ yıl çalışana her yıl 30 günlük brüt.\nTavan: ${formatMoney(severanceCeiling)}₺\n\n⚖️ İHBAR SÜRELERİ:\n<6 ay: 2 hafta\n6ay-1.5yıl: 4 hafta\n1.5-3 yıl: 6 hafta\n3+ yıl: 8 hafta", fontSize = 13.sp)
        }, confirmButton = { TextButton(onClick = { showInfoDialog = false }) { Text("Tamam") } })
    }
}
