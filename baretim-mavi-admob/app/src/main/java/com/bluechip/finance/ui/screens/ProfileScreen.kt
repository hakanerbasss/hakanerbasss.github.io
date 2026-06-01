package com.bluechip.finance.ui.screens

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.bluechip.finance.data.BackupManager
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.data.UserProfile
import com.bluechip.finance.ui.components.*
import com.bluechip.finance.ui.theme.*
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun ProfileScreen(onNavigate: (String) -> Unit = {}, autoAddIncome: Boolean = false) {
    val context = LocalContext.current
    val colors = LocalAppColors.current
    val profileManager = remember { ProfileManager(context) }
    val dateFormat = remember { SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()) }

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        uri ?: return@rememberLauncherForActivityResult
        try {
            context.contentResolver.openOutputStream(uri)?.use { BackupManager.export(context, it) }
            Toast.makeText(context, "Yedek kaydedildi", Toast.LENGTH_SHORT).show()
        } catch (_: Exception) {
            Toast.makeText(context, "Yedek hatası", Toast.LENGTH_SHORT).show()
        }
    }
    val importLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        uri ?: return@rememberLauncherForActivityResult
        try {
            val ok = context.contentResolver.openInputStream(uri)?.use { BackupManager.import(context, it) } ?: false
            Toast.makeText(context, if (ok) "Veriler geri yüklendi, uygulamayı yeniden başlatın" else "Geri yükleme hatası", Toast.LENGTH_LONG).show()
        } catch (_: Exception) {
            Toast.makeText(context, "Geri yükleme hatası", Toast.LENGTH_SHORT).show()
        }
    }

    var name by remember { mutableStateOf("") }
    var salary by remember { mutableStateOf("") }
    var netSalary by remember { mutableStateOf("") }
    var salaryDay by remember { mutableStateOf("") }
    var startDateMillis by remember { mutableLongStateOf(0L) }
    var startText by remember { mutableStateOf("Tarih Seç") }
    var birthDateMillis by remember { mutableLongStateOf(0L) }
    var birthText by remember { mutableStateOf("Tarih Seç") }
    var underground by remember { mutableStateOf(false) }
    var advanceDay by remember { mutableStateOf("") }
    var advanceAmount by remember { mutableStateOf("") }
    var isSaved by remember { mutableStateOf(false) }
    var infoExpanded by remember { mutableStateOf(false) }
    var isRetired by remember { mutableStateOf(false) }
    var retirementSalary by remember { mutableStateOf("") }
    var retirementDay by remember { mutableStateOf("") }
    var sideIncomes by remember { mutableStateOf<List<com.bluechip.finance.data.SideIncome>>(emptyList()) }
    var showAddSideIncome by remember { mutableStateOf(autoAddIncome) }
    var editSideIncome by remember { mutableStateOf<com.bluechip.finance.data.SideIncome?>(null) }
    var showEditRecord by remember { mutableStateOf(false) }
    var editingRecord by remember { mutableStateOf<com.bluechip.finance.data.SideIncomeRecord?>(null) }
    var editingRecordSideId by remember { mutableStateOf("") }

    // DatePicker state
    var showBirthPicker by remember { mutableStateOf(false) }
    var showStartPicker by remember { mutableStateOf(false) }
    var showInsurancePicker by remember { mutableStateOf(false) }
    var firstInsuranceDateMillis by remember { mutableLongStateOf(0L) }
    var firstInsuranceText by remember { mutableStateOf("Tarih Sec") }

    // Profil ekranindan cikinca tax flag temizle
    DisposableEffect(Unit) {
        onDispose {
            context.getSharedPreferences("app_prefs", android.content.Context.MODE_PRIVATE)
                .edit().remove("tax_open_net_mode").remove("net_salary_for_tax").apply()
        }
    }

    LaunchedEffect(Unit) {
        val p = profileManager.load()
        if (p.isLoggedIn) {
            name = p.name
            salary = if (p.grossSalary > 0) p.grossSalary.toInt().toString() else ""
            netSalary = if (p.netSalary > 0) p.netSalary.toInt().toString() else ""
            salaryDay = if (p.salaryDay > 0) p.salaryDay.toString() else ""
            advanceDay = if (p.advanceDay > 0) p.advanceDay.toString() else ""
            advanceAmount = if (p.advanceAmount > 0) p.advanceAmount.toInt().toString() else ""
            underground = p.isUnderground
            startDateMillis = p.startDateMillis
            birthDateMillis = p.birthDateMillis
            if (p.startDateMillis > 0) startText = dateFormat.format(Date(p.startDateMillis))
            firstInsuranceDateMillis = p.firstInsuranceDateMillis
            if (p.firstInsuranceDateMillis > 0) firstInsuranceText = dateFormat.format(Date(p.firstInsuranceDateMillis))
            if (p.birthDateMillis > 0) birthText = dateFormat.format(Date(p.birthDateMillis))
            isRetired = p.isRetired
            retirementSalary = if (p.retirementSalary > 0) p.retirementSalary.toInt().toString() else ""
            retirementDay = if (p.retirementDay > 0) p.retirementDay.toString() else ""
            sideIncomes = p.sideIncomes
            isSaved = true
        }
    }

    // Doğum tarihi picker dialog
    if (showBirthPicker) {
        WheelDatePickerDialog(title = "Doğum Tarihi", onDismiss = { showBirthPicker = false }) { sel ->
            birthDateMillis = sel.timeInMillis
            birthText = dateFormat.format(sel.time)
        }
    }

    // İşe başlama tarihi picker dialog
    if (showStartPicker) {
        WheelDatePickerDialog(title = "Ise Baslama Tarihi", onDismiss = { showStartPicker = false }) { sel ->
            startDateMillis = sel.timeInMillis
            startText = dateFormat.format(sel.time)
        }
    }

    // Ilk sigortalilik tarihi picker dialog
    if (showInsurancePicker) {
        WheelDatePickerDialog(title = "Ilk Sigortalilik Tarihi", onDismiss = { showInsurancePicker = false }) { sel ->
            firstInsuranceDateMillis = sel.timeInMillis
            firstInsuranceText = dateFormat.format(sel.time)
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        // ── Profil başlık kartı ────────────────────────────────────────────
        Card(
            shape = RoundedCornerShape(20.dp),
            elevation = CardDefaults.cardElevation(2.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(20.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    modifier = Modifier.size(60.dp).background(
                        Brush.radialGradient(listOf(PurplePrimaryLight, PurplePrimary)), CircleShape
                    ),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Default.Person, null, tint = Color.White, modifier = Modifier.size(32.dp))
                }
                Spacer(Modifier.width(16.dp))
                Column {
                    Text(
                        if (isSaved && name.isNotBlank()) name else "Profilim",
                        fontWeight = FontWeight.Bold, fontSize = 18.sp, color = colors.textPrimary
                    )
                    Text(
                        if (isSaved) "Profil kayıtlı ✓" else "Bilgilerini kaydet",
                        fontSize = 13.sp,
                        color = if (isSaved) colors.success else colors.textSecondary
                    )
                }
            }
        }

        // ── Maaş kartı ────────────────────────────────────────────────────
        Card(
            shape = RoundedCornerShape(20.dp),
            elevation = CardDefaults.cardElevation(2.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg)
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier.size(36.dp).background(PurplePrimary.copy(0.12f), RoundedCornerShape(10.dp)),
                        contentAlignment = Alignment.Center
                    ) { Icon(Icons.Default.AccountBalanceWallet, null, tint = PurplePrimary, modifier = Modifier.size(20.dp)) }
                    Spacer(Modifier.width(10.dp))
                    Text("Maaş Bilgisi", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary)
                }
                OutlinedTextField(
                    value = name, onValueChange = { name = it },
                    label = { Text("Adınız") },
                    leadingIcon = { Icon(Icons.Default.Person, null, tint = PurplePrimary) },
                    modifier = Modifier.fillMaxWidth(), singleLine = true,
                    shape = RoundedCornerShape(16.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = PurplePrimary,
                        unfocusedBorderColor = PurplePrimary.copy(alpha = 0.2f),
                        focusedContainerColor = colors.cardBg,
                        unfocusedContainerColor = colors.cardBg,
                        focusedTextColor = colors.textPrimary,
                        unfocusedTextColor = colors.textPrimary
                    )
                )
                CurrencyField(value = salary, onValueChange = { salary = it }, label = "Brut Maas (TL)")
                Text("Not: Brut maas bilinmiyorsa Araclar > Vergi sayfasindan hesaplanabilir.",
                    fontSize = 11.sp, color = colors.textSecondary,
                    modifier = androidx.compose.ui.Modifier.padding(start = 4.dp))
                CurrencyField(value = netSalary, onValueChange = { netSalary = it }, label = "Net Maaş (₺)")
                NumberField(value = salaryDay, onValueChange = { v -> if (v.isEmpty() || (v.toIntOrNull() ?: 0) in 1..31) salaryDay = v }, label = "Maaş Günü (1-31)")
                HorizontalDivider(
                    modifier = androidx.compose.ui.Modifier.padding(vertical = 4.dp),
                    color = com.bluechip.finance.ui.theme.PurplePrimary.copy(alpha = 0.1f)
                )
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Box(
                        modifier = androidx.compose.ui.Modifier.size(36.dp)
                            .background(androidx.compose.ui.graphics.Color(0xFF00897B).copy(0.12f), RoundedCornerShape(10.dp)),
                        contentAlignment = androidx.compose.ui.Alignment.Center
                    ) {
                        Text("💸", fontSize = 18.sp)
                    }
                    Spacer(androidx.compose.ui.Modifier.width(10.dp))
                    Text("Avans Bilgisi", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary)
                }
                NumberField(
                    value = advanceDay,
                    onValueChange = { v -> if (v.isEmpty() || (v.toIntOrNull() ?: 0) in 1..31) advanceDay = v },
                    label = "Avans Günü (1-31, 0=yok)"
                )
                CurrencyField(value = advanceAmount, onValueChange = { advanceAmount = it }, label = "Avans Tutarı (₺)")
            }
        }

        // ── Tarih bilgileri kartı ──────────────────────────────────────────
        Card(
            shape = RoundedCornerShape(20.dp),
            elevation = CardDefaults.cardElevation(2.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg)
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier.size(36.dp).background(Color(0xFF6A1B9A).copy(0.12f), RoundedCornerShape(10.dp)),
                        contentAlignment = Alignment.Center
                    ) { Icon(Icons.Default.DateRange, null, tint = Color(0xFF6A1B9A), modifier = Modifier.size(20.dp)) }
                    Spacer(Modifier.width(10.dp))
                    Text("Tarih Bilgileri", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary)
                }
                Text("Doğum Tarihi", fontSize = 13.sp, color = colors.textSecondary)
                DatePickerButton(birthText) { showBirthPicker = true }
                Text("Ise Baslama Tarihi", fontSize = 13.sp, color = colors.textSecondary)
                DatePickerButton(startText) { showStartPicker = true }
                Text("Ilk Sigortalilik Tarihi", fontSize = 13.sp, color = colors.textSecondary)
                Text("(Bos birakilirsa ise giris tarihi kullanilir)", fontSize = 11.sp, color = colors.textSecondary)
                DatePickerButton(firstInsuranceText) { showInsurancePicker = true }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = underground, onCheckedChange = { underground = it },
                        colors = CheckboxDefaults.colors(checkedColor = PurplePrimary)
                    )
                    Spacer(Modifier.width(4.dp))
                    Text("Yer altı işçisiyim", color = colors.textPrimary)
                }
            }
        }



        // Emeklilik karti
        Card(shape = RoundedCornerShape(20.dp), elevation = CardDefaults.cardElevation(2.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg)) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(modifier = Modifier.size(36.dp).background(Color(0xFF2E7D32).copy(0.12f), RoundedCornerShape(10.dp)),
                        contentAlignment = Alignment.Center) { Text("🏦", fontSize = 18.sp) }
                    Spacer(Modifier.width(10.dp))
                    Text("Emeklilik", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                    Switch(checked = isRetired, onCheckedChange = { isRetired = it },
                        colors = SwitchDefaults.colors(checkedThumbColor = Color.White, checkedTrackColor = PurplePrimary))
                }
                if (isRetired) {
                    CurrencyField(value = retirementSalary, onValueChange = { retirementSalary = it }, label = "Emekli Maasi (TL)")
                    NumberField(value = retirementDay,
                        onValueChange = { v -> if (v.isEmpty() || (v.toIntOrNull() ?: 0) in 1..31) retirementDay = v },
                        label = "Emekli Maasi Yatma Gunu (1-31)")
                }
            }
        }

        // Yan gelirler karti
        Card(shape = RoundedCornerShape(20.dp), elevation = CardDefaults.cardElevation(2.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg)) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(modifier = Modifier.size(36.dp).background(Color(0xFF1565C0).copy(0.12f), RoundedCornerShape(10.dp)),
                        contentAlignment = Alignment.Center) { Text("💼", fontSize = 18.sp) }
                    Spacer(Modifier.width(10.dp))
                    Text("Yan Gelirler", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                    IconButton(onClick = { editSideIncome = null; showAddSideIncome = true }) {
                        Icon(Icons.Default.Add, null, tint = PurplePrimary)
                    }
                }
                if (sideIncomes.isEmpty()) {
                    Text("Henuz yan gelir eklenmedi", fontSize = 12.sp, color = colors.textSecondary)
                } else {
                    sideIncomes.forEach { side ->
                        Column {
                            Row(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                Text(side.category.emoji, fontSize = 18.sp)
                                Spacer(Modifier.width(8.dp))
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(side.label.ifBlank { side.category.label }, fontSize = 13.sp, color = colors.textPrimary)
                                    val dispAmt = side.currentMonthAmount()
                                    Text(
                                        if (side.isVariable) "Bu ay: ${com.bluechip.finance.ui.components.formatMoney(dispAmt)} TL  (ort: ${com.bluechip.finance.ui.components.formatMoney(side.effectiveAmount())} TL)"
                                        else "${com.bluechip.finance.ui.components.formatMoney(side.amount)} TL",
                                        fontSize = 11.sp, color = colors.textSecondary
                                    )
                                }
                                IconButton(onClick = { editSideIncome = side; showAddSideIncome = true }, modifier = Modifier.size(32.dp)) {
                                    Icon(Icons.Default.Edit, null, tint = colors.info, modifier = Modifier.size(16.dp))
                                }
                                IconButton(onClick = { sideIncomes = sideIncomes.filter { it.id != side.id } }, modifier = Modifier.size(32.dp)) {
                                    Icon(Icons.Default.Delete, null, tint = colors.error, modifier = Modifier.size(16.dp))
                                }
                            }
                            if (side.isVariable && side.records.isNotEmpty()) {
                                val fmt = java.text.SimpleDateFormat("MM/yy", java.util.Locale.getDefault())
                                Column(modifier = Modifier.padding(start = 26.dp, bottom = 4.dp)) {
                                    Text("Gecmis:", fontSize = 10.sp, color = colors.textSecondary)
                                    side.records.takeLast(6).reversed().forEach { rec ->
                                        Row(modifier = Modifier.fillMaxWidth(),
                                            verticalAlignment = Alignment.CenterVertically) {
                                            Text(fmt.format(java.util.Date(rec.dateMillis)), fontSize = 10.sp,
                                                color = colors.textSecondary, modifier = Modifier.width(36.dp))
                                            Text("${com.bluechip.finance.ui.components.formatMoney(rec.amount)} TL",
                                                fontSize = 11.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                                            IconButton(onClick = {
                                                editingRecord = rec
                                                editingRecordSideId = side.id
                                                showEditRecord = true
                                            }, modifier = Modifier.size(24.dp)) {
                                                Icon(Icons.Default.Edit, null, tint = colors.info, modifier = Modifier.size(12.dp))
                                            }
                                            IconButton(onClick = {
                                                sideIncomes = sideIncomes.map { s ->
                                                    if (s.id == side.id) s.copy(records = s.records.filter { it.id != rec.id }) else s
                                                }
                                            }, modifier = Modifier.size(24.dp)) {
                                                Icon(Icons.Default.Close, null, tint = colors.error, modifier = Modifier.size(12.dp))
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        HorizontalDivider(color = PurplePrimary.copy(alpha = 0.08f))
                    }
                    Spacer(Modifier.height(4.dp))
                    val sideTotal = sideIncomes.sumOf { it.effectiveAmount() }
                    Row(modifier = Modifier.fillMaxWidth()) {
                        Text("Toplam yan gelir:", fontSize = 12.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
                        Text("${formatMoney(sideTotal)} TL", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = PurplePrimary)
                    }
                }
            }
        }

        if (showAddSideIncome) {
            SideIncomeDialog(
                existing = editSideIncome,
                onDismiss = { showAddSideIncome = false; editSideIncome = null },
                onSave = { newSide ->
                    sideIncomes = if (editSideIncome != null)
                        sideIncomes.map { if (it.id == newSide.id) newSide else it }
                    else sideIncomes + newSide
                    showAddSideIncome = false; editSideIncome = null
                }
            )
        }

        // Gecmis kayit duzenleme dialog
        if (showEditRecord && editingRecord != null) {
            var editAmt by remember { mutableStateOf(editingRecord!!.amount.toInt().toString()) }
            androidx.compose.ui.window.Dialog(onDismissRequest = { showEditRecord = false }) {
                Card(shape = androidx.compose.foundation.shape.RoundedCornerShape(20.dp),
                    colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                    elevation = CardDefaults.cardElevation(8.dp)) {
                    Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("Gecmis Kaydi Duzenle", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)
                        val fmt2 = java.text.SimpleDateFormat("MM/yyyy", java.util.Locale.getDefault())
                        Text(fmt2.format(java.util.Date(editingRecord!!.dateMillis)), fontSize = 13.sp, color = colors.textSecondary)
                        CurrencyField(value = editAmt, onValueChange = { editAmt = it }, label = "Tutar (TL)")
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            OutlinedButton(onClick = { showEditRecord = false }, modifier = Modifier.weight(1f),
                                shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)) { Text("Iptal") }
                            Button(
                                onClick = {
                                    val newAmt = editAmt.toDoubleOrNull() ?: editingRecord!!.amount
                                    sideIncomes = sideIncomes.map { s ->
                                        if (s.id == editingRecordSideId)
                                            s.copy(records = s.records.map { r ->
                                                if (r.id == editingRecord!!.id) r.copy(amount = newAmt) else r
                                            })
                                        else s
                                    }
                                    showEditRecord = false
                                },
                                modifier = Modifier.weight(1f),
                                shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = PurplePrimary)
                            ) { Text("Kaydet", fontWeight = FontWeight.Bold) }
                        }
                    }
                }
            }
        }
        // Kaydet / Guncelle butonu
        val netVal = netSalary.toDoubleOrNull() ?: 0.0
        // Brut maas: kullanicinin girdigi deger varsa onu kullan, yoksa net / 0.71 yaklasimi
        val enteredGross = salary.toDoubleOrNull() ?: 0.0
        val grossForSave = if (enteredGross > 0) enteredGross else if (netVal > 0) netVal / 0.71 else 0.0
        Button(
            onClick = {
                profileManager.save(com.bluechip.finance.data.UserProfile(
                    name = name,
                    grossSalary = grossForSave,
                    netSalary = netVal,
                    salaryDay = salaryDay.toIntOrNull() ?: 0,
                    advanceDay = advanceDay.toIntOrNull() ?: 0,
                    advanceAmount = advanceAmount.toDoubleOrNull() ?: 0.0,
                    startDateMillis = startDateMillis,
                    birthDateMillis = birthDateMillis,
                    firstInsuranceDateMillis = firstInsuranceDateMillis,
                    isUnderground = underground,
                    isRetired = isRetired,
                    retirementSalary = retirementSalary.toDoubleOrNull() ?: 0.0,
                    retirementDay = retirementDay.toIntOrNull() ?: 0,
                    sideIncomes = sideIncomes,
                    isLoggedIn = true
                ))
                isSaved = true
                android.widget.Toast.makeText(context,
                    "Profil ${if (isSaved) "guncellendi" else "kaydedildi"}!",
                    android.widget.Toast.LENGTH_SHORT).show()
            },
            modifier = androidx.compose.ui.Modifier.fillMaxWidth().height(54.dp),
            shape = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(containerColor = com.bluechip.finance.ui.theme.PurplePrimary),
            enabled = name.isNotBlank() && netSalary.isNotBlank()
        ) {
            androidx.compose.material3.Icon(
                if (isSaved) androidx.compose.material.icons.Icons.Default.Update
                else androidx.compose.material.icons.Icons.Default.Save,
                null,
                modifier = androidx.compose.ui.Modifier.size(20.dp),
                tint = androidx.compose.ui.graphics.Color.White
            )
            androidx.compose.foundation.layout.Spacer(androidx.compose.ui.Modifier.width(8.dp))
            Text(
                if (isSaved) "GUNCELLE" else "KAYDET",
                fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
                color = androidx.compose.ui.graphics.Color.White,
                fontSize = 15.sp
            )
        }

        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(
                onClick = {
                    val ts = SimpleDateFormat("yyyyMMdd_HHmm", Locale.getDefault()).format(Date())
                    exportLauncher.launch("baretim_yedek_$ts.json")
                },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(12.dp)
            ) {
                Icon(Icons.Default.Upload, null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Yedekle", fontSize = 13.sp)
            }
            OutlinedButton(
                onClick = { importLauncher.launch(arrayOf("application/json", "*/*")) },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(12.dp)
            ) {
                Icon(Icons.Default.Download, null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Geri Yükle", fontSize = 13.sp)
            }
        }

        // ── Otomatik Doldurma - Açılır/Kapanır ───────────────────────────
        Card(
            shape = RoundedCornerShape(20.dp),
            elevation = CardDefaults.cardElevation(2.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg)
        ) {
            Column {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { infoExpanded = !infoExpanded }
                        .padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier.size(36.dp).background(Color(0xFF1565C0).copy(0.12f), RoundedCornerShape(10.dp)),
                        contentAlignment = Alignment.Center
                    ) { Icon(Icons.Default.Lightbulb, null, tint = Color(0xFF1565C0), modifier = Modifier.size(20.dp)) }
                    Spacer(Modifier.width(10.dp))
                    Text("💡 Otomatik Doldurma", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                    Icon(
                        if (infoExpanded) Icons.Default.KeyboardArrowUp else Icons.Default.KeyboardArrowDown,
                        null, tint = colors.textSecondary
                    )
                }
                AnimatedVisibility(visible = infoExpanded, enter = expandVertically(), exit = shrinkVertically()) {
                    Column(modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 16.dp)) {
                        HorizontalDivider(color = PurplePrimary.copy(alpha = 0.1f))
                        Spacer(Modifier.height(12.dp))
                        listOf(
                            Pair(Icons.Default.Receipt, "Vergi & Bordro → Brüt Maaş"),
                            Pair(Icons.Default.AccountBalance, "Tazminat → Maaş + İşe Giriş"),
                            Pair(Icons.Default.DateRange, "İzin → İşe Başlama + Yer altı"),
                            Pair(Icons.Default.MoneyOff, "İşsizlik → Maaş + İşe Giriş"),
                            Pair(Icons.Default.Elderly, "Emeklilik → Doğum + İlk Sigorta"),
                            Pair(Icons.Default.CompareArrows, "Karşılaştırma → Mevcut Maaş"),
                        ).forEach { (icon, text) ->
                            Row(modifier = Modifier.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                                Icon(icon, null, tint = PurplePrimary, modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(8.dp))
                                Text(text, fontSize = 12.sp, color = colors.textSecondary)
                            }
                        }
                        Spacer(Modifier.height(8.dp))
                        Text("Tüm veriler yalnızca telefonunuzda saklanır.", fontSize = 11.sp, color = colors.textSecondary)
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))
        Spacer(Modifier.height(80.dp))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SideIncomeDialog(
    existing: com.bluechip.finance.data.SideIncome?,
    onDismiss: () -> Unit,
    onSave: (com.bluechip.finance.data.SideIncome) -> Unit
) {
    val colors = LocalAppColors.current
    var label      by remember { mutableStateOf(existing?.label ?: "") }
    var amount     by remember { mutableStateOf(if ((existing?.amount ?: 0.0) > 0) existing!!.amount.toInt().toString() else "") }
    var isVariable by remember { mutableStateOf(existing?.isVariable ?: false) }
    var category   by remember { mutableStateOf(existing?.category ?: com.bluechip.finance.data.SideIncomeCategory.DIGER) }
    var catExpanded by remember { mutableStateOf(false) }
    // Degisken: bu ay icin tutar girisi (records e eklenecek)
    var thisMonthAmount by remember { mutableStateOf("") }

    Dialog(onDismissRequest = onDismiss) {
        Card(shape = androidx.compose.foundation.shape.RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            elevation = CardDefaults.cardElevation(8.dp)) {
            Column(modifier = Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(if (existing == null) "Yan Gelir Ekle" else "Yan Gelir Duzenle",
                    fontWeight = FontWeight.Bold, fontSize = 17.sp, color = colors.textPrimary)

                ExposedDropdownMenuBox(expanded = catExpanded, onExpandedChange = { catExpanded = it }) {
                    OutlinedTextField(
                        value = "${category.emoji} ${category.label}",
                        onValueChange = {}, readOnly = true,
                        label = { Text("Kategori") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(catExpanded) },
                        modifier = Modifier.fillMaxWidth().menuAnchor(),
                        shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)
                    )
                    ExposedDropdownMenu(expanded = catExpanded, onDismissRequest = { catExpanded = false }) {
                        com.bluechip.finance.data.SideIncomeCategory.values().forEach { cat ->
                            DropdownMenuItem(
                                text = { Text("${cat.emoji} ${cat.label}") },
                                onClick = { category = cat; catExpanded = false }
                            )
                        }
                    }
                }

                OutlinedTextField(
                    value = label, onValueChange = { label = it },
                    label = { Text("Aciklama (opsiyonel)") },
                    singleLine = true, modifier = Modifier.fillMaxWidth(),
                    shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)
                )

                // Sabit: tek tutar. Degisken: bu ayin tutarini gir
                CurrencyField(
                    value = if (isVariable) thisMonthAmount else amount,
                    onValueChange = { if (isVariable) thisMonthAmount = it else amount = it },
                    label = if (isVariable) "Bu Ayin Tutari (TL)" else "Tutar (TL)"
                )

                if (isVariable && existing != null && existing.records.isNotEmpty()) {
                    val avg = existing.effectiveAmount()
                    Text("Gecmis ort.: ${com.bluechip.finance.ui.components.formatMoney(avg)} TL  |  Bos biraksan bu deger kullanilir",
                        fontSize = 11.sp, color = colors.textSecondary)
                }

                Row(modifier = Modifier.fillMaxWidth()
                    .background(if (isVariable) PurplePrimary.copy(alpha = 0.08f) else Color.Transparent,
                        androidx.compose.foundation.shape.RoundedCornerShape(10.dp))
                    .clickable { isVariable = !isVariable }
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = isVariable, onCheckedChange = { isVariable = it },
                        colors = CheckboxDefaults.colors(checkedColor = PurplePrimary))
                    Spacer(Modifier.width(8.dp))
                    Column {
                        Text("Degisken tutar", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = colors.textPrimary)
                        Text("Her ay ortalama hesaplanir", fontSize = 11.sp, color = colors.textSecondary)
                    }
                }

                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(onClick = onDismiss, modifier = Modifier.weight(1f),
                        shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)) { Text("Iptal") }
                    Button(
                        onClick = {
                            val base = existing ?: com.bluechip.finance.data.SideIncome()
                            if (isVariable) {
                                // Degisken: tutari records e ekle
                                val newAmt = thisMonthAmount.toDoubleOrNull()
                                    ?: if (existing != null) existing.effectiveAmount() else 0.0
                                val newRecord = com.bluechip.finance.data.SideIncomeRecord(amount = newAmt)
                                onSave(base.copy(
                                    category = category,
                                    label = label.trim(),
                                    amount = newAmt,
                                    isVariable = true,
                                    records = base.records + newRecord
                                ))
                            } else {
                                onSave(base.copy(
                                    category = category,
                                    label = label.trim(),
                                    amount = amount.toDoubleOrNull() ?: 0.0,
                                    isVariable = false,
                                    records = emptyList()
                                ))
                            }
                        },
                        modifier = Modifier.weight(1f),
                        shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PurplePrimary),
                        enabled = isVariable || amount.isNotBlank()
                    ) { Text("Kaydet", fontWeight = FontWeight.Bold) }
                }
            }
        }
    }
}
