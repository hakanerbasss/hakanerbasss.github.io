package com.bluechip.finance.ui.screens

import android.app.Activity
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.bluechip.finance.UnityAdsManager
import com.bluechip.finance.data.*
import com.bluechip.finance.data.AdFreeManager
import com.bluechip.finance.ui.components.CurrencyField
import com.bluechip.finance.ui.components.formatMoney
import com.bluechip.finance.ui.components.formatNumber
import com.bluechip.finance.ui.theme.*
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SavingsScreen() {
    val context       = LocalContext.current
    val colors        = LocalAppColors.current
    val scope         = rememberCoroutineScope()
    val manager       = remember { SavingsManager(context) }
    val isAdFree      = remember { AdFreeManager.isAdFree(context) }

    var records       by remember { mutableStateOf(manager.loadAll()) }
    var priceCache    by remember { mutableStateOf(manager.loadPriceCache()) }
    var isUpdating    by remember { mutableStateOf(false) }
    var selectedTab   by remember { mutableIntStateOf(0) }
    var showAddDialog by remember { mutableStateOf(false) }
    var editRecord    by remember { mutableStateOf<SavingsRecord?>(null) }
    var detailRecord  by remember { mutableStateOf<SavingsRecord?>(null) }
    var showAdSnack   by remember { mutableStateOf(false) }

    val tabs = listOf(
        SavingsCategory.CRYPTO to "\uD83E\uDE99",
        SavingsCategory.METAL  to "\uD83E\uDD47",
        SavingsCategory.DOVIZ  to "\uD83D\uDCB5"
    )

    // Ilk yuklemede fiyatlari guncelle (stale ise)
    LaunchedEffect(Unit) {
        if (priceCache.isStale() && records.isNotEmpty()) {
            isUpdating = true
            val usdRate = priceCache.prices["USD"] ?: 32.5
            val fresh = SavingsPriceService.fetchPrices(records, usdRate)
            if (fresh.isNotEmpty()) {
                manager.savePriceCache(fresh)
                priceCache = manager.loadPriceCache()
            }
            isUpdating = false
        }
    }

    fun refreshPrices() {
        scope.launch {
            isUpdating = true
            val usdRate = priceCache.prices["USD"] ?: 32.5
            val fresh = SavingsPriceService.fetchPrices(records, usdRate)
            if (fresh.isNotEmpty()) {
                manager.savePriceCache(fresh)
                priceCache = manager.loadPriceCache()
            }
            isUpdating = false
        }
    }

    val allRecords   = records
    val totalValue   = manager.totalValueTry(allRecords, priceCache)
    val totalCost    = manager.totalCostTry(allRecords)
    val totalProfit  = totalValue - totalCost
    val profitPct    = if (totalCost > 0) (totalProfit / totalCost) * 100.0 else 0.0
    val moodEmoji    = when {
        totalProfit > 0  -> "\uD83D\uDE0A"
        totalProfit < 0  -> "\uD83D\uDE22"
        else             -> "\uD83D\uDE10"
    }

    Column(modifier = Modifier.fillMaxSize()) {

        // ── Ozet kart ──────────────────────────────────────────────────
        Card(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            elevation = CardDefaults.cardElevation(3.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(moodEmoji, fontSize = 32.sp)
                    Spacer(Modifier.width(12.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Toplam Birikim", fontSize = 12.sp, color = colors.textSecondary)
                        Text("${formatMoney(totalValue)} TL",
                            fontSize = 20.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary)
                    }
                    // Guncelle butonu
                    IconButton(onClick = {
                        if (isAdFree) {
                            // Reklamsız modda direkt yenile
                            refreshPrices()
                        } else {
                            UnityAdsManager.showRewarded(
                                activity = context as Activity,
                                onRewarded = { refreshPrices() },
                                onNotReady = { showAdSnack = true }
                            )
                        }
                    }) {
                        if (isUpdating)
                            CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp, color = PurplePrimary)
                        else
                            Icon(Icons.Default.Refresh, null, tint = PurplePrimary)
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    Column {
                        Text("Maliyet", fontSize = 11.sp, color = colors.textSecondary)
                        Text("${formatMoney(totalCost)} TL", fontSize = 13.sp, color = colors.textPrimary)
                    }
                    Column {
                        Text("Kar/Zarar", fontSize = 11.sp, color = colors.textSecondary)
                        Text(
                            "${if (totalProfit >= 0) "+" else ""}${formatMoney(totalProfit)} TL  (%${"%.1f".format(profitPct)})",
                            fontSize = 13.sp, fontWeight = FontWeight.Bold,
                            color = if (totalProfit >= 0) colors.success else colors.error
                        )
                    }
                }

                // Basit bar grafik
                if (allRecords.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    MiniBarChart(records = allRecords, cache = priceCache, manager = manager, colors = colors)
                }
            }
        }

        // ── Sekmeler ────────────────────────────────────────────────────
        TabRow(
            selectedTabIndex = selectedTab,
            containerColor = colors.cardBg,
            contentColor = PurplePrimary,
            modifier = Modifier.padding(horizontal = 16.dp)
        ) {
            tabs.forEachIndexed { i, (cat, emoji) ->
                Tab(
                    selected = selectedTab == i,
                    onClick = { selectedTab = i },
                    text = {
                        Text("$emoji ${cat.label}", fontSize = 12.sp,
                            color = if (selectedTab == i) PurplePrimary else colors.textSecondary)
                    }
                )
            }
        }

        // ── Sekme icerigi ───────────────────────────────────────────────
        val currentCat = tabs[selectedTab].first
        val catRecords = allRecords.filter { it.category == currentCat }

        Box(modifier = Modifier.weight(1f)) {
            if (catRecords.isEmpty()) {
                Column(
                    modifier = Modifier.fillMaxSize(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Text(tabs[selectedTab].second, fontSize = 48.sp)
                    Spacer(Modifier.height(12.dp))
                    Text("Henuz ${currentCat.label} kaydi yok",
                        fontSize = 14.sp, color = colors.textSecondary)
                    Spacer(Modifier.height(8.dp))
                    TextButton(onClick = { editRecord = null; showAddDialog = true }) {
                        Text("+ Ekle", color = PurplePrimary)
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Kategori toplami
                    item {
                        val catValue  = manager.totalValueTry(catRecords, priceCache)
                        val catCost   = manager.totalCostTry(catRecords)
                        val catProfit = catValue - catCost
                        Row(
                            modifier = Modifier.fillMaxWidth()
                                .background(PurplePrimary.copy(alpha = 0.07f), RoundedCornerShape(12.dp))
                                .padding(horizontal = 12.dp, vertical = 8.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("Toplam: ${formatMoney(catValue)} TL",
                                fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary)
                            Text(
                                "${if (catProfit >= 0) "+" else ""}${formatMoney(catProfit)} TL",
                                fontSize = 13.sp, fontWeight = FontWeight.Bold,
                                color = if (catProfit >= 0) colors.success else colors.error
                            )
                        }
                    }
                    items(catRecords, key = { it.id }) { rec ->
                        SavingsRecordCard(
                            record   = rec,
                            cache    = priceCache,
                            manager  = manager,
                            colors   = colors,
                            onEdit   = { editRecord = rec; showAddDialog = true },
                            onDelete = {
                                manager.delete(rec.id)
                                records = manager.loadAll()
                            },
                            onTap    = { detailRecord = rec }
                        )
                    }
                    item { Spacer(Modifier.height(80.dp)) }
                }
            }

            // FAB
            FloatingActionButton(
                onClick = { editRecord = null; showAddDialog = true },
                modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
                containerColor = PurplePrimary, contentColor = Color.White,
                shape = CircleShape
            ) { Icon(Icons.Default.Add, null) }
        }
    }

    // ── Add/Edit Dialog ──────────────────────────────────────────────
    if (showAddDialog) {
        SavingsAddDialog(
            existing    = editRecord,
            category    = tabs[selectedTab].first,
            priceCache  = priceCache,
            onDismiss   = { showAddDialog = false; editRecord = null },
            onSave      = { rec ->
                if (editRecord != null) manager.update(rec) else manager.add(rec)
                records = manager.loadAll()
                // Yeni kayit sonrasi tum fiyatlari yenile
                scope.launch {
                    isUpdating = true
                    val usdRate = priceCache.prices["USD"] ?: 32.5
                    // Önce tek fiyatı hemen al
                    val price = SavingsPriceService.fetchSinglePrice(rec.assetId, rec.category, usdRate)
                    if (price > 0) {
                        val newPrices = priceCache.prices.toMutableMap()
                        newPrices[rec.assetId] = price
                        manager.savePriceCache(newPrices)
                        priceCache = manager.loadPriceCache()
                    }
                    // Sonra tüm kayitlarin fiyatini da tazele
                    val allRecords = manager.loadAll()
                    if (allRecords.isNotEmpty()) {
                        val fresh = SavingsPriceService.fetchPrices(allRecords, usdRate)
                        if (fresh.isNotEmpty()) {
                            manager.savePriceCache(fresh)
                            priceCache = manager.loadPriceCache()
                        }
                    }
                    isUpdating = false
                }
                showAddDialog = false; editRecord = null
            }
        )
    }

    // ── Detay Dialog ──────────────────────────────────────────────────
    detailRecord?.let { rec ->
        SavingsDetailDialog(
            record  = rec,
            cache   = priceCache,
            manager = manager,
            colors  = colors,
            onDismiss = { detailRecord = null }
        )
    }

    // ── Snackbar - reklam hazir degil ─────────────────────────────────
    if (showAdSnack) {
        LaunchedEffect(Unit) {
            kotlinx.coroutines.delay(2500)
            showAdSnack = false
        }
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.BottomCenter) {
            Snackbar(modifier = Modifier.padding(16.dp)) {
                Text("Reklam yuklenemedi. Birazdan tekrar deneyin.")
            }
        }
    }
}

// ── Kayıt Kartı ───────────────────────────────────────────────────────
@Composable
private fun SavingsRecordCard(
    record:   SavingsRecord,
    cache:    PriceCache,
    manager:  SavingsManager,
    colors:   AppColors,
    onEdit:   () -> Unit,
    onDelete: () -> Unit,
    onTap:    () -> Unit
) {
    val currentVal = manager.currentValueTry(record, cache)
    val profit     = manager.profitTry(record, cache)
    val profitPct  = manager.profitPct(record, cache)
    val fmt        = SimpleDateFormat("dd.MM.yyyy", Locale.getDefault())
    var showConfirm by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier.fillMaxWidth().clickable { onTap() },
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
        elevation = CardDefaults.cardElevation(2.dp)
    ) {
        Row(modifier = Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            // Kategori emoji
            Box(
                modifier = Modifier.size(42.dp)
                    .background(PurplePrimary.copy(alpha = 0.12f), RoundedCornerShape(12.dp)),
                contentAlignment = Alignment.Center
            ) { Text(record.category.emoji, fontSize = 20.sp) }

            Spacer(Modifier.width(12.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(record.assetName, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary)
                Text("${formatNumber(record.quantity)} adet  •  ${fmt.format(Date(record.buyDate))}",
                    fontSize = 11.sp, color = colors.textSecondary)
                Text("Maliyet: ${formatMoney(record.totalCostTry())} TL",
                    fontSize = 11.sp, color = colors.textSecondary)
            }

            Column(horizontalAlignment = Alignment.End) {
                Text("${formatMoney(currentVal)} TL",
                    fontWeight = FontWeight.Bold, fontSize = 13.sp, color = colors.textPrimary)
                val profitStr = "${if (profit >= 0) "+" else ""}${formatMoney(profit)} TL"
                Text(profitStr, fontSize = 11.sp,
                    color = if (profit >= 0) colors.success else colors.error)
                Text("(%${"%.1f".format(profitPct)})", fontSize = 10.sp,
                    color = if (profit >= 0) colors.success else colors.error)
            }

            Spacer(Modifier.width(4.dp))
            Column {
                IconButton(onClick = onEdit, modifier = Modifier.size(30.dp)) {
                    Icon(Icons.Default.Edit, null, tint = colors.info, modifier = Modifier.size(16.dp))
                }
                IconButton(onClick = { showConfirm = true }, modifier = Modifier.size(30.dp)) {
                    Icon(Icons.Default.Delete, null, tint = colors.error, modifier = Modifier.size(16.dp))
                }
            }
        }
    }

    if (showConfirm) {
        AlertDialog(
            onDismissRequest = { showConfirm = false },
            title = { Text("Sil") },
            text  = { Text("${record.assetName} kaydini silmek istediginize emin misiniz?") },
            confirmButton = {
                TextButton(onClick = { onDelete(); showConfirm = false }) { Text("Sil", color = colors.error) }
            },
            dismissButton = {
                TextButton(onClick = { showConfirm = false }) { Text("Iptal") }
            }
        )
    }
}

// ── Mini Bar Grafik ───────────────────────────────────────────────────
@Composable
private fun MiniBarChart(
    records: List<SavingsRecord>,
    cache:   PriceCache,
    manager: SavingsManager,
    colors:  AppColors
) {
    val catData = SavingsCategory.values().map { cat ->
        val recs = records.filter { it.category == cat }
        Triple(cat, manager.totalValueTry(recs, cache), manager.totalCostTry(recs))
    }.filter { it.second > 0 }

    if (catData.isEmpty()) return

    val maxVal = catData.maxOf { it.second }
    val barColors = listOf(PurplePrimary, Color(0xFFFF9800), Color(0xFF4CAF50))

    Row(
        modifier = Modifier.fillMaxWidth().height(60.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.Bottom
    ) {
        catData.forEachIndexed { i, (cat, value, cost) ->
            val pct    = (value / maxVal).toFloat().coerceIn(0.1f, 1f)
            val profit = value - cost
            Column(
                modifier = Modifier.weight(1f),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    "${if (profit >= 0) "+" else ""}${formatMoney(profit)}",
                    fontSize = 9.sp,
                    color = if (profit >= 0) colors.success else colors.error,
                    maxLines = 1
                )
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .fillMaxHeight(pct)
                        .background(barColors[i % barColors.size], RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp))
                )
                Text(cat.emoji, fontSize = 12.sp)
            }
        }
    }
}

