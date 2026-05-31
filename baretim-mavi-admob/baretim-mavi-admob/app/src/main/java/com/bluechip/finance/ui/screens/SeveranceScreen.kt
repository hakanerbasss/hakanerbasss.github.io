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
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun SeveranceScreen() {
    val context = LocalContext.current; val colors = LocalAppColors.current
    val activity = context as? android.app.Activity
    val scrollState = rememberScrollState(); val scope = rememberCoroutineScope()
    val profileManager = remember { ProfileManager(context) }
    val dateFormat = remember { SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()) }
    var startDate by remember { mutableStateOf<Calendar?>(null) }; var endDate by remember { mutableStateOf<Calendar?>(null) }
    var startText by remember { mutableStateOf("Tarih Seç") }; var endText by remember { mutableStateOf("Tarih Seç") }
    var salary by remember { mutableStateOf("") }; var showResult by remember { mutableStateOf(false) }
    var showReasonDialog by remember { mutableStateOf(false) }; var showNoticeDialog by remember { mutableStateOf(false) }; var showInfoDialog by remember { mutableStateOf(false) }
    var noticeGiven by remember { mutableStateOf(false) }; var leaveDays by remember { mutableStateOf("") }
    var profileStartLoaded by remember { mutableStateOf(false) }; var profileSalaryLoaded by remember { mutableStateOf(false) }
    val reasons = listOf("İşveren Feshi","İşçi Haklı Feshi","Emeklilik","Askerlik","Evlilik (Kadın, 1 Yıl İçinde)","İşçi Haksız Feshi","Deneme Süresi Feshi")
    var selectedReason by remember { mutableStateOf(reasons[0]) }
    var severanceCeiling by remember { mutableDoubleStateOf(64948.77) }; var stampTaxRate by remember { mutableDoubleStateOf(0.00759) }; var lastUpdate by remember { mutableStateOf("2026-02-02") }
    var resultDuration by remember { mutableStateOf("") }; var resultSevGross by remember { mutableStateOf("") }; var resultSevTax by remember { mutableStateOf("") }
    var resultSevNet by remember { mutableStateOf("") }; var resultNoticePeriod by remember { mutableStateOf("") }; var resultNotGross by remember { mutableStateOf("") }
    var resultNotTax by remember { mutableStateOf("") }; var resultNotNet by remember { mutableStateOf("") }; var resultTotal by remember { mutableStateOf("") }; var resultInfo by remember { mutableStateOf("") }
    var resultLeaveGross by remember { mutableStateOf("") }; var resultLeaveTax by remember { mutableStateOf("") }; var resultLeaveNet by remember { mutableStateOf("") }
    var projectionText by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        val p = profileManager.load()
        if (p.isLoggedIn) {
            if (p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileSalaryLoaded = true }
            if (p.startDateMillis > 0L) { val cal = Calendar.getInstance().apply { timeInMillis = p.startDateMillis }; startDate = cal; startText = dateFormat.format(cal.time); profileStartLoaded = true }
        }
    }

    fun fetchParams() { scope.launch { withContext(Dispatchers.IO) { try {
        val json = URL("https://raw.githubusercontent.com/hakanerbasss/baretim-mavi/main/tax_parameters.json?t=${System.currentTimeMillis()}").readText()
        val obj = JSONObject(json); severanceCeiling = obj.getDouble("severance_ceiling"); stampTaxRate = obj.getDouble("stamp_tax_rate"); lastUpdate = obj.getString("last_update")
    } catch (_: Exception) {} } } }
    LaunchedEffect(Unit) { fetchParams() }

    var showStartDatePicker by remember { mutableStateOf(false) }
    var showEndDatePicker by remember { mutableStateOf(false) }

    if (showStartDatePicker) {
        WheelDatePickerDialog(title = "İşe Giriş Tarihi", onDismiss = { showStartDatePicker = false }) { sel ->
            startDate = sel; startText = dateFormat.format(sel.time); profileStartLoaded = false
        }
    }
    if (showEndDatePicker) {
        WheelDatePickerDialog(title = "İşten Çıkış Tarihi", onDismiss = { showEndDatePicker = false }) { sel ->
            endDate = sel; endText = dateFormat.format(sel.time)
        }
    }

    fun calculate() {
        val sd = startDate ?: run { android.widget.Toast.makeText(context, "Lutfen ise giris tarihi seciniz", android.widget.Toast.LENGTH_SHORT).show(); return }
        val ed = endDate ?: run { android.widget.Toast.makeText(context, "Lutfen isten cikis tarihi seciniz", android.widget.Toast.LENGTH_SHORT).show(); return }
        if (salary.isBlank()) { android.widget.Toast.makeText(context, "Lutfen maas giriniz", android.widget.Toast.LENGTH_SHORT).show(); return }
        val sal = salary.toDoubleOrNull() ?: run { android.widget.Toast.makeText(context, "Gecersiz maas degeri", android.widget.Toast.LENGTH_SHORT).show(); return }
        val totalDays = ((ed.timeInMillis - sd.timeInMillis + 86400000) / 86400000).toInt()
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
        val leaveNum = leaveDays.toDoubleOrNull() ?: 0.0
        var leaveGross = 0.0; var leaveTax = 0.0; var leaveNet = 0.0
        if (leaveNum > 0) { leaveGross = (sal / 30.0) * leaveNum; val lS = leaveGross * 0.14; val lU = leaveGross * 0.01; val lI = (leaveGross - lS - lU) * 0.15; leaveTax = lS + lU + lI + (leaveGross * stampTaxRate); leaveNet = leaveGross - leaveTax }
        resultLeaveGross = "${formatMoney(leaveGross)}₺"; resultLeaveTax = "${formatMoney(leaveTax)}₺"; resultLeaveNet = "${formatMoney(leaveNet)}₺"
        resultTotal = "${formatMoney(sevNet + notNet + leaveNet)}₺"
        resultInfo = buildString { if (!sevEligible) append("⚠️ $selectedReason: kıdem hakkı yok.\n") else if (sal > severanceCeiling) append("ℹ️ Tavan: ${formatMoney(severanceCeiling)}₺\n"); if (noticeGiven) append("✓ İhbar verildi.\n"); if (leaveNum > 0) append("📅 ${leaveNum.toInt()} gün izin dahil.") }
        if (sevEligible) { projectionText = buildString { append("📊 PROJEKSİYON\n"); listOf(6 to "+6 ay", 12 to "+1 yıl", 24 to "+2 yıl", 60 to "+5 yıl").forEach { (am, label) ->
            val fc = ed.clone() as Calendar; fc.add(Calendar.MONTH, am); val fd = ((fc.timeInMillis - sd.timeInMillis + 86400000) / 86400000).toInt()
            val fg = minOf(sal, severanceCeiling) * (fd / 365.0); val fn = fg - (fg * stampTaxRate); append("⏳ $label → ${formatMoney(fn)}₺\n") } } } else projectionText = ""
        activity?.let { act -> UnityAdsManager.showInterstitial(act) { showResult = true } }
            ?: run { showResult = true }
        scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
        HistoryManager.save(context, HistoryEntry(
            screenId = "severance", timestamp = System.currentTimeMillis(),
            label = "${formatMoney(sal)}₺ — $resultDuration",
            resultSummary = "Toplam: $resultTotal",
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
        SectionHeader("KIDEM & İHBAR TAZMİNATI", Icons.Default.AccountBalance) { showInfoDialog = true }
        UpdateStatusBar(lastUpdate) { fetchParams(); Toast.makeText(context, "Güncelleniyor...", Toast.LENGTH_SHORT).show() }
        Text("İşe Giriş Tarihi", fontSize = 14.sp, color = colors.textPrimary)
        DatePickerButton(startText) { showStartDatePicker = true }
        if (profileStartLoaded) ProfileAutoFillNote()
        Text("İşten Çıkış Tarihi", fontSize = 14.sp, color = colors.textPrimary); DatePickerButton(endText) { showEndDatePicker = true }
        CurrencyField(value = salary, onValueChange = { salary = it; profileSalaryLoaded = false }, label = "Brüt Maaş (₺)")
        if (profileSalaryLoaded) ProfileAutoFillNote()
        SelectorButton(selectedReason) { showReasonDialog = true }
        SelectorButton(if (noticeGiven) "Evet (İhbar verildi)" else "Hayır (İhbar verilmedi)") { showNoticeDialog = true }
        NumberField(value = leaveDays, onValueChange = { leaveDays = it }, label = "Kullanılmayan İzin Günü (opsiyonel)")
        HistoryCard(screenId = "severance") { restored -> salary = restored; profileSalaryLoaded = false }
        ProfileFillButton {
            val p = profileManager.load()
            if (p.isLoggedIn) {
                if (p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileSalaryLoaded = true }
                if (p.startDateMillis > 0L) { val cal = java.util.Calendar.getInstance().apply { timeInMillis = p.startDateMillis }; startDate = cal; startText = dateFormat.format(cal.time); profileStartLoaded = true }
            }
        }
        ActionButtons(onCalculate = { calculate() }, onReset = { startDate = null; endDate = null; startText = "Tarih Seç"; endText = "Tarih Seç"; salary = ""; selectedReason = reasons[0]; noticeGiven = false; leaveDays = ""; showResult = false; profileStartLoaded = false; profileSalaryLoaded = false })
        } // inputs column
        } // AnimatedVisibility
        ResultCard(visible = showResult) {
            Text("SONUÇ", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary); Spacer(Modifier.height(8.dp))
            ResultLine("Çalışma Süresi", resultDuration, colors.textPrimary, true); HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("🎁 KIDEM TAZMİNATI", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            ResultLine("Brüt", resultSevGross); ResultLine("Damga V.", resultSevTax, colors.textSecondary); ResultLine("Net", resultSevNet, colors.success, true)
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("⚖️ İHBAR TAZMİNATI", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            ResultLine("Süre", resultNoticePeriod); ResultLine("Brüt", resultNotGross); ResultLine("Net", resultNotNet, colors.success, true)
            if ((leaveDays.toDoubleOrNull() ?: 0.0) > 0) { HorizontalDivider(Modifier.padding(vertical = 8.dp)); Text("📅 İZİN ÜCRETİ", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                ResultLine("Brüt", resultLeaveGross); ResultLine("Net", resultLeaveNet, colors.success, true) }
            HorizontalDivider(Modifier.padding(vertical = 8.dp)); BigResult("TOPLAM NET ALACAK", resultTotal)
            if (resultInfo.isNotEmpty()) Text(resultInfo, fontSize = 12.sp, color = colors.warning)
            if (projectionText.isNotEmpty()) { HorizontalDivider(Modifier.padding(vertical = 8.dp)); Text(projectionText, fontSize = 12.sp, lineHeight = 18.sp, color = colors.info) }
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
            ShareButton { context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, "🎁 TAZMİNAT\nSüre: $resultDuration\nKıdem: $resultSevNet\nİhbar: $resultNotNet\nİzin: $resultLeaveNet\nTOPLAM: $resultTotal\n📱 Baretim Mavi") }, "Paylaş")) }
        }
        SupportUsCard(visible = showResult)
    }
    if (showReasonDialog) { AlertDialog(onDismissRequest = { showReasonDialog = false }, title = { Text("Çıkış Nedeni") }, text = { Column { reasons.forEach { r -> Row(Modifier.fillMaxWidth().padding(vertical = 6.dp)) { RadioButton(selected = selectedReason == r, onClick = { selectedReason = r; showReasonDialog = false }); Spacer(Modifier.width(8.dp)); Text(r, fontSize = 14.sp) } } } }, confirmButton = { TextButton(onClick = { showReasonDialog = false }) { Text("Kapat") } }) }
    if (showNoticeDialog) { AlertDialog(onDismissRequest = { showNoticeDialog = false }, title = { Text("İhbar Verildi mi?") }, text = { Column { listOf(false to "Hayır", true to "Evet").forEach { (v, l) -> Row(Modifier.fillMaxWidth().padding(vertical = 6.dp)) { RadioButton(selected = noticeGiven == v, onClick = { noticeGiven = v; showNoticeDialog = false }); Spacer(Modifier.width(8.dp)); Text(l) } } } }, confirmButton = { TextButton(onClick = { showNoticeDialog = false }) { Text("Kapat") } }) }
    if (showInfoDialog) { AlertDialog(onDismissRequest = { showInfoDialog = false }, title = { Text("Tazminat Rehberi") }, text = { Text("🎁 KIDEM: 1+ yıl, her yıl 30 gün brüt\nTavan: ${formatMoney(severanceCeiling)}₺\n\n⚖️ İHBAR: <6ay=2hf, 6ay-1.5yıl=4hf, 1.5-3yıl=6hf, 3+yıl=8hf\n\n📅 İZİN: Kullanılmayan izinler ücret olarak ödenir\n\n📊 PROJEKSİYON: Daha çalışsanız ne alırsınız", fontSize = 13.sp) }, confirmButton = { TextButton(onClick = { showInfoDialog = false }) { Text("Tamam") } }) }
}
