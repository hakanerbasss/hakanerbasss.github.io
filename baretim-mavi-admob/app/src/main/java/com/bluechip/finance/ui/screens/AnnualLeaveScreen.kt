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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.ui.components.*
import com.bluechip.finance.ui.theme.*
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun AnnualLeaveScreen() {
    val context = LocalContext.current; val colors = LocalAppColors.current
    val scrollState = rememberScrollState(); val scope = rememberCoroutineScope()
    val profileManager = remember { ProfileManager(context) }
    val dateFormat = remember { SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()) }
    var startDate by remember { mutableStateOf<Calendar?>(null) }; var calcDate by remember { mutableStateOf(Calendar.getInstance()) }
    var startText by remember { mutableStateOf("Tarih Seç") }; var calcText by remember { mutableStateOf(dateFormat.format(Calendar.getInstance().time)) }
    var underground by remember { mutableStateOf(false) }
    var showResult by remember { mutableStateOf(false) }; var showInfoDialog by remember { mutableStateOf(false) }
    var resultDuration by remember { mutableStateOf("") }; var resultLeave by remember { mutableStateOf("") }; var resultInfo by remember { mutableStateOf("") }
    var profileStartLoaded by remember { mutableStateOf(false) }

    // Profil yükle
    LaunchedEffect(Unit) {
        val p = profileManager.load()
        if (p.isLoggedIn) {
            if (p.startDateMillis > 0L) { val cal = Calendar.getInstance().apply { timeInMillis = p.startDateMillis }; startDate = cal; startText = dateFormat.format(cal.time); profileStartLoaded = true }
            underground = p.isUnderground
        }
    }

    var showStartDatePicker by remember { mutableStateOf(false) }
    var showCalcDatePicker by remember { mutableStateOf(false) }

    if (showStartDatePicker) {
        WheelDatePickerDialog(title = "İşe Başlama Tarihi", onDismiss = { showStartDatePicker = false }) { sel ->
            startDate = sel; startText = dateFormat.format(sel.time)
        }
    }
    if (showCalcDatePicker) {
        WheelDatePickerDialog(title = "Hesaplama Tarihi", onDismiss = { showCalcDatePicker = false }) { sel ->
            calcDate = sel; calcText = dateFormat.format(sel.time)
        }
    }


    fun calculate() {
        val sd = startDate ?: run { android.widget.Toast.makeText(context, "Lutfen ise baslama tarihi seciniz", android.widget.Toast.LENGTH_SHORT).show(); return }
        val totalDays = ((calcDate.timeInMillis - sd.timeInMillis + 86400000) / 86400000).toInt()
        val years = totalDays / 365; val months = (totalDays % 365) / 30; val days = (totalDays % 365) % 30
        resultDuration = "$years yıl $months ay $days gün"
        // Doğum tarihinden yaş hesapla
        val p = profileManager.load(); var ageVal: Int? = null
        if (p.birthDateMillis > 0L) { val birthCal = Calendar.getInstance().apply { timeInMillis = p.birthDateMillis }; ageVal = calcDate.get(Calendar.YEAR) - birthCal.get(Calendar.YEAR) }
        var leave = when { ageVal != null && ageVal < 18 -> 20; ageVal != null && ageVal >= 50 -> 20; years < 5 -> 14; years < 15 -> 20; else -> 26 }
        if (underground) leave += 4; resultLeave = "$leave gün"
        resultInfo = buildString { when { ageVal != null && ageVal < 18 -> append("ℹ️ 18 yaş altı: 20 gün\n"); ageVal != null && ageVal >= 50 -> append("ℹ️ 50+ yaş: 20 gün\n")
            years < 5 -> append("ℹ️ 0-5 yıl: 14 gün\n"); years < 15 -> append("ℹ️ 5-15 yıl: 20 gün\n"); else -> append("ℹ️ 15+ yıl: 26 gün\n") }; if (underground) append("ℹ️ Yer altı: +4 gün") }
        showResult = true; scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        androidx.compose.animation.AnimatedVisibility(
            visible = !showResult,
            enter = androidx.compose.animation.expandVertically(),
            exit = androidx.compose.animation.shrinkVertically()
        ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        SectionHeader("YILLIK İZİN HESAPLAMA", Icons.Default.DateRange) { showInfoDialog = true }
        Text("İşe Başlama Tarihi", fontSize = 14.sp, color = colors.textPrimary)
        DatePickerButton(startText) { showStartDatePicker = true }
        if (profileStartLoaded) ProfileAutoFillNote()
        Text("Hesaplama Tarihi", fontSize = 14.sp, color = colors.textPrimary); DatePickerButton(calcText) { showCalcDatePicker = true }
        Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = underground, onCheckedChange = { underground = it }); Spacer(Modifier.width(4.dp)); Text("Yer altı işçisiyim (+4 gün)", color = colors.textPrimary) }
        ProfileFillButton {
            val p = profileManager.load()
            if (p.isLoggedIn) {
                if (p.startDateMillis > 0L) { val cal = Calendar.getInstance().apply { timeInMillis = p.startDateMillis }; startDate = cal; startText = dateFormat.format(cal.time); profileStartLoaded = true }
                underground = p.isUnderground
            }
        }
        ActionButtons(onCalculate = { calculate() }, onReset = { startDate = null; calcDate = Calendar.getInstance(); startText = "Tarih Seç"; calcText = dateFormat.format(Calendar.getInstance().time); underground = false; showResult = false; profileStartLoaded = false })
        } // inputs column
        } // AnimatedVisibility
        ResultCard(visible = showResult) {
            Text("SONUÇ", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary); Spacer(Modifier.height(8.dp))
            ResultLine("Çalışma Süresi", resultDuration, colors.textPrimary, true); Spacer(Modifier.height(8.dp))
            BigResult("Yıllık İzin Hakkı", resultLeave, MaterialTheme.colorScheme.primary)
            if (resultInfo.isNotEmpty()) Text(resultInfo, fontSize = 12.sp, color = colors.textSecondary)
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
            ShareButton { context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, "📅 YILLIK İZİN\nSüre: $resultDuration\nİzin: $resultLeave\n$resultInfo\n📱 Baretim Mavi") }, "Paylaş")) }
        }
    }
    if (showInfoDialog) { AlertDialog(onDismissRequest = { showInfoDialog = false }, title = { Text("İzin Rehberi") }, text = { Text("📜 4857 İş Kanunu Mad. 53\n\n• 0-5 yıl: 14 gün\n• 5-15 yıl: 20 gün\n• 15+ yıl: 26 gün\n• 18 yaş altı / 50+ yaş: 20 gün\n• Yer altı: +4 gün\n\n💡 Profilinizde doğum tarihi varsa yaş otomatik hesaplanır.", fontSize = 13.sp) }, confirmButton = { TextButton(onClick = { showInfoDialog = false }) { Text("Tamam") } }) }
}
