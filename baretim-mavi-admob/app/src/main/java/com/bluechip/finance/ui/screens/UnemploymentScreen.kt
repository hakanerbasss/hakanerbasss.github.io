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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
fun UnemploymentScreen() {
    val context = LocalContext.current; val colors = LocalAppColors.current
    val scrollState = rememberScrollState(); val scope = rememberCoroutineScope()
    val profileManager = remember { ProfileManager(context) }
    val dateFormat = remember { SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()) }
    var salary by remember { mutableStateOf("") }; var premDays by remember { mutableStateOf("") }
    var startDate by remember { mutableStateOf<Calendar?>(null) }; var endDate by remember { mutableStateOf<Calendar?>(null) }
    var startText by remember { mutableStateOf("Tarih Seç") }; var endText by remember { mutableStateOf("Tarih Seç") }
    var showResult by remember { mutableStateOf(false) }; var showInfoDialog by remember { mutableStateOf(false) }
    var profileStartLoaded by remember { mutableStateOf(false) }; var profileSalaryLoaded by remember { mutableStateOf(false) }
    var minWageGross by remember { mutableDoubleStateOf(33030.0) }
    var lastUpdate by remember { mutableStateOf("2026-02-02") }

    // Sonuç
    var rMonthly by remember { mutableDoubleStateOf(0.0) }; var rDuration by remember { mutableIntStateOf(0) }; var rTotal by remember { mutableDoubleStateOf(0.0) }
    var rDays by remember { mutableIntStateOf(0) }; var rError by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        val p = profileManager.load()
        if (p.isLoggedIn) {
            if (p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileSalaryLoaded = true }
            if (p.startDateMillis > 0L) { val cal = Calendar.getInstance().apply { timeInMillis = p.startDateMillis }; startDate = cal; startText = dateFormat.format(cal.time); profileStartLoaded = true }
        }
    }

    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            try {
                val json = URL("https://raw.githubusercontent.com/hakanerbasss/baretim-mavi/main/tax_parameters.json?t=${System.currentTimeMillis()}").readText()
                val obj = JSONObject(json)
                minWageGross = obj.getDouble("min_wage_gross")
                lastUpdate = obj.getString("last_update")
            } catch (_: Exception) {}
        }
    }

    var showStartDatePicker by remember { mutableStateOf(false) }
    var showEndDatePicker by remember { mutableStateOf(false) }

    if (showStartDatePicker) {
        WheelDatePickerDialog(title = "İşe Giriş Tarihi", onDismiss = { showStartDatePicker = false }) { sel ->
            startDate = sel; startText = dateFormat.format(sel.time); profileStartLoaded = false
        }
    }
    if (showEndDatePicker) {
        WheelDatePickerDialog(title = "İşten Ayrılma Tarihi", onDismiss = { showEndDatePicker = false }) { sel ->
            endDate = sel; endText = dateFormat.format(sel.time)
        }
    }

    fun calculate() {
        if (salary.isBlank()) { android.widget.Toast.makeText(context, "Lutfen maas giriniz", android.widget.Toast.LENGTH_SHORT).show(); return }
        val gross = salary.toDoubleOrNull() ?: run { android.widget.Toast.makeText(context, "Gecersiz deger", android.widget.Toast.LENGTH_SHORT).show(); return }
        // Prim gün hesapla
        var days = premDays.toIntOrNull() ?: 0
        if (days == 0 && startDate != null && endDate != null) {
            days = ((endDate!!.timeInMillis - startDate!!.timeInMillis + 86400000) / 86400000).toInt()
        }
        if (days == 0) days = 600
        rDays = days

        if (days < 600) { rError = "⚠️ En az 600 gün prim gerekli. Mevcut: $days gün"; showResult = true; scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }; return }
        rError = ""

        val ceiling = minWageGross * 0.80
        val monthlyBenefit = minOf(gross * 0.40, ceiling)
        val durationMonths = when { days >= 1080 -> 10; days >= 900 -> 8; else -> 6 }
        rMonthly = monthlyBenefit; rDuration = durationMonths; rTotal = monthlyBenefit * durationMonths
        showResult = true; scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        androidx.compose.animation.AnimatedVisibility(
            visible = !showResult,
            enter = androidx.compose.animation.expandVertically(),
            exit = androidx.compose.animation.shrinkVertically()
        ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        SectionHeader("İŞSİZLİK MAAŞI", Icons.Default.MoneyOff) { showInfoDialog = true }
        CurrencyField(value = salary, onValueChange = { salary = it; profileSalaryLoaded = false }, label = "Son Brüt Maaş (₺)")
        if (profileSalaryLoaded) ProfileAutoFillNote()
        Text("İşe Giriş Tarihi", fontSize = 14.sp, color = colors.textPrimary)
        DatePickerButton(startText) { showStartDatePicker = true }
        if (profileStartLoaded) ProfileAutoFillNote()
        Text("İşten Çıkış Tarihi", fontSize = 14.sp, color = colors.textPrimary)
        DatePickerButton(endText) { showEndDatePicker = true }
        NumberField(value = premDays, onValueChange = { premDays = it }, label = "veya Prim Günü girin (opsiyonel)")
        ProfileFillButton {
            val p = profileManager.load()
            if (p.isLoggedIn) {
                if (p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileSalaryLoaded = true }
                if (p.startDateMillis > 0L) { val cal = java.util.Calendar.getInstance().apply { timeInMillis = p.startDateMillis }; startDate = cal; startText = dateFormat.format(cal.time); profileStartLoaded = true }
            }
        }
        ActionButtons(onCalculate = { calculate() }, onReset = { salary = ""; premDays = ""; startDate = null; endDate = null; startText = "Tarih Seç"; endText = "Tarih Seç"; showResult = false; profileStartLoaded = false; profileSalaryLoaded = false })
        } // inputs column
        } // AnimatedVisibility
        ResultCard(visible = showResult) {
            if (rError.isNotEmpty()) { Text(rError, fontSize = 14.sp, color = colors.error, fontWeight = FontWeight.Bold) } else {
                Text("SONUÇ", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary); Spacer(Modifier.height(8.dp))
                ResultLine("Prim Günü", "$rDays gün")
                ResultLine("Brüt Maaş", "${formatMoney(salary.toDoubleOrNull() ?: 0.0)}₺")
                HorizontalDivider(Modifier.padding(vertical = 6.dp))
                ResultLine("Hesaplama", "Brüt × %40")
                ResultLine("Aylık Ödenek", "${formatMoney(rMonthly)}₺", colors.success, true)
                ResultLine("Süre", "$rDuration ay", colors.textPrimary, true)
                Text(when { rDays >= 1080 -> "1080+ gün → 10 ay"; rDays >= 900 -> "900-1079 gün → 8 ay"; else -> "600-899 gün → 6 ay" }, fontSize = 11.sp, color = colors.textSecondary)
                HorizontalDivider(Modifier.padding(vertical = 6.dp))
                BigResult("Toplam Ödenek", "${formatMoney(rTotal)}₺")
                Spacer(Modifier.height(4.dp))
                Text("📊 Tavan: ${formatMoney(minWageGross * 0.80)}₺ (asgari ücret %80)", fontSize = 12.sp, color = colors.info)
                Text("✅ GSS devlet karşılar", fontSize = 12.sp, color = colors.success)
                Text("✅ İŞKUR'a 30 gün içinde başvuru", fontSize = 12.sp, color = colors.success)
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
            ShareButton { context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, "💸 İŞSİZLİK MAAŞI\nPrim: $rDays gün\nAylık: ${formatMoney(rMonthly)}₺\nSüre: $rDuration ay\nToplam: ${formatMoney(rTotal)}₺\n📱 Baretim Mavi") }, "Paylaş")) }
        }
    }
    if (showInfoDialog) { AlertDialog(onDismissRequest = { showInfoDialog = false }, title = { Text("İşsizlik Ödeneği") }, text = { Text("📜 4447 Sayılı Kanun\n\nŞartlar:\n• Son 3 yılda en az 600 gün prim\n• İşveren kaynaklı fesih\n• 30 gün içinde İŞKUR başvurusu\n\nSüre:\n• 600-899 gün → 6 ay\n• 900-1079 gün → 8 ay\n• 1080+ gün → 10 ay\n\nTutar: Brüt × %40\nTavan: ${formatMoney(minWageGross * 0.80)}₺ (asgari %80)\nGüncelleme: $lastUpdate", fontSize = 13.sp) }, confirmButton = { TextButton(onClick = { showInfoDialog = false }) { Text("Tamam") } }) }
}
