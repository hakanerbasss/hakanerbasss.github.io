package com.bluechip.finance.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.bluechip.finance.data.OvertimeManager
import com.bluechip.finance.data.OvertimeRecord
import com.bluechip.finance.data.OvertimeTrackType
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.ui.components.WheelDatePickerDialog
import com.bluechip.finance.ui.components.formatMoney
import com.bluechip.finance.ui.theme.*
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun OvertimeTrackScreen() {
    val context    = LocalContext.current
    val colors     = LocalAppColors.current
    val dateFmt    = remember { SimpleDateFormat("dd MMM yyyy", Locale("tr")) }
    val monthFmt   = remember { SimpleDateFormat("MMMM yyyy",  Locale("tr")) }

    var records            by remember { mutableStateOf(OvertimeManager.loadAll(context)) }
    var showAdd            by remember { mutableStateOf(false) }
    var editRec            by remember { mutableStateOf<OvertimeRecord?>(null) }
    var showDeleteAll      by remember { mutableStateOf(false) }
    var showDeleteOne      by remember { mutableStateOf<OvertimeRecord?>(null) }

    val profile     = remember { ProfileManager(context).load() }
    val grossSalary = profile.grossSalary

    fun reload() { records = OvertimeManager.loadAll(context) }

    val now             = Calendar.getInstance()
    val thisMonth       = now.get(Calendar.MONTH)
    val thisYear        = now.get(Calendar.YEAR)
    val thisMonthRecs   = records.filter {
        val c = Calendar.getInstance().apply { timeInMillis = it.dateMillis }
        c.get(Calendar.MONTH) == thisMonth && c.get(Calendar.YEAR) == thisYear
    }
    val thisMonthBrut   = thisMonthRecs.sumOf { it.brutAmount }
    val thisMonthNet    = thisMonthRecs.sumOf { it.netAmount }
    val thisMonthHours  = thisMonthRecs.sumOf { it.hours }
    val thisMonthName   = monthFmt.format(now.time).replaceFirstChar { it.uppercase() }

    // %50 birim net saat ucreti - bilgi icin
    val unit50Net  = OvertimeManager.unitHourlyNet(grossSalary, OvertimeTrackType.PCT50)

    val grouped = records.sortedByDescending { it.dateMillis }
        .groupBy {
            val c = Calendar.getInstance().apply { timeInMillis = it.dateMillis }
            "${c.get(Calendar.YEAR)}-${c.get(Calendar.MONTH)}"
        }.entries.toList()

    Scaffold(
        floatingActionButton = {
            FloatingActionButton(
                onClick = { editRec = null; showAdd = true },
                containerColor = PurplePrimary, contentColor = Color.White,
                shape = RoundedCornerShape(16.dp)
            ) { Icon(Icons.Default.Add, "Mesai Ekle") }
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(vertical = 16.dp)
        ) {
            // Baslik
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Mesai Takip", fontWeight = FontWeight.Bold, fontSize = 20.sp, color = colors.textPrimary)
                        Text("Gunluk mesailerinizi kaydedin", fontSize = 12.sp, color = colors.textSecondary)
                    }
                    if (records.isNotEmpty()) {
                        IconButton(onClick = { showDeleteAll = true }) {
                            Icon(Icons.Default.DeleteSweep, null, tint = colors.error, modifier = Modifier.size(22.dp))
                        }
                    }
                }
            }

            // Maaş + birim ucret bilgi karti
            item {
                Card(
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                    elevation = CardDefaults.cardElevation(2.dp)
                ) {
                    Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(modifier = Modifier.fillMaxWidth()) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Brut Maas", fontSize = 11.sp, color = colors.textSecondary)
                                Text(
                                    if (grossSalary > 0) "${formatMoney(grossSalary)} TL" else "Profilde tanimli degil",
                                    fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary
                                )
                            }
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Net Maas", fontSize = 11.sp, color = colors.textSecondary)
                                Text(
                                    if (profile.netSalary > 0) "${formatMoney(profile.netSalary)} TL" else "-",
                                    fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary
                                )
                            }
                        }
                        HorizontalDivider(color = PurplePrimary.copy(alpha = 0.1f))
                        Row(modifier = Modifier.fillMaxWidth()) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Saatlik Brut (%50 FM)", fontSize = 11.sp, color = colors.textSecondary)
                                Text(
                                    if (grossSalary > 0) "${formatMoney(grossSalary / 225.0 * 1.5)} TL/saat" else "-",
                                    fontSize = 13.sp, fontWeight = FontWeight.Medium, color = PurplePrimary
                                )
                            }
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Saatlik Net (%50 FM)", fontSize = 11.sp, color = colors.textSecondary)
                                Text(
                                    if (unit50Net > 0) "${formatMoney(unit50Net)} TL/saat" else "-",
                                    fontSize = 13.sp, fontWeight = FontWeight.Medium, color = colors.success
                                )
                            }
                        }
                        Text(
                            "* Net tahmin: kesintiler sonrasi ~%71.5 kaliyor (vergi dilimine gore degisebilir)",
                            fontSize = 10.sp, color = colors.textSecondary
                        )
                    }
                }
            }

            // Bu ay ozet karti
            item {
                Card(
                    shape = RoundedCornerShape(20.dp),
                    colors = CardDefaults.cardColors(containerColor = PurplePrimary),
                    elevation = CardDefaults.cardElevation(4.dp)
                ) {
                    Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(thisMonthName, fontSize = 13.sp, color = Color.White.copy(alpha = 0.8f))
                        Row(modifier = Modifier.fillMaxWidth()) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Net (ele gecen)", fontSize = 11.sp, color = Color.White.copy(alpha = 0.7f))
                                Text("${formatMoney(thisMonthNet)} TL",
                                    fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Color.White)
                                Text("Brut: ${formatMoney(thisMonthBrut)} TL",
                                    fontSize = 11.sp, color = Color.White.copy(alpha = 0.7f))
                            }
                            Column(horizontalAlignment = Alignment.End) {
                                Text("Toplam Sure", fontSize = 11.sp, color = Color.White.copy(alpha = 0.7f))
                                Text(
                                    if (thisMonthHours == thisMonthHours.toLong().toDouble())
                                        "${thisMonthHours.toInt()} saat"
                                    else "${String.format("%.1f", thisMonthHours)} saat",
                                    fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Color.White
                                )
                                Text("${thisMonthRecs.size} kayit", fontSize = 11.sp, color = Color.White.copy(alpha = 0.7f))
                            }
                        }
                        if (grossSalary <= 0) {
                            Text("Profilde brut maas tanimli degil — Profil > Maas bilgisi girin",
                                fontSize = 11.sp, color = Color.White.copy(alpha = 0.85f))
                        }
                    }
                }
            }

            // Bos liste
            if (records.isEmpty()) {
                item {
                    Box(modifier = Modifier.fillMaxWidth().padding(vertical = 40.dp), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("⏰", fontSize = 48.sp)
                            Text("Henuz mesai kaydi yok", fontSize = 15.sp, color = colors.textSecondary)
                            Text("Sag alttaki + butonuna basin", fontSize = 12.sp, color = colors.textSecondary)
                        }
                    }
                }
            }

            // Ay bazli liste
            grouped.forEach { (_, monthRecs) ->
                val first   = monthRecs.first()
                val cal     = Calendar.getInstance().apply { timeInMillis = first.dateMillis }
                val mName   = monthFmt.format(cal.time).replaceFirstChar { it.uppercase() }
                val mNet    = monthRecs.sumOf { it.netAmount }
                val mBrut   = monthRecs.sumOf { it.brutAmount }
                val mHours  = monthRecs.sumOf { it.hours }

                item {
                    Row(modifier = Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(mName, fontSize = 13.sp, fontWeight = FontWeight.Bold,
                            color = colors.textSecondary, modifier = Modifier.weight(1f))
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Net: ${formatMoney(mNet)} TL", fontSize = 12.sp, color = colors.textSecondary)
                            Text(
                                "${if (mHours == mHours.toLong().toDouble()) mHours.toInt().toString() else String.format("%.1f", mHours)}s  •  Brut: ${formatMoney(mBrut)} TL",
                                fontSize = 11.sp, color = colors.textSecondary
                            )
                        }
                    }
                }

                items(monthRecs, key = { it.id }) { rec ->
                    Card(
                        modifier = Modifier.fillMaxWidth().clickable { editRec = rec; showAdd = true },
                        shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                        elevation = CardDefaults.cardElevation(2.dp)
                    ) {
                        Row(modifier = Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier.size(42.dp).background(PurplePrimary.copy(alpha = 0.1f), RoundedCornerShape(12.dp)),
                                contentAlignment = Alignment.Center
                            ) { Text(rec.type.pct, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = PurplePrimary) }
                            Spacer(Modifier.width(12.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(dateFmt.format(Date(rec.dateMillis)), fontSize = 13.sp,
                                    fontWeight = FontWeight.Medium, color = colors.textPrimary)
                                Text(
                                    "${rec.type.label}  •  ${if (rec.hours == rec.hours.toLong().toDouble()) "${rec.hours.toInt()} saat" else "${String.format("%.1f", rec.hours)} saat"}",
                                    fontSize = 11.sp, color = colors.textSecondary
                                )
                                if (rec.note.isNotBlank()) Text(rec.note, fontSize = 10.sp, color = colors.textSecondary)
                            }
                            Column(horizontalAlignment = Alignment.End) {
                                Text("${formatMoney(rec.netAmount)} TL", fontSize = 14.sp,
                                    fontWeight = FontWeight.Bold, color = colors.success)
                                Text("ele gecen", fontSize = 9.sp, color = colors.textSecondary)
                                Text("brut: ${formatMoney(rec.brutAmount)} TL", fontSize = 10.sp, color = colors.textSecondary)
                                IconButton(onClick = { showDeleteOne = rec }, modifier = Modifier.size(28.dp)) {
                                    Icon(Icons.Default.Close, null, tint = colors.error, modifier = Modifier.size(16.dp))
                                }
                            }
                        }
                    }
                }
            }

            item { Spacer(Modifier.height(80.dp)) }
        }
    }

    // Tumu sil
    if (showDeleteAll) {
        AlertDialog(
            onDismissRequest = { showDeleteAll = false },
            title = { Text("Tum Kayitlari Sil") },
            text  = { Text("Tum mesai gecmisi silinecek. Emin misiniz?") },
            confirmButton = {
                TextButton(onClick = { OvertimeManager.deleteAll(context); reload(); showDeleteAll = false }) {
                    Text("Sil", color = colors.error, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = { TextButton(onClick = { showDeleteAll = false }) { Text("Iptal") } }
        )
    }

    // Tek sil
    showDeleteOne?.let { rec ->
        AlertDialog(
            onDismissRequest = { showDeleteOne = null },
            title = { Text("Mesayi Sil") },
            text  = { Text("${dateFmt.format(Date(rec.dateMillis))} tarihli kayit silinecek.") },
            confirmButton = {
                TextButton(onClick = { OvertimeManager.delete(context, rec.id); reload(); showDeleteOne = null }) {
                    Text("Sil", color = colors.error, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = { TextButton(onClick = { showDeleteOne = null }) { Text("Iptal") } }
        )
    }

    // Ekle / duzenle
    if (showAdd) {
        OvertimeAddDialog(
            existing    = editRec,
            grossSalary = grossSalary,
            onDismiss   = { showAdd = false; editRec = null },
            onSave      = { rec ->
                if (editRec != null) OvertimeManager.update(context, rec)
                else OvertimeManager.add(context, rec)
                reload(); showAdd = false; editRec = null
            }
        )
    }
}

@Composable
private fun OvertimeAddDialog(
    existing:    OvertimeRecord?,
    grossSalary: Double,
    onDismiss:   () -> Unit,
    onSave:      (OvertimeRecord) -> Unit
) {
    val colors = LocalAppColors.current
    val types  = OvertimeTrackType.values().toList()

    var selectedDate   by remember { mutableLongStateOf(existing?.dateMillis ?: System.currentTimeMillis()) }
    var dateText       by remember { mutableStateOf(SimpleDateFormat("dd MMM yyyy", Locale("tr")).format(Date(existing?.dateMillis ?: System.currentTimeMillis()))) }
    var selectedType   by remember { mutableStateOf(existing?.type ?: OvertimeTrackType.PCT50) }
    var hours          by remember { mutableStateOf(existing?.hours ?: 0.0) }
    var note           by remember { mutableStateOf(existing?.note ?: "") }
    var showDatePicker by remember { mutableStateOf(false) }
    var showHourMenu   by remember { mutableStateOf(false) }

    val brutAmount = OvertimeManager.calcBrutAmount(grossSalary, hours, selectedType)
    val netAmount  = OvertimeManager.calcNetAmount(brutAmount)

    fun fmtH(h: Double) = if (h == 0.0) "Saat Sec"
        else if (h == h.toLong().toDouble()) "${h.toInt()} saat"
        else "${String.format("%.1f", h)} saat"

    val hourOptions = listOf(0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0,5.5,6.0,6.5,7.0,7.5,8.0,9.0,10.0,11.0,12.0)

    if (showDatePicker) {
        WheelDatePickerDialog(title = "Mesai Tarihi", onDismiss = { showDatePicker = false }) { sel ->
            selectedDate = sel.timeInMillis
            dateText = SimpleDateFormat("dd MMM yyyy", Locale("tr")).format(sel.time)
        }
    }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            elevation = CardDefaults.cardElevation(8.dp)
        ) {
            Column(
                modifier = Modifier.padding(24.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                Text(if (existing == null) "Mesai Ekle" else "Mesai Duzenle",
                    fontWeight = FontWeight.Bold, fontSize = 17.sp, color = colors.textPrimary)

                // Tarih
                Text("Tarih", fontSize = 13.sp, color = colors.textSecondary)
                OutlinedButton(onClick = { showDatePicker = true },
                    modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp)) {
                    Icon(Icons.Default.DateRange, null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(8.dp)); Text(dateText)
                }

                // Tip
                Text("Mesai Tipi", fontSize = 13.sp, color = colors.textSecondary)
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    types.chunked(3).forEach { row ->
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            row.forEach { t ->
                                val sel = t == selectedType
                                Button(
                                    onClick = { selectedType = t },
                                    modifier = Modifier.weight(1f).height(52.dp),
                                    shape = RoundedCornerShape(10.dp),
                                    colors = ButtonDefaults.buttonColors(
                                        containerColor = if (sel) PurplePrimary else PurplePrimary.copy(alpha = 0.08f),
                                        contentColor   = if (sel) Color.White else PurplePrimary
                                    ),
                                    contentPadding = PaddingValues(4.dp)
                                ) {
                                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                        Text(t.pct, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                        Text(t.label, fontSize = 9.sp, textAlign = TextAlign.Center, maxLines = 1)
                                    }
                                }
                            }
                            repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                        }
                    }
                }

                // Saat
                Text("Sure", fontSize = 13.sp, color = colors.textSecondary)
                Box {
                    OutlinedButton(onClick = { showHourMenu = true },
                        modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp)) {
                        Icon(Icons.Default.AccessTime, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(fmtH(hours), modifier = Modifier.weight(1f))
                        Icon(Icons.Default.ArrowDropDown, null)
                    }
                    DropdownMenu(expanded = showHourMenu, onDismissRequest = { showHourMenu = false }) {
                        hourOptions.forEach { h ->
                            DropdownMenuItem(text = { Text(fmtH(h)) }, onClick = { hours = h; showHourMenu = false })
                        }
                    }
                }

                // Hesaplanan tutar - brut ve net
                if (hours > 0 && grossSalary > 0) {
                    Card(
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = PurplePrimary.copy(alpha = 0.06f))
                    ) {
                        Column(modifier = Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                Text("Brut tutar:", fontSize = 13.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
                                Text("${formatMoney(brutAmount)} TL", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = colors.textPrimary)
                            }
                            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                Text("Ele gecen (net):", fontSize = 13.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
                                Text("${formatMoney(netAmount)} TL", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = colors.success)
                            }
                            Text("* Tahmini — vergi dilimine gore degisebilir",
                                fontSize = 10.sp, color = colors.textSecondary)
                        }
                    }
                } else if (grossSalary <= 0) {
                    Text("Profilde brut maas tanimli degil", fontSize = 11.sp, color = colors.warning)
                }

                // Not
                OutlinedTextField(value = note, onValueChange = { note = it },
                    label = { Text("Not (opsiyonel)") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp))

                // Butonlar
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(onClick = onDismiss, modifier = Modifier.weight(1f), shape = RoundedCornerShape(12.dp)) { Text("Iptal") }
                    Button(
                        onClick = {
                            onSave((existing ?: OvertimeRecord()).copy(
                                dateMillis = selectedDate, hours = hours,
                                type = selectedType, brutAmount = brutAmount,
                                netAmount = netAmount, note = note.trim()
                            ))
                        },
                        modifier = Modifier.weight(1f), shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PurplePrimary),
                        enabled = hours > 0
                    ) { Text("Kaydet", fontWeight = FontWeight.Bold) }
                }
            }
        }
    }
}
