package com.bluechip.finance.ui.screens

import android.content.Intent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
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
import com.bluechip.finance.UnityAdsManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.LaunchedEffect
import com.bluechip.finance.data.HistoryEntry
import com.bluechip.finance.data.HistoryManager
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.ui.components.*
import com.bluechip.finance.ui.theme.*
import kotlinx.coroutines.launch

data class OvertimeType(val pct: String, val name: String, val mult: Double, val law: String, val desc: String)
data class OvertimeEntry(val typeIndex: Int = 1, val hours: Double = 0.0)

@Composable
fun OvertimeScreen() {
    val context = LocalContext.current
    val activity = context as? android.app.Activity
    val colors = LocalAppColors.current
    val scrollState = rememberScrollState()
    val scope = rememberCoroutineScope()

    var salary by remember { mutableStateOf("") }
    var profileLoaded by remember { mutableStateOf(false) }
    var showResult by remember { mutableStateOf(false) }
    var showInfoDialog by remember { mutableStateOf(false) }
    val profileManager = remember { ProfileManager(context) }

    val types = remember { listOf(
        OvertimeType("%25",  "Gece",          1.25, "Mad. 69",    "20:00-06:00 gece"),
        OvertimeType("%50",  "Fazla Çalışma", 1.5,  "Mad. 41",    "Haftalık 45+ saat"),
        OvertimeType("%75",  "Gece+Fazla",    1.75, "Mad. 41+69", "Gece fazla mesai"),
        OvertimeType("%100", "Bayram/Tatil",  2.0,  "Mad. 47",    "Bayram/tatil günü"),
        OvertimeType("%125", "Gece+Tatil",    2.25, "Mad. 47+69", "Tatil gece mesai"),
        OvertimeType("%200", "Resmi Tatil",   3.0,  "Mad. 47",    "Resmi tatil 3 kat ücret")
    ) }

    LaunchedEffect(Unit) {
        val p = profileManager.load()
        if (p.isLoggedIn && p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileLoaded = true }
    }

    LaunchedEffect(Unit) {
        val p = profileManager.load()
        if (p.isLoggedIn && p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileLoaded = true }
    }

    var entries by remember { mutableStateOf(listOf(OvertimeEntry())) }
    var showTypeDialog by remember { mutableIntStateOf(-1) }
    var showHoursDialog by remember { mutableIntStateOf(-1) }
    var resultLines by remember { mutableStateOf<List<Triple<String, String, Double>>>(emptyList()) }
    var grandTotalBrut by remember { mutableDoubleStateOf(0.0) }
    var grandTotalNet by remember { mutableDoubleStateOf(0.0) }
    var baseSalary by remember { mutableDoubleStateOf(0.0) }

    fun formatHours(h: Double): String {
        return if (h == 0.0) "Saat Seç"
        else if (h == h.toLong().toDouble()) "${h.toInt()} saat"
        else "${String.format("%.1f", h)} saat"
    }

    fun calculate() {
        if (salary.isBlank()) {
            android.widget.Toast.makeText(context, "Lutfen maas giriniz", android.widget.Toast.LENGTH_SHORT).show()
            return
        }
        val sal = salary.toDoubleOrNull() ?: run {
            android.widget.Toast.makeText(context, "Gecersiz maas degeri", android.widget.Toast.LENGTH_SHORT).show()
            return
        }
        val hasHours = entries.any { it.hours > 0 }
        if (!hasHours) {
            android.widget.Toast.makeText(context, "Lutfen en az bir mesai saati giriniz", android.widget.Toast.LENGTH_SHORT).show()
            return
        }
        baseSalary = sal
        val base = sal / 225.0
        var total = 0.0
        val lines = mutableListOf<Triple<String, String, Double>>()

        entries.forEach { entry ->
            if (entry.hours > 0) {
                val type = types[entry.typeIndex]
                val rate = base * type.mult
                val lineTotal = rate * entry.hours
                total += lineTotal
                lines.add(Triple("${type.pct} ${type.name} (${formatHours(entry.hours).replace(" saat", "s")})", "${formatMoney(lineTotal)}₺", lineTotal))
            }
        }

        grandTotalBrut = total
        grandTotalNet = total - (total * 0.14) - (total * 0.01)
        resultLines = lines
        val shouldShow = lines.isNotEmpty()
        if (shouldShow) {
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
        if (showResult) HistoryManager.save(context, HistoryEntry(
            screenId = "overtime", timestamp = System.currentTimeMillis(),
            label = "${formatMoney(sal)}₺ — ${entries.size} kalem",
            resultSummary = "Net Mesai: ~${formatMoney(grandTotalNet)}₺",
            salary = salary
        ))
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        androidx.compose.animation.AnimatedVisibility(
            visible = !showResult,
            enter = androidx.compose.animation.expandVertically(),
            exit = androidx.compose.animation.shrinkVertically()
        ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        SectionHeader("FAZLA MESAİ HESAPLAMA", Icons.Default.AccessTime) { showInfoDialog = true }
        CurrencyField(value = salary, onValueChange = { salary = it; profileLoaded = false }, label = "Brut Maas (TL)")
        if (profileLoaded) ProfileAutoFillNote()

        Text("Mesai Kalemleri", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary)

        entries.forEachIndexed { idx, entry ->
            Card(shape = RoundedCornerShape(12.dp), colors = CardDefaults.cardColors(containerColor = colors.cardGray)) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Tür seçimi
                    OutlinedButton(
                        onClick = { showTypeDialog = idx },
                        modifier = Modifier.weight(1f).height(48.dp),
                        shape = RoundedCornerShape(8.dp),
                        contentPadding = PaddingValues(horizontal = 6.dp)
                    ) {
                        Text(
                            types[entry.typeIndex].pct + " " + types[entry.typeIndex].name,
                            fontSize = 11.sp, maxLines = 1
                        )
                    }

                    // Saat seçimi - aynı boyut
                    OutlinedButton(
                        onClick = { showHoursDialog = idx },
                        modifier = Modifier.weight(1f).height(48.dp),
                        shape = RoundedCornerShape(8.dp),
                        contentPadding = PaddingValues(horizontal = 6.dp)
                    ) {
                        Text(formatHours(entry.hours), fontSize = 11.sp, maxLines = 1)
                    }

                    // Sil
                    if (entries.size > 1) {
                        IconButton(
                            onClick = { entries = entries.toMutableList().also { it.removeAt(idx) } },
                            modifier = Modifier.size(32.dp)
                        ) { Icon(Icons.Default.Close, "Sil", tint = colors.error, modifier = Modifier.size(16.dp)) }
                    }
                }
            }
        }

        OutlinedButton(
            onClick = { entries = entries + OvertimeEntry() },
            modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp)
        ) { Icon(Icons.Default.Add, null, Modifier.size(18.dp)); Spacer(Modifier.width(4.dp)); Text("Mesai Kalemi Ekle") }

        HistoryCard(screenId = "overtime") { restored -> salary = restored; profileLoaded = false }
        ProfileFillButton {
            val p = profileManager.load()
            if (p.isLoggedIn && p.grossSalary > 0) { salary = p.grossSalary.toInt().toString(); profileLoaded = true }
        }
        ActionButtons(onCalculate = { calculate() }, onReset = { salary = ""; entries = listOf(OvertimeEntry()); showResult = false; profileLoaded = false })
        } // inputs column
        } // AnimatedVisibility

        ResultCard(visible = showResult) {
            Text("SONUÇ", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)
            Spacer(Modifier.height(8.dp))
            ResultLine("Net Maaş", "${formatMoney(baseSalary)}₺")
            ResultLine("Birim Ücret", "${formatMoney(baseSalary / 225.0)}₺/saat")
            HorizontalDivider(Modifier.padding(vertical = 6.dp))
            resultLines.forEach { (label, value, _) -> ResultLine(label, value) }
            HorizontalDivider(Modifier.padding(vertical = 6.dp))
            ResultLine("Brüt Toplam", "${formatMoney(grandTotalBrut)}₺", colors.textPrimary, true)
            ResultLine("SGK (%14)", "-${formatMoney(grandTotalBrut * 0.14)}₺", colors.error)
            ResultLine("İşsizlik (%1)", "-${formatMoney(grandTotalBrut * 0.01)}₺", colors.error)
            Spacer(Modifier.height(4.dp))
            BigResult("Tahmini Net Mesai", "~${formatMoney(grandTotalNet)}₺")
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
            Spacer(Modifier.height(8.dp))
            ShareButton {
                val text = buildString {
                    append("💰 FAZLA MESAİ\nMaaş: ${formatMoney(baseSalary)}₺\n")
                    resultLines.forEach { (l, v, _) -> append("$l: $v\n") }
                    append("Brüt: ${formatMoney(grandTotalBrut)}₺\nNet: ~${formatMoney(grandTotalNet)}₺\n📱 Baretim Mavi")
                }
                context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text) }, "Paylaş"))
            }
        }
    }

    // Mesai türü seçim
    if (showTypeDialog >= 0) {
        AlertDialog(
            onDismissRequest = { showTypeDialog = -1 },
            title = { Text("Mesai Türü") },
            text = {
                Column {
                    types.forEachIndexed { i, type ->
                        Row(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                            RadioButton(
                                selected = entries[showTypeDialog].typeIndex == i,
                                onClick = {
                                    entries = entries.toMutableList().also { it[showTypeDialog] = it[showTypeDialog].copy(typeIndex = i) }
                                    showTypeDialog = -1
                                })
                            Spacer(Modifier.width(8.dp))
                            Column {
                                Text("${type.pct} - ${type.name}", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                Text("${type.desc} (${type.law})", fontSize = 12.sp, color = colors.textSecondary)
                            }
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { showTypeDialog = -1 }) { Text("Kapat") } }
        )
    }

    // Saat seçim - basit scrollable liste
    if (showHoursDialog >= 0) {
        val currentHours = entries[showHoursDialog].hours
        var addHalf by remember(showHoursDialog) { mutableStateOf(currentHours != 0.0 && currentHours != currentHours.toLong().toDouble()) }
        val listState = rememberLazyListState()

        // Mevcut seçime scroll
        LaunchedEffect(showHoursDialog) {
            val scrollTo = if (currentHours > 0) (currentHours.toInt() - 1).coerceAtLeast(0) else 0
            listState.scrollToItem(scrollTo)
        }

        AlertDialog(
            onDismissRequest = { showHoursDialog = -1 },
            title = { Text("Saat Seç") },
            text = {
                Column {
                    // Yarım saat checkbox
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = addHalf, onCheckedChange = { addHalf = it })
                        Spacer(Modifier.width(4.dp))
                        Text("Yarım saat ekle (+0.5)", fontSize = 13.sp)
                    }

                    Spacer(Modifier.height(8.dp))

                    // 1-190 scrollable liste
                    LazyColumn(
                        state = listState,
                        modifier = Modifier.height(300.dp).fillMaxWidth()
                    ) {
                        items((1..190).toList()) { hour ->
                            val isSelected = currentHours.toInt() == hour
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                RadioButton(
                                    selected = isSelected,
                                    onClick = {
                                        val finalHours = if (addHalf) hour + 0.5 else hour.toDouble()
                                        entries = entries.toMutableList().also { it[showHoursDialog] = it[showHoursDialog].copy(hours = finalHours) }
                                        showHoursDialog = -1
                                    }
                                )
                                Spacer(Modifier.width(8.dp))
                                Text(
                                    if (addHalf) "${hour}.5 saat" else "$hour saat",
                                    fontSize = 14.sp,
                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                    color = if (isSelected) MaterialTheme.colorScheme.primary else colors.textPrimary
                                )
                            }
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { showHoursDialog = -1 }) { Text("Kapat") } }
        )
    }

    // Bilgi
    if (showInfoDialog) {
        AlertDialog(
            onDismissRequest = { showInfoDialog = false },
            title = { Text("Fazla Mesai") },
            text = {
                Text(
                    "%25 Gece (Mad.69) × 1.25\n%50 Fazla (Mad.41) × 1.50\n%75 Gece+Fazla × 1.75\n%100 Bayram (Mad.47) × 2.00\n%125 Gece+Tatil × 2.25\n\n💡 Birden fazla mesai türü ekleyebilirsiniz.",
                    fontSize = 13.sp
                )
            },
            confirmButton = { TextButton(onClick = { showInfoDialog = false }) { Text("Tamam") } }
        )
    }
}
