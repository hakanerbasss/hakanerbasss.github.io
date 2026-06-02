package com.bluechip.finance.ui.screens

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.bluechip.finance.data.Payment
import com.bluechip.finance.data.PaymentCategory
import com.bluechip.finance.data.PaymentManager
import com.bluechip.finance.data.PaymentRecord
import com.bluechip.finance.ui.components.formatMoney
import com.bluechip.finance.ui.theme.*
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun PaymentScreen(autoAdd: Boolean = false) {
    val context = LocalContext.current
    val colors  = LocalAppColors.current
    val scrollState = rememberScrollState()

    var payments  by remember { mutableStateOf(PaymentManager.getActivePayments(context)) }
    var records   by remember { mutableStateOf(PaymentManager.getRecords(context)) }
    var monthly   by remember { mutableStateOf(PaymentManager.getMonthlyTotals(context)) }
    var upcoming  by remember { mutableStateOf(PaymentManager.getUpcomingThisMonth(context)) }

    var showAddDialog    by remember { mutableStateOf(autoAdd) }
    var editPayment      by remember { mutableStateOf<Payment?>(null) }
    var showDeleteConfirm by remember { mutableStateOf<Payment?>(null) }
    var selectedTab      by remember { mutableStateOf(0) }  // 0=Yaklaşan 1=Geçmiş 2=Grafik
    var showClearDialog  by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        PaymentManager.autoMarkDuePayments(context)
        payments = PaymentManager.getActivePayments(context)
        records  = PaymentManager.getRecords(context)
        monthly  = PaymentManager.getMonthlyTotals(context)
        upcoming = PaymentManager.getUpcomingThisMonth(context)
    }

    fun refresh() {
        payments = PaymentManager.getActivePayments(context)
        records  = PaymentManager.getRecords(context)
        monthly  = PaymentManager.getMonthlyTotals(context)
        upcoming = PaymentManager.getUpcomingThisMonth(context)
    }

    // Diyaloglar
    if (showAddDialog || editPayment != null) {
        PaymentAddDialog(
            existing = editPayment,
            onDismiss = { showAddDialog = false; editPayment = null },
            onSave = { p -> PaymentManager.savePayment(context, p); refresh(); showAddDialog = false; editPayment = null }
        )
    }
    showDeleteConfirm?.let { p ->
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = null },
            title = { Text("Ödemeyi Sil") },
            text  = { Text("\"${p.name}\" silinsin mi?") },
            confirmButton = {
                TextButton(onClick = { PaymentManager.deletePayment(context, p.id); refresh(); showDeleteConfirm = null }) {
                    Text("Sil", color = colors.error)
                }
            },
            dismissButton = { TextButton(onClick = { showDeleteConfirm = null }) { Text("İptal") } }
        )
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)) {

        // ── Başlık + Ekle butonu ──────────────────────────────────
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Payment, null, tint = PurplePrimary, modifier = Modifier.size(24.dp))
            Spacer(Modifier.width(8.dp))
            Text("Ödeme Takip", fontWeight = FontWeight.Bold, fontSize = 20.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
            FloatingActionButton(
                onClick = { showAddDialog = true },
                modifier = Modifier.size(42.dp),
                containerColor = PurplePrimary,
                contentColor = Color.White,
                elevation = FloatingActionButtonDefaults.elevation(4.dp)
            ) { Icon(Icons.Default.Add, null, modifier = Modifier.size(22.dp)) }
        }

        // ── Özet kartları ─────────────────────────────────────────
        val thisMonthTotal = upcoming.sumOf { it.amount }
        val totalPaid = PaymentManager.getTotalPaid(context)
        val highest = PaymentManager.getHighestMonth(context)

        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SummaryMiniCard(
                modifier = Modifier.weight(1f),
                title = "Bu Ay Ödenecek",
                value = "${formatMoney(thisMonthTotal)} ₺",
                color = PurplePrimary,
                icon = Icons.Default.DateRange
            )
            SummaryMiniCard(
                modifier = Modifier.weight(1f),
                title = "Toplam Ödendi",
                value = "${formatMoney(totalPaid)} ₺",
                color = Color(0xFF2E7D32),
                icon = Icons.Default.CheckCircle
            )
        }

        // Uyarı: en yüksek ay
        if (highest != null) {
            val lastTwo = monthly.takeLast(2)
            val isIncreased = lastTwo.size == 2 && lastTwo[1].second > lastTwo[0].second * 1.1
            if (isIncreased) {
                Card(shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = colors.warning.copy(alpha = 0.12f))) {
                    Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("⚠️", fontSize = 20.sp)
                        Spacer(Modifier.width(8.dp))
                        Column {
                            Text("Harcama Arttı!", fontWeight = FontWeight.Bold, fontSize = 13.sp, color = colors.warning)
                            Text("En yüksek ay: ${highest.first} — ${formatMoney(highest.second)} ₺", fontSize = 12.sp, color = colors.textSecondary)
                        }
                    }
                }
            }
        }

        // ── Tab seçici ────────────────────────────────────────────
        val tabs = listOf("Yaklaşan", "Geçmiş", "Grafik")
        TabRow(
            selectedTabIndex = selectedTab,
            containerColor = colors.cardBg,
            contentColor = PurplePrimary,
            modifier = Modifier.clip(RoundedCornerShape(12.dp))
        ) {
            tabs.forEachIndexed { i, t ->
                Tab(selected = selectedTab == i, onClick = { selectedTab = i },
                    text = { Text(t, fontSize = 13.sp, fontWeight = FontWeight.Medium) })
            }
        }

        // ── Tab içerikleri ────────────────────────────────────────
        when (selectedTab) {

            // YAKLAŞAN ÖDEMELER
            0 -> {
                if (payments.isEmpty()) {
                    EmptyState("Henüz ödeme yok", "Sağ üstteki + ile ekle") { showAddDialog = true }
                } else {
                    payments.sortedBy { it.dueDayOfMonth }.forEach { p ->
                        PaymentCard(
                            payment = p,
                            context = context,
                            onPaid = { PaymentManager.markAsPaid(context, p); refresh() },
                            onEdit = { editPayment = p },
                            onDelete = { showDeleteConfirm = p },
                            onUnpaid = {
                                val cal2 = Calendar.getInstance()
                                val rec = PaymentManager.getRecords(context)
                                    .firstOrNull { it.paymentId == p.id
                                        && it.dueMonth == cal2.get(Calendar.MONTH)
                                        && it.dueYear  == cal2.get(Calendar.YEAR) }
                                if (rec != null) { PaymentManager.deleteRecord(context, rec.id); refresh() }
                            }
                        )
                    }
                }
            }

            // GEÇMİŞ ÖDEMELER
            1 -> {
                if (records.isEmpty()) {
                    EmptyState("Henüz ödeme kaydı yok", "Ödeme yaptıkça burada görünür")
                } else {
                    val fmt = SimpleDateFormat("dd.MM.yyyy", Locale.getDefault())
                    records.take(50).forEach { r ->
                        RecordCard(
                            record = r,
                            dateFormat = fmt,
                            onDelete = {
                                PaymentManager.deleteRecord(context, r.id)
                                records = PaymentManager.getRecords(context)
                                monthly = PaymentManager.getMonthlyTotals(context)
                            },
                            onEdit = { editPayment = payments.firstOrNull { p -> p.id == r.paymentId } }
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(
                        onClick = { showClearDialog = true },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFD32F2F)),
                        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFD32F2F))
                    ) {
                        Icon(Icons.Default.Delete, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Geçmişi Temizle", fontSize = 13.sp)
                    }
                }
            }

            // AYLIK GRAFİK
            2 -> {
                MonthlyChart(monthly = monthly)

                // Kategori bazlı özet (bu ay)
                if (records.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    Text("Kategori Dağılımı (Bu Ay)", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary)
                    val cal = Calendar.getInstance()
                    val thisMonth = cal.get(Calendar.MONTH)
                    val thisYear  = cal.get(Calendar.YEAR)
                    val thisMonthRecords = records.filter { it.dueMonth == thisMonth && it.dueYear == thisYear }
                    if (thisMonthRecords.isEmpty()) {
                        Text("Bu ay henüz ödeme kaydı yok.", fontSize = 13.sp, color = colors.textSecondary)
                    } else {
                        PaymentCategory.values().forEach { cat ->
                            val total = thisMonthRecords.filter { it.category == cat }.sumOf { it.amount }
                            if (total > 0) {
                                Row(modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
                                    verticalAlignment = Alignment.CenterVertically) {
                                    Text(cat.emoji, fontSize = 16.sp)
                                    Spacer(Modifier.width(8.dp))
                                    Text(cat.label, fontSize = 13.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                                    Text("${formatMoney(total)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = PurplePrimary)
                                }
                            }
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))
    }

    // Gecmisi temizle onay dialog
    if (showClearDialog) {
        AlertDialog(
            onDismissRequest = { showClearDialog = false },
            title = { Text("Geçmişi Temizle") },
            text = { Text("Tüm ödeme geçmişi silinecek. Emin misiniz?") },
            confirmButton = {
                TextButton(onClick = {
                    PaymentManager.clearRecords(context)
                    refresh()
                    showClearDialog = false
                }) { Text("Temizle", color = Color(0xFFD32F2F)) }
            },
            dismissButton = {
                TextButton(onClick = { showClearDialog = false }) { Text("İptal") }
            }
        )
    }
}

// ── Ödeme Kartı ───────────────────────────────────────────────────
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun PaymentCard(
    payment: Payment,
    context: android.content.Context,
    onPaid: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onUnpaid: () -> Unit
) {
    val colors = LocalAppColors.current
    val cal = Calendar.getInstance()
    val today = cal.get(Calendar.DAY_OF_MONTH)
    val daysLeft = payment.dueDayOfMonth - today
    val isOverdue = daysLeft < 0
    val isUrgent  = daysLeft in 0..3

    val borderColor = when {
        isOverdue -> colors.error
        isUrgent  -> colors.warning
        else      -> Color.Transparent
    }

    Card(shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(2.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
        modifier = Modifier.fillMaxWidth()) {
        Row(modifier = Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            // Emoji ikonu
            Box(modifier = Modifier.size(46.dp)
                .background(PurplePrimary.copy(alpha = 0.1f), RoundedCornerShape(14.dp)),
                contentAlignment = Alignment.Center) {
                Text(payment.category.emoji, fontSize = 22.sp)
            }
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(payment.name, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(payment.category.label, fontSize = 11.sp, color = colors.textSecondary)
                Spacer(Modifier.height(2.dp))
                val dueTxt = when {
                    isOverdue -> "Geçti! (ayın ${payment.dueDayOfMonth})"
                    daysLeft == 0 -> "Bugün!"
                    else -> "Ayın ${payment.dueDayOfMonth} — $daysLeft gün kaldı"
                }
                Text(dueTxt, fontSize = 11.sp, color = when { isOverdue -> colors.error; isUrgent -> colors.warning; else -> colors.info })
            }
            Column(horizontalAlignment = Alignment.End) {
                Text("${formatMoney(payment.amount)} ₺", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = PurplePrimary)
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    val paidThisMonth = PaymentManager.isPaidThisMonth(context, payment.id)
                    Box(
                        modifier = Modifier
                            .size(30.dp)
                            .background(
                                (if (paidThisMonth) Color(0xFF2E7D32)
                                else androidx.compose.ui.graphics.Color(0xFF9E9E9E)).copy(alpha = 0.1f),
                                CircleShape
                            )
                            .combinedClickable(
                                onClick     = { if (!paidThisMonth) onPaid() },
                                onLongClick = { if (paidThisMonth) onUnpaid() }
                            ),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            if (paidThisMonth) Icons.Default.CheckCircle
                            else Icons.Default.RadioButtonUnchecked,
                            null,
                            tint = if (paidThisMonth) Color(0xFF2E7D32)
                                   else androidx.compose.ui.graphics.Color(0xFF9E9E9E),
                            modifier = Modifier.size(16.dp)
                        )
                    }
                    SmallIconBtn(Icons.Default.Edit, colors.info) { onEdit() }
                    SmallIconBtn(Icons.Default.Delete, colors.error) { onDelete() }
                }
            }
        }
    }
}

// ── Geçmiş kayıt kartı ───────────────────────────────────────────
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun RecordCard(
    record: PaymentRecord,
    dateFormat: SimpleDateFormat,
    onDelete: () -> Unit,
    onEdit: () -> Unit
) {
    val colors = LocalAppColors.current
    var showActions by remember { mutableStateOf(false) }
    Column {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .combinedClickable(onClick = {}, onLongClick = { showActions = !showActions })
                .padding(vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(record.category.emoji, fontSize = 18.sp, modifier = Modifier.width(30.dp))
            Spacer(Modifier.width(8.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(record.paymentName, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = colors.textPrimary)
                Text(dateFormat.format(Date(record.paidAt)), fontSize = 11.sp, color = colors.textSecondary)
            }
            Text("${formatMoney(record.amount)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Color(0xFF2E7D32))
        }
        AnimatedVisibility(visible = showActions) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(start = 38.dp, bottom = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedButton(
                    onClick = { showActions = false; onEdit() },
                    modifier = Modifier.height(32.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = colors.info),
                    border = androidx.compose.foundation.BorderStroke(1.dp, colors.info)
                ) {
                    Icon(Icons.Default.Edit, null, modifier = Modifier.size(13.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Duzenle", fontSize = 11.sp)
                }
                OutlinedButton(
                    onClick = { showActions = false; onDelete() },
                    modifier = Modifier.height(32.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFD32F2F)),
                    border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFD32F2F))
                ) {
                    Icon(Icons.Default.Delete, null, modifier = Modifier.size(13.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Sil", fontSize = 11.sp)
                }
            }
        }
        HorizontalDivider(color = colors.cardGray)
    }
}

// ── Aylık bar grafik ─────────────────────────────────────────────
@Composable
private fun MonthlyChart(monthly: List<Pair<String, Double>>) {
    val colors = LocalAppColors.current
    val maxVal = monthly.maxOfOrNull { it.second }?.takeIf { it > 0 } ?: 1.0
    Card(shape = RoundedCornerShape(16.dp), elevation = CardDefaults.cardElevation(2.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Son 6 Ay", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary)
            Spacer(Modifier.height(12.dp))
            Row(modifier = Modifier.fillMaxWidth().height(120.dp),
                horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.Bottom) {
                monthly.forEach { (label, value) ->
                    val ratio = (value / maxVal).toFloat().coerceIn(0.05f, 1f)
                    val isHighest = value == maxVal && value > 0
                    Column(horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Bottom,
                        modifier = Modifier.weight(1f).fillMaxHeight()) {
                        if (value > 0) {
                            Text(formatMoney(value).let { if (it.length > 6) "${it.take(4)}.." else it },
                                fontSize = 8.sp, color = if (isHighest) colors.warning else colors.textSecondary,
                                textAlign = TextAlign.Center)
                        }
                        Spacer(Modifier.height(2.dp))
                        Box(modifier = Modifier.fillMaxWidth(0.6f).fillMaxHeight(ratio)
                            .background(if (isHighest) colors.warning else PurplePrimary.copy(alpha = 0.7f),
                                RoundedCornerShape(topStart = 6.dp, topEnd = 6.dp)))
                        Spacer(Modifier.height(4.dp))
                        Text(label, fontSize = 9.sp, color = colors.textSecondary, textAlign = TextAlign.Center)
                    }
                }
            }
        }
    }
}

// ── Ödeme Ekle / Düzenle Dialog ───────────────────────────────────
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PaymentAddDialog(existing: Payment?, onDismiss: () -> Unit, onSave: (Payment) -> Unit) {
    val colors = LocalAppColors.current
    var name       by remember { mutableStateOf(existing?.name ?: "") }
    var amount     by remember { mutableStateOf(if ((existing?.amount ?: 0.0) > 0) existing!!.amount.toInt().toString() else "") }
    var dueDay     by remember { mutableStateOf(existing?.dueDayOfMonth?.toString() ?: "") }
    var category   by remember { mutableStateOf(existing?.category ?: PaymentCategory.FATURA) }
    var isRecurring by remember { mutableStateOf(existing?.isRecurring ?: true) }
    var isVariable  by remember { mutableStateOf(existing?.isVariable ?: false) }
    var catExpanded by remember { mutableStateOf(false) }

    Dialog(onDismissRequest = onDismiss) {
        Card(shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            elevation = CardDefaults.cardElevation(8.dp)) {
            Column(modifier = Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(if (existing == null) "Ödeme Ekle" else "Düzenle",
                    fontWeight = FontWeight.Bold, fontSize = 18.sp, color = colors.textPrimary)

                OutlinedTextField(value = name, onValueChange = { name = it },
                    label = { Text("Ödeme Adı (Elektrik, Kira...)") },
                    singleLine = true, modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp))

                OutlinedTextField(value = amount, onValueChange = { amount = it.filter { c -> c.isDigit() } },
                    label = { Text("Tutar (₺)") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp),
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Number))

                OutlinedTextField(value = dueDay, onValueChange = { v -> if (v.isEmpty() || (v.toIntOrNull() ?: 0) in 1..31) dueDay = v },
                    label = { Text("Son Ödeme Günü (Ayın kaçı?)") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp),
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Number))

                // Kategori seçici
                ExposedDropdownMenuBox(expanded = catExpanded, onExpandedChange = { catExpanded = it }) {
                    OutlinedTextField(value = "${category.emoji} ${category.label}", onValueChange = {},
                        readOnly = true, label = { Text("Kategori") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(catExpanded) },
                        modifier = Modifier.fillMaxWidth().menuAnchor(), shape = RoundedCornerShape(12.dp))
                    ExposedDropdownMenu(expanded = catExpanded, onDismissRequest = { catExpanded = false }) {
                        PaymentCategory.values().forEach { cat ->
                            DropdownMenuItem(text = { Text("${cat.emoji} ${cat.label}") },
                                onClick = { category = cat; catExpanded = false })
                        }
                    }
                }

                // Tekrarlayan toggle
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Switch(
                        checked = isRecurring,
                        onCheckedChange = { isRecurring = it; if (!it) isVariable = false },
                        colors = SwitchDefaults.colors(checkedThumbColor = Color.White, checkedTrackColor = PurplePrimary)
                    )
                    Spacer(Modifier.width(10.dp))
                    Column {
                        Text("Aylik Tekrarlayan", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = colors.textPrimary)
                        Text("Her ay ayni gunde tekrar eder", fontSize = 11.sp, color = colors.textSecondary)
                    }
                }
                if (isRecurring) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(
                                if (isVariable) PurplePrimary.copy(alpha = 0.08f) else Color.Transparent,
                                RoundedCornerShape(10.dp)
                            )
                            .clickable { isVariable = !isVariable }
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = isVariable,
                            onCheckedChange = { isVariable = it },
                            colors = CheckboxDefaults.colors(checkedColor = PurplePrimary)
                        )
                        Spacer(Modifier.width(8.dp))
                        Column {
                            Text("Degisken tutar", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = colors.textPrimary)
                            Text("Sonraki ay odenen tutarlarin ortalamasi (dogalgaz, su vb.)",
                                fontSize = 11.sp, color = colors.textSecondary)
                        }
                    }
                }

                // Butonlar
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(onClick = onDismiss, modifier = Modifier.weight(1f), shape = RoundedCornerShape(12.dp)) { Text("İptal") }
                    Button(
                        onClick = {
                            val p = (existing ?: Payment()).copy(
                                name = name.trim(),
                                amount = amount.toDoubleOrNull() ?: 0.0,
                                dueDayOfMonth = dueDay.toIntOrNull()?.coerceIn(1, 31) ?: 1,
                                category = category,
                                isRecurring = isRecurring,
                                isVariable  = isVariable && isRecurring
                            )
                            if (p.name.isNotBlank() && p.amount > 0) onSave(p)
                        },
                        modifier = Modifier.weight(1f), shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PurplePrimary)
                    ) { Text("Kaydet", fontWeight = FontWeight.Bold) }
                }
            }
        }
    }
}