// ── Add/Edit Dialog ───────────────────────────────────────────────────
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SavingsAddDialog(
    existing:   SavingsRecord?,
    category:   SavingsCategory,
    priceCache: PriceCache,
    onDismiss:  () -> Unit,
    onSave:     (SavingsRecord) -> Unit
) {
    val context = LocalContext.current
    val colors  = LocalAppColors.current
    val scope   = rememberCoroutineScope()

    var assetId    by remember { mutableStateOf(existing?.assetId ?: "") }
    var assetName  by remember { mutableStateOf(existing?.assetName ?: "") }
    var quantity   by remember { mutableStateOf(if ((existing?.quantity ?: 0.0) > 0) existing!!.quantity.toString() else "") }
    var buyPrice   by remember { mutableStateOf(if ((existing?.buyPriceTry ?: 0.0) > 0) existing!!.buyPriceTry.toInt().toString() else "") }
    var note       by remember { mutableStateOf(existing?.note ?: "") }
    var currentPriceHint by remember { mutableStateOf("") }
    var isLoadingPrice   by remember { mutableStateOf(false) }

    // Asset secimi icin dropdown
    var assetExpanded by remember { mutableStateOf(false) }
    var showCoinSearch by remember { mutableStateOf(false) }
    var coinSearchQuery by remember { mutableStateOf("") }
    var coinSearchResults by remember { mutableStateOf<List<Pair<String,String>>>(emptyList()) }
    var coinSearchLoading by remember { mutableStateOf(false) }
    var coinSearchError by remember { mutableStateOf("") }
    val assetOptions: List<Pair<String, String>> = when (category) {
        SavingsCategory.CRYPTO -> KnownCoins.list
        SavingsCategory.METAL  -> KnownMetals.list
        SavingsCategory.DOVIZ  -> KnownCurrencies.list.map { it.first to it.second }
    }

    // Secilen asset'in anlık fiyatını goster
    fun loadCurrentPrice() {
        if (assetId.isBlank()) return
        scope.launch {
            isLoadingPrice = true
            val usdRate = priceCache.prices["USD"] ?: 32.5
            val price = SavingsPriceService.fetchSinglePrice(assetId, category, usdRate)
            currentPriceHint = if (price > 0) "Anlık: ${formatMoney(price)} TL" else "Fiyat alinamadi"
            if (price > 0 && buyPrice.isBlank()) buyPrice = price.toInt().toString()
            isLoadingPrice = false
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
                Text(
                    if (existing == null) "${category.emoji} ${category.label} Ekle"
                    else "${category.emoji} Duzenle",
                    fontWeight = FontWeight.Bold, fontSize = 17.sp, color = colors.textPrimary
                )

                // Asset dropdown
                ExposedDropdownMenuBox(expanded = assetExpanded, onExpandedChange = { assetExpanded = it }) {
                    OutlinedTextField(
                        value = if (assetName.isNotBlank()) assetName else "Seciniz",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text(when (category) {
                            SavingsCategory.CRYPTO -> "Kripto Para"
                            SavingsCategory.METAL  -> "Metal"
                            SavingsCategory.DOVIZ  -> "Doviz"
                        }) },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(assetExpanded) },
                        modifier = Modifier.fillMaxWidth().menuAnchor(),
                        shape = RoundedCornerShape(12.dp)
                    )
                    ExposedDropdownMenu(expanded = assetExpanded, onDismissRequest = { assetExpanded = false }) {
                        assetOptions.forEach { (id, label) ->
                            DropdownMenuItem(
                                text = { Text("$id — $label") },
                                onClick = {
                                    assetId   = id
                                    assetName = when (category) {
                                        SavingsCategory.CRYPTO -> KnownCoins.symbolOf(id)
                                        SavingsCategory.METAL  -> label
                                        SavingsCategory.DOVIZ  -> id
                                    }
                                    assetExpanded = false
                                    loadCurrentPrice()
                                }
                            )
                        }
                        // Listede olmayan coin arama
                        if (category == SavingsCategory.CRYPTO) {
                            HorizontalDivider()
                            DropdownMenuItem(
                                text = {
                                    Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                                        Icon(Icons.Default.Search, null,
                                            modifier = Modifier.size(16.dp),
                                            tint = MaterialTheme.colorScheme.primary)
                                        Spacer(Modifier.width(8.dp))
                                        Text("Listede yok? Ara...",
                                            color = MaterialTheme.colorScheme.primary,
                                            fontWeight = FontWeight.Bold)
                                    }
                                },
                                onClick = {
                                    assetExpanded = false
                                    coinSearchQuery = ""
                                    coinSearchResults = emptyList()
                                    coinSearchError = ""
                                    showCoinSearch = true
                                }
                            )
                        }
                    }
                }

    if (showCoinSearch) {
        val searchScope = rememberCoroutineScope()
        CoinSearchDialog(
            query = coinSearchQuery,
            onQueryChange = { coinSearchQuery = it },
            results = coinSearchResults,
            isLoading = coinSearchLoading,
            error = coinSearchError,
            onSearch = {
                if (coinSearchQuery.isBlank()) return@CoinSearchDialog
                coinSearchLoading = true
                coinSearchError = ""
                coinSearchResults = emptyList()
                searchScope.launch {
                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                        try {
                            val url = "https://api.coingecko.com/api/v3/search?query=${coinSearchQuery.trim()}"
                            val json = org.json.JSONObject(java.net.URL(url).readText())
                            val coins = json.getJSONArray("coins")
                            val found = mutableListOf<Pair<String,String>>()
                            for (i in 0 until minOf(coins.length(), 6)) {
                                val c = coins.getJSONObject(i)
                                found.add(c.getString("id") to "${c.getString("symbol").uppercase()} — ${c.getString("name")}")
                            }
                            coinSearchResults = found
                            if (found.isEmpty()) coinSearchError = "Sonuc bulunamadi"
                        } catch (_: Exception) { coinSearchError = "Arama basarisiz" }
                        coinSearchLoading = false
                    }
                }
            },
            onSelect = { id, label ->
                assetId   = id
                assetName = label.substringBefore(" —").trim()
                showCoinSearch = false
                loadCurrentPrice()
            },
            onDismiss = { showCoinSearch = false }
        )
    }
                // Anlık fiyat hint
                if (isLoadingPrice) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp, color = PurplePrimary)
                        Spacer(Modifier.width(6.dp))
                        Text("Fiyat aliyor...", fontSize = 11.sp, color = colors.textSecondary)
                    }
                } else if (currentPriceHint.isNotBlank()) {
                    Text(currentPriceHint, fontSize = 11.sp, color = colors.info)
                }

                CurrencyField(
                    value = quantity,
                    onValueChange = { quantity = it },
                    label = when (category) {
                        SavingsCategory.CRYPTO -> "Miktar (adet)"
                        SavingsCategory.METAL  -> "Miktar (gram)"
                        SavingsCategory.DOVIZ  -> "Miktar (birim)"
                    },
                    isQuantity = category != SavingsCategory.DOVIZ
                )

                CurrencyField(value = buyPrice, onValueChange = { buyPrice = it },
                    label = "Alim Fiyati (TL/birim)")

                OutlinedTextField(
                    value = note, onValueChange = { note = it },
                    label = { Text("Not (opsiyonel)") },
                    singleLine = true, modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp)
                )

                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(onClick = onDismiss, modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)) { Text("Iptal") }
                    Button(
                        onClick = {
                            val rec = (existing ?: SavingsRecord()).copy(
                                category    = category,
                                assetId     = assetId,
                                assetName   = assetName,
                                quantity    = quantity.toDoubleOrNull() ?: 0.0,
                                buyPriceTry = buyPrice.toDoubleOrNull() ?: 0.0,
                                note        = note.trim()
                            )
                            onSave(rec)
                        },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PurplePrimary),
                        enabled = assetId.isNotBlank() && quantity.isNotBlank() && buyPrice.isNotBlank()
                    ) { Text("Kaydet", fontWeight = FontWeight.Bold) }
                }
            }
        }
    }
}

