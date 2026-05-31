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
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun RetirementScreen() {
    val context = LocalContext.current; val colors = LocalAppColors.current
    val scrollState = rememberScrollState(); val scope = rememberCoroutineScope()
    val profileManager = remember { ProfileManager(context) }
    val dateFormat = remember { SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()) }

    var birthDate by remember { mutableStateOf<Calendar?>(null) }; var birthText by remember { mutableStateOf("Tarih Seç") }
    var startDate by remember { mutableStateOf<Calendar?>(null) }; var startText by remember { mutableStateOf("Tarih Seç") }
    var totalPremDays by remember { mutableStateOf("") }; var isFemale by remember { mutableStateOf(false) }
    var showResult by remember { mutableStateOf(false) }; var showInfoDialog by remember { mutableStateOf(false) }
    var profileBirthLoaded by remember { mutableStateOf(false) }; var profileStartLoaded by remember { mutableStateOf(false) }

    // Sonuç
    var rRetireAge by remember { mutableIntStateOf(0) }; var rRetireYear by remember { mutableIntStateOf(0) }
    var rRemainingYears by remember { mutableIntStateOf(0) }; var rRequiredDays by remember { mutableIntStateOf(7200) }
    var rCurrentPrem by remember { mutableIntStateOf(0) }; var rRemainingDays by remember { mutableIntStateOf(0) }
    var rStatus by remember { mutableStateOf("") }
    var rLawPeriod by remember { mutableStateOf("") }
    var rEarlyWarning by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        val p = profileManager.load()
        if (p.isLoggedIn) {
            if (p.birthDateMillis > 0L) { val cal = Calendar.getInstance().apply { timeInMillis = p.birthDateMillis }; birthDate = cal; birthText = dateFormat.format(cal.time); profileBirthLoaded = true }
            // Ilk sigortalilik tarihi varsa onu kullan, yoksa ise giris tarihi fallback
            val insuranceMillis = if (p.firstInsuranceDateMillis > 0L) p.firstInsuranceDateMillis else p.startDateMillis
            if (insuranceMillis > 0L) { val cal = Calendar.getInstance().apply { timeInMillis = insuranceMillis }; startDate = cal; startText = dateFormat.format(cal.time); profileStartLoaded = true }
        }
    }

    var showBirthDatePicker by remember { mutableStateOf(false) }
    var showStartDatePicker by remember { mutableStateOf(false) }

    if (showBirthDatePicker) {
        WheelDatePickerDialog(title = "Doğum Tarihi", onDismiss = { showBirthDatePicker = false }) { sel ->
            birthDate = sel; birthText = dateFormat.format(sel.time)
        }
    }
    if (showStartDatePicker) {
        WheelDatePickerDialog(title = "İlk Sigorta Tarihi", onDismiss = { showStartDatePicker = false }) { sel ->
            startDate = sel; startText = dateFormat.format(sel.time)
        }
    }


    fun calculate() {
        val bd = birthDate ?: run { android.widget.Toast.makeText(context, "Lutfen dogum tarihi seciniz", android.widget.Toast.LENGTH_SHORT).show(); return }
        val sd = startDate ?: run { android.widget.Toast.makeText(context, "Lutfen ilk sigorta tarihi seciniz", android.widget.Toast.LENGTH_SHORT).show(); return }
        val birthYear = bd.get(Calendar.YEAR); val startYear = sd.get(Calendar.YEAR); val currentYear = 2026
        val currentPrem = totalPremDays.toIntOrNull() ?: run {
            // Tarihlerden otomatik hesapla
            val now = Calendar.getInstance()
            ((now.timeInMillis - sd.timeInMillis + 86400000) / 86400000).toInt()
        }

        // 3 donem: <1999 / 1999-2007 / 2008+
        val retireAge: Int
        val requiredDays: Int
        val lawPeriod: String
        val earlyWarning: String

        when {
            startYear < 1999 -> {
                retireAge = if (isFemale) 50 else 55
                requiredDays = 5000
                lawPeriod = "506 Sayili Kanun (1999 oncesi)"
                earlyWarning = "⚠️ 1999 oncesi sigorta girisi icin yas ve prim gun sayisi bireye gore degisir. Bu hesap yaklasiktir — kesin sonuc icin SGK'ya basvurun."
            }
            startYear < 2008 -> {
                retireAge = if (isFemale) 58 else 60
                requiredDays = 7200
                lawPeriod = "4447 Sayili Kanun (1999-2007)"
                earlyWarning = ""
            }
            else -> {
                retireAge = if (isFemale) 58 else 60
                requiredDays = 7200
                lawPeriod = "5510 Sayili Kanun (2008+)"
                earlyWarning = ""
            }
        }

        val retireYear = birthYear + retireAge
        val remainingYears = maxOf(0, retireYear - currentYear); val remainingDays = maxOf(0, requiredDays - currentPrem)

        rRetireAge = retireAge; rRetireYear = retireYear; rRemainingYears = remainingYears
        rRequiredDays = requiredDays; rCurrentPrem = currentPrem; rRemainingDays = remainingDays
        rLawPeriod = lawPeriod; rEarlyWarning = earlyWarning
        rStatus = when {
            remainingYears <= 0 && remainingDays <= 0 -> "🎉 TEBRİKLER! Emekliliğe hak kazandınız!"
            remainingYears <= 0 -> "⏳ Yaş tamam, prim gününüz tamamlanınca emekli olabilirsiniz."
            remainingDays <= 0 -> "⏳ Prim gününüz tamam, yaş şartını bekliyorsunuz."
            else -> "⏳ Hem yaş hem prim gün şartı devam ediyor."
        }
        showResult = true; scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        androidx.compose.animation.AnimatedVisibility(
            visible = !showResult,
            enter = androidx.compose.animation.expandVertically(),
            exit = androidx.compose.animation.shrinkVertically()
        ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        SectionHeader("EMEKLİLİK HESAPLAMA", Icons.Default.Elderly) { showInfoDialog = true }
        Text("Doğum Tarihi", fontSize = 14.sp, color = colors.textPrimary)
        DatePickerButton(birthText) { showBirthDatePicker = true }
        if (profileBirthLoaded) ProfileAutoFillNote()
        Text("İlk Sigorta Tarihi", fontSize = 14.sp, color = colors.textPrimary)
        DatePickerButton(startText) { showStartDatePicker = true }
        if (profileStartLoaded) ProfileAutoFillNote()
        NumberField(value = totalPremDays, onValueChange = { totalPremDays = it }, label = "Toplam Prim Günü (boş = otomatik)")
        Row { Checkbox(checked = isFemale, onCheckedChange = { isFemale = it }); Spacer(Modifier.width(4.dp)); Text("Kadın", color = colors.textPrimary) }
        ProfileFillButton {
            val p = profileManager.load()
            if (p.isLoggedIn) {
                if (p.birthDateMillis > 0L) { val cal = Calendar.getInstance().apply { timeInMillis = p.birthDateMillis }; birthDate = cal; birthText = dateFormat.format(cal.time); profileBirthLoaded = true }
                val insuranceMillis = if (p.firstInsuranceDateMillis > 0L) p.firstInsuranceDateMillis else p.startDateMillis
                if (insuranceMillis > 0L) { val cal = Calendar.getInstance().apply { timeInMillis = insuranceMillis }; startDate = cal; startText = dateFormat.format(cal.time); profileStartLoaded = true }
            }
        }
        ActionButtons(onCalculate = { calculate() }, onReset = { birthDate = null; startDate = null; birthText = "Tarih Seç"; startText = "Tarih Seç"; totalPremDays = ""; isFemale = false; showResult = false; profileBirthLoaded = false; profileStartLoaded = false })
        } // inputs column
        } // AnimatedVisibility
        ResultCard(visible = showResult) {
            Text("SONUÇ", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary); Spacer(Modifier.height(8.dp))
            Text(rLawPeriod, fontSize = 11.sp, color = colors.info)
            Spacer(Modifier.height(4.dp))
            ResultLine("Emeklilik Yasi", "$rRetireAge")
            ResultLine("Emeklilik Yili", "$rRetireYear", colors.textPrimary, true)
            if (rEarlyWarning.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Text(rEarlyWarning, fontSize = 12.sp, color = colors.warning, lineHeight = 17.sp)
            }
            ResultLine("Kalan Süre", "$rRemainingYears yıl", if (rRemainingYears > 0) colors.warning else colors.success, true)
            HorizontalDivider(Modifier.padding(vertical = 6.dp))
            ResultLine("Gerekli Prim", "${formatNumber(rRequiredDays.toDouble())} gün")
            ResultLine("Mevcut Prim", "${formatNumber(rCurrentPrem.toDouble())} gün", colors.success)
            ResultLine("Kalan Prim", "${formatNumber(rRemainingDays.toDouble())} gün (~${rRemainingDays/30} ay)", if (rRemainingDays > 0) colors.warning else colors.success, true)
            Spacer(Modifier.height(8.dp))
            Text(rStatus, fontSize = 14.sp, fontWeight = FontWeight.Bold, color = if (rRemainingYears <= 0 && rRemainingDays <= 0) colors.success else colors.info)
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
            ShareButton { context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, "👴 EMEKLİLİK\nYaş: $rRetireAge ($rRetireYear)\nKalan: $rRemainingYears yıl\nPrim: ${rCurrentPrem}/${rRequiredDays} gün\n$rStatus\n📱 Baretim Mavi") }, "Paylaş")) }
        }
    }
    if (showInfoDialog) { AlertDialog(onDismissRequest = { showInfoDialog = false }, title = { Text("Emeklilik Şartları") }, text = { Text("Hangi kanun uygulanir?\n\n📅 1999 oncesi sigorta:\n506 Sayili Kanun — yas ve prim gun sayisi bireye gore degisir, SGK dokümanizla karsilastirin.\n\n📅 1999-2007 arasi sigorta:\n4447 Sayili Kanun\n• Erkek: 60 yas + 7200 gun\n• Kadin: 58 yas + 7200 gun\n\n📅 2008 ve sonrasi sigorta:\n5510 Sayili Kanun\n• Erkek: 60 yas + 7200 gun\n• Kadin: 58 yas + 7200 gun\n\n⚠️ Kesin sonuc icin SGK dokuminuze bakin.", fontSize = 13.sp) }, confirmButton = { TextButton(onClick = { showInfoDialog = false }) { Text("Tamam") } }) }
}