// ── Yardımcı bileşenler ───────────────────────────────────────────
@Composable
private fun SummaryMiniCard(modifier: Modifier, title: String, value: String, color: Color, icon: androidx.compose.ui.graphics.vector.ImageVector) {
    val colors = LocalAppColors.current
    Card(shape = RoundedCornerShape(16.dp), elevation = CardDefaults.cardElevation(2.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg), modifier = modifier) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(icon, null, tint = color, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text(title, fontSize = 11.sp, color = colors.textSecondary)
            }
            Spacer(Modifier.height(4.dp))
            Text(value, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = color)
        }
    }
}

@Composable
private fun SmallIconBtn(icon: androidx.compose.ui.graphics.vector.ImageVector, tint: Color, onClick: () -> Unit) {
    Box(modifier = Modifier.size(30.dp).background(tint.copy(alpha = 0.1f), CircleShape).clickable { onClick() },
        contentAlignment = Alignment.Center) {
        Icon(icon, null, tint = tint, modifier = Modifier.size(16.dp))
    }
}

@Composable
private fun EmptyState(title: String, subtitle: String, onClick: (() -> Unit)? = null) {
    val colors = LocalAppColors.current
    Column(modifier = Modifier.fillMaxWidth().padding(32.dp).then(if (onClick != null) Modifier.clickable { onClick() } else Modifier),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("📋", fontSize = 40.sp)
        Text(title, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary)
        Text(subtitle, fontSize = 13.sp, color = colors.textSecondary, textAlign = TextAlign.Center)
    }
}