// ── Detay Dialog ──────────────────────────────────────────────────────
@Composable
private fun SavingsDetailDialog(
    record:    SavingsRecord,
    cache:     PriceCache,
    manager:   SavingsManager,
    colors:    AppColors,
    onDismiss: () -> Unit
) {
    val currentVal = manager.currentValueTry(record, cache)
    val profit     = manager.profitTry(record, cache)
    val profitPct  = manager.profitPct(record, cache)
    val currentPrice = if (record.quantity > 0) currentVal / record.quantity else 0.0
    val fmt = SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.getDefault())

    Dialog(onDismissRequest = onDismiss) {
        Card(shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            elevation = CardDefaults.cardElevation(8.dp)) {
            Column(modifier = Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(record.category.emoji, fontSize = 24.sp)
                    Spacer(Modifier.width(8.dp))
                    Text(record.assetName, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = colors.textPrimary)
                }
                HorizontalDivider(color = PurplePrimary.copy(alpha = 0.15f))
                DetailRow("Miktar",        "${formatNumber(record.quantity)} birim", colors)
                DetailRow("Alim Fiyati",   "${formatMoney(record.buyPriceTry)} TL", colors)
                DetailRow("Toplam Maliyet","${formatMoney(record.totalCostTry())} TL", colors)
                DetailRow("Anlık Fiyat",   "${formatMoney(currentPrice)} TL", colors)
                DetailRow("Guncel Deger",  "${formatMoney(currentVal)} TL", colors)
                HorizontalDivider(color = PurplePrimary.copy(alpha = 0.15f))
                DetailRow(
                    "Kar / Zarar",
                    "${if (profit >= 0) "+" else ""}${formatMoney(profit)} TL  (%${"%.2f".format(profitPct)})",
                    colors,
                    valueColor = if (profit >= 0) colors.success else colors.error
                )
                DetailRow("Tarih", fmt.format(Date(record.buyDate)), colors)
                if (record.note.isNotBlank()) DetailRow("Not", record.note, colors)
                TextButton(onClick = onDismiss, modifier = Modifier.align(Alignment.End)) { Text("Kapat") }
            }
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String, colors: AppColors, valueColor: Color = Color.Unspecified) {
    Row(modifier = Modifier.fillMaxWidth()) {
        Text(label, fontSize = 13.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
        Text(value, fontSize = 13.sp, fontWeight = FontWeight.Medium,
            color = if (valueColor == Color.Unspecified) colors.textPrimary else valueColor,
            textAlign = TextAlign.End)
    }
}

// ── Coin Arama Dialog ────────────────────────────────────────────
@Composable
fun CoinSearchDialog(
    query: String,
    onQueryChange: (String) -> Unit,
    results: List<Pair<String, String>>,
    isLoading: Boolean,
    error: String,
    onSearch: () -> Unit,
    onSelect: (String, String) -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Kripto Ara") },
        text = {
            Column(verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = query,
                    onValueChange = onQueryChange,
                    label = { Text("Coin adı veya sembol") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    trailingIcon = {
                        IconButton(onClick = onSearch) {
                            Icon(Icons.Default.Search, null)
                        }
                    }
                )
                if (isLoading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                if (error.isNotEmpty()) Text(error, color = androidx.compose.ui.graphics.Color.Red, fontSize = 12.sp)
                results.forEach { (id, name) ->
                    androidx.compose.material3.Card(
                        modifier = Modifier.fillMaxWidth().clickable { onSelect(id, name) },
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Row(modifier = Modifier.padding(10.dp).fillMaxWidth(),
                            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(name, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                Text(id, fontSize = 11.sp, color = androidx.compose.ui.graphics.Color.Gray)
                            }
                            Icon(Icons.Default.Add, null, tint = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onSearch) { Text("Ara") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Kapat") } }
    )
}
