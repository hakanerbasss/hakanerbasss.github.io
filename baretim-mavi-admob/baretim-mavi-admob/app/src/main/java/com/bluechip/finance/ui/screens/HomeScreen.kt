package com.bluechip.finance.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.*
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.border
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.bluechip.finance.data.Article
import com.bluechip.finance.data.PaymentManager
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.util.getMoodInfo
import com.bluechip.finance.data.NewsApiService
import com.bluechip.finance.ui.components.TipCard
import com.bluechip.finance.data.SpecialDayManager
import com.bluechip.finance.data.HolidayManager
import com.bluechip.finance.data.PublicHoliday
import com.bluechip.finance.data.SpecialDay
import com.bluechip.finance.ui.components.formatMoney
import com.bluechip.finance.ui.components.formatNumber
import com.bluechip.finance.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.URL
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun HomeScreen(onNavigate: (String) -> Unit) {
    val context = LocalContext.current
    val colors  = LocalAppColors.current

    var usdRate    by remember { mutableDoubleStateOf(0.0) }
    var eurRate    by remember { mutableDoubleStateOf(0.0) }
    var goldUSD    by remember { mutableDoubleStateOf(0.0) }
    var btcUSD     by remember { mutableDoubleStateOf(0.0) }
    var ethUSD     by remember { mutableDoubleStateOf(0.0) }
    var isTL       by remember { mutableStateOf(true) }
    var updateTime by remember { mutableStateOf("") }
    var isLoading  by remember { mutableStateOf(true) }
    var marketExpanded by remember { mutableStateOf(true) }

    // Özel kripto listesi — SharedPreferences'tan yükle
    val cryptoPrefs = remember { context.getSharedPreferences("custom_cryptos", android.content.Context.MODE_PRIVATE) }
    var customCryptos by remember {
        val saved = cryptoPrefs.getStringSet("ids", emptySet()) ?: emptySet()
        val savedNames = saved.map { id ->
            Triple(id, cryptoPrefs.getString("name_$id", id.uppercase()) ?: id.uppercase(), cryptoPrefs.getInt("color_$id", 0xFF9C27B0.toInt()))
        }
        mutableStateOf(savedNames)
    }
    var customPrices by remember { mutableStateOf<Map<String, Double>>(emptyMap()) }
    var showCryptoSearch by remember { mutableStateOf(false) }
    var cryptoSearchQuery by remember { mutableStateOf("") }
    var cryptoSearchResults by remember { mutableStateOf<List<Triple<String, String, String>>>(emptyList()) }
    var cryptoSearchLoading by remember { mutableStateOf(false) }
    var cryptoSearchError by remember { mutableStateOf("") }

    var articles    by remember { mutableStateOf<List<Article>>(emptyList()) }
    var newsStatus  by remember { mutableStateOf("Haberler yukleniyor...") }
    var showAllNews by remember { mutableStateOf(false) }
    val pagerState  = rememberPagerState(pageCount = { 2 })
    val coroutineScope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            try {
                val tcmb = URL("https://www.tcmb.gov.tr/kurlar/today.xml").readText()
                val usdMatch = Regex("<Currency[^>]*CurrencyCode=\"USD\"[^>]*>.*?<ForexSelling>([0-9.]+)</ForexSelling>", RegexOption.DOT_MATCHES_ALL).find(tcmb)
                val eurMatch = Regex("<Currency[^>]*CurrencyCode=\"EUR\"[^>]*>.*?<ForexSelling>([0-9.]+)</ForexSelling>", RegexOption.DOT_MATCHES_ALL).find(tcmb)
                if (usdMatch != null) usdRate = usdMatch.groupValues[1].toDouble()
                if (eurMatch != null) eurRate = eurMatch.groupValues[1].toDouble()
            } catch (_: Exception) { usdRate = 32.5; eurRate = 35.2 }
            try {
                val crypto = URL("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether-gold&vs_currencies=usd").readText()
                val json = JSONObject(crypto)
                btcUSD  = json.getJSONObject("bitcoin").getDouble("usd")
                ethUSD  = json.getJSONObject("ethereum").getDouble("usd")
                goldUSD = json.getJSONObject("tether-gold").getDouble("usd")
            } catch (_: Exception) { btcUSD = 64200.0; ethUSD = 3100.0; goldUSD = 2650.0 }
            isLoading  = false
            updateTime = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
        }
        // Özel kripto fiyatları
        if (customCryptos.isNotEmpty()) {
            withContext(Dispatchers.IO) {
                try {
                    val ids = customCryptos.joinToString(",") { it.first }
                    val url = "https://api.coingecko.com/api/v3/simple/price?ids=$ids&vs_currencies=usd"
                    val json = JSONObject(URL(url).readText())
                    val prices = mutableMapOf<String, Double>()
                    customCryptos.forEach { (id, _, _) ->
                        if (json.has(id)) prices[id] = json.getJSONObject(id).getDouble("usd")
                    }
                    customPrices = prices
                } catch (_: Exception) {}
            }
        }

        withContext(Dispatchers.IO) {
            try {
                val response = NewsApiService.instance.getNews()
                articles    = response.articles.take(6)
                newsStatus  = "Son guncelleme: ${SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())}"
            } catch (_: Exception) { newsStatus = "Haber yuklenemedi" }
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {

        // ── Sekme Bar ───────────────────────────────────────────
        val tabTitles = listOf("Profil", "Keşfet")
        TabRow(
            selectedTabIndex = pagerState.currentPage,
            containerColor = colors.cardBg,
            contentColor = com.bluechip.finance.ui.theme.PurplePrimary,
            modifier = Modifier.clip(RoundedCornerShape(12.dp))
        ) {
            tabTitles.forEachIndexed { i, title ->
                Tab(
                    selected = pagerState.currentPage == i,
                    onClick = { coroutineScope.launch { pagerState.animateScrollToPage(i) } },
                    text = { Text(title, fontSize = 14.sp, fontWeight = FontWeight.Medium) },
                    icon = {
                        Icon(
                            if (i == 0) Icons.Default.Person else Icons.Default.Explore,
                            contentDescription = null, modifier = Modifier.size(18.dp)
                        )
                    }
                )
            }
        }

        HorizontalPager(
            state = pagerState,
            modifier = Modifier.fillMaxWidth()
        ) { page ->
            Column(
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
            when (page) {
                0 -> {
                    // ── Profil Sekmesi ─────────────────────────────────
                    SalaryCard(context, onNavigate)
                    UpcomingPaymentsCard(context = context, onNavigate = onNavigate)
                    SavingsHomeCard(context = context, onNavigate = onNavigate)
                    OvertimeHomeCard(context = context, onNavigate = onNavigate)
                    UpcomingSpecialDaysCard(context = context, onNavigate = onNavigate)
                }
                1 -> {
                    // ── Kesfet Sekmesi ─────────────────────────────────
        // ── 1. Piyasa Karti (Collapsible) ────────────────────────
        Card(
            shape  = RoundedCornerShape(16.dp),
            elevation = CardDefaults.cardElevation(4.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {

                // Baslik + toggle
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { marketExpanded = !marketExpanded },
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(Icons.Default.TrendingUp, null,
                        tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(8.dp))
                    Text("Piyasa Verileri",
                        fontWeight = FontWeight.Bold, fontSize = 16.sp,
                        color = colors.textPrimary, modifier = Modifier.weight(1f))
                    if (updateTime.isNotEmpty()) {
                        Text(updateTime, fontSize = 10.sp, color = colors.textSecondary)
                        Spacer(Modifier.width(4.dp))
                    }
                    // Kripto ekle butonu
                    IconButton(
                        onClick = { showCryptoSearch = true; cryptoSearchQuery = ""; cryptoSearchResults = emptyList(); cryptoSearchError = "" },
                        modifier = Modifier.size(32.dp)
                    ) {
                        Icon(Icons.Default.Add, "Kripto Ekle",
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(20.dp))
                    }
                    Icon(
                        if (marketExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        null, tint = colors.textSecondary, modifier = Modifier.size(20.dp)
                    )
                }

                // TL/USD toggle → küçük pill
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(
                        modifier = Modifier
                            .background(
                                MaterialTheme.colorScheme.primary.copy(alpha = 0.1f),
                                androidx.compose.foundation.shape.RoundedCornerShape(20.dp)
                            )
                            .padding(2.dp)
                    ) {
                        listOf("TL", "USD").forEach { label ->
                            val selected = (label == "TL") == isTL
                            Box(
                                modifier = Modifier
                                    .background(
                                        if (selected) MaterialTheme.colorScheme.primary
                                        else androidx.compose.ui.graphics.Color.Transparent,
                                        androidx.compose.foundation.shape.RoundedCornerShape(18.dp)
                                    )
                                    .clickable { isTL = (label == "TL") }
                                    .padding(horizontal = 14.dp, vertical = 4.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(label, fontSize = 12.sp, fontWeight = FontWeight.Bold,
                                    color = if (selected) androidx.compose.ui.graphics.Color.White
                                            else colors.textSecondary)
                            }
                        }
                    }
                }

                // Animasyonlu icerik
                AnimatedVisibility(
                    visible = marketExpanded,
                    enter = expandVertically() + fadeIn(),
                    exit  = shrinkVertically() + fadeOut()
                ) {
                    Column {
                        Spacer(Modifier.height(8.dp))
                        if (isLoading) {
                            // Skeleton loader
                            SkeletonLoader()
                        } else {
                            val s = if (isTL) "TL" else "$"
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceEvenly
                            ) {
                                PriceChip("USD",  "${formatMoney(if (isTL) usdRate else 1.0)}$s",            Color(0xFF4CAF50))
                                PriceChip("EUR",  "${formatMoney(if (isTL) eurRate else eurRate/usdRate)}$s", Color(0xFF2196F3))
                                PriceChip("Altin","${formatMoney(if (isTL) goldUSD*usdRate else goldUSD)}$s", Color(0xFFFF9800))
                            }
                            Spacer(Modifier.height(8.dp))
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceEvenly
                            ) {
                                PriceChip("BTC", "${formatNumber(if (isTL) btcUSD*usdRate else btcUSD)}$s", Color(0xFFF7931A))
                                PriceChip("ETH", "${formatNumber(if (isTL) ethUSD*usdRate else ethUSD)}$s", Color(0xFF627EEA))
                            }

                            // Özel kriptolar
                            if (customCryptos.isNotEmpty()) {
                                Spacer(Modifier.height(6.dp))
                                customCryptos.chunked(3).forEach { row ->
                                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                                        row.forEach { (id, symbol, colorInt) ->
                                            val price = customPrices[id] ?: 0.0
                                            val priceStr = if (price > 1) formatNumber(if (isTL) price * usdRate else price)
                                                           else String.format("%.6f", if (isTL) price * usdRate else price)
                                            CustomCryptoChip(
                                                name = symbol,
                                                price = "$priceStr$s",
                                                color = Color(colorInt),
                                                onLongClick = {
                                                    // Sil
                                                    customCryptos = customCryptos.filter { it.first != id }
                                                    cryptoPrefs.edit()
                                                        .putStringSet("ids", customCryptos.map { it.first }.toSet())
                                                        .remove("name_$id")
                                                        .remove("color_$id")
                                                        .apply()
                                                }
                                            )
                                        }
                                        // Boş hücre dolgu
                                        repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                                    }
                                }
                                Spacer(Modifier.height(4.dp))
                                Text("Uzun bas → sil", fontSize = 9.sp, color = colors.textSecondary,
                                    modifier = Modifier.fillMaxWidth(),
                                    textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                            }
                        }
                    }
                }
            }
        }

        // ── 2. Bilgi Karti ───────────────────────────────────────
        TipCard()

        // ── 3. Ekonomi Haberleri ─────────────────────────────────
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(Icons.Default.Newspaper, null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(6.dp))
            Text("Ekonomi Haberleri",
                fontWeight = FontWeight.Bold, fontSize = 16.sp,
                color = colors.textPrimary, modifier = Modifier.weight(1f))
            Text(newsStatus, fontSize = 10.sp, color = colors.textSecondary)
        }

        val visibleArticles = if (showAllNews) articles else articles.take(3)

        visibleArticles.forEach { article ->
            Card(
                modifier = Modifier.fillMaxWidth().clickable {
                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(article.url)))
                },
                shape  = RoundedCornerShape(12.dp),
                elevation = CardDefaults.cardElevation(2.dp),
                colors = CardDefaults.cardColors(containerColor = colors.cardBg)
            ) {
                Column {
                    if (!article.urlToImage.isNullOrEmpty() && article.urlToImage != "null") {
                        AsyncImage(
                            model = article.urlToImage, contentDescription = null,
                            modifier = Modifier
                                .fillMaxWidth().height(160.dp)
                                .clip(RoundedCornerShape(topStart = 12.dp, topEnd = 12.dp)),
                            contentScale = ContentScale.Crop
                        )
                    }
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(article.title,
                            fontWeight = FontWeight.Bold, fontSize = 14.sp,
                            color = colors.textPrimary, maxLines = 2,
                            overflow = TextOverflow.Ellipsis)
                        Spacer(Modifier.height(4.dp))
                        Text(article.description ?: "Detaylar icin tiklayin",
                            fontSize = 12.sp, color = colors.info, maxLines = 2)
                    }
                }
            }
        }

        // "Daha Fazla / Daha Az" butonu
        if (articles.size > 3) {
            OutlinedButton(
                onClick = { showAllNews = !showAllNews },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp)
            ) {
                Icon(
                    if (showAllNews) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    null, modifier = Modifier.size(16.dp)
                )
                Spacer(Modifier.width(6.dp))
                Text(if (showAllNews) "Daha Az Goster" else "Daha Fazla Haber")
            }
        }

        Spacer(Modifier.height(8.dp))
                } // end when page 1
            } // end when
            } // end inner Column
        } // end HorizontalPager

        Spacer(Modifier.height(8.dp))
    }

    // ── Kripto Arama Diyaloğu ──────────────────────────────────
    if (showCryptoSearch) {
        val scope = rememberCoroutineScope()
        CryptoSearchDialog(
            query = cryptoSearchQuery,
            onQueryChange = { cryptoSearchQuery = it },
            results = cryptoSearchResults,
            isLoading = cryptoSearchLoading,
            error = cryptoSearchError,
            onSearch = {
                if (cryptoSearchQuery.isBlank()) return@CryptoSearchDialog
                cryptoSearchLoading = true
                cryptoSearchError = ""
                cryptoSearchResults = emptyList()
                scope.launch {
                    withContext(Dispatchers.IO) {
                        try {
                            val q = cryptoSearchQuery.trim().lowercase()
                            // Önce hardcoded popüler listede ara
                            val hardcoded = mapOf(
                                "bitcoin" to "BTC", "ethereum" to "ETH",
                                "ripple" to "XRP", "solana" to "SOL",
                                "dogecoin" to "DOGE", "cardano" to "ADA",
                                "polkadot" to "DOT", "chainlink" to "LINK",
                                "litecoin" to "LTC", "avalanche-2" to "AVAX",
                                "binancecoin" to "BNB", "matic-network" to "MATIC",
                                "tron" to "TRX", "stellar" to "XLM",
                                "uniswap" to "UNI", "cosmos" to "ATOM",
                                "near" to "NEAR", "aptos" to "APT",
                                "arbitrum" to "ARB", "optimism" to "OP",
                                "pepe" to "PEPE", "shiba-inu" to "SHIB",
                                "toncoin" to "TON", "sui" to "SUI",
                                "floki" to "FLOKI", "bonk" to "BONK"
                            )
                            val local = hardcoded.filter { (id, sym) ->
                                sym.lowercase().contains(q) || id.contains(q)
                            }.map { (id, sym) ->
                                Triple(id, sym, id.replace("-", " ")
                                    .replaceFirstChar { it.uppercase() })
                            }

                            if (local.isNotEmpty()) {
                                cryptoSearchResults = local.take(5)
                            } else {
                                // CoinGecko search API
                                val url = "https://api.coingecko.com/api/v3/search?query=$q"
                                val json = org.json.JSONObject(URL(url).readText())
                                val coins = json.getJSONArray("coins")
                                val found = mutableListOf<Triple<String, String, String>>()
                                for (i in 0 until minOf(coins.length(), 5)) {
                                    val coin = coins.getJSONObject(i)
                                    found.add(Triple(
                                        coin.getString("id"),
                                        coin.getString("symbol").uppercase(),
                                        coin.getString("name")
                                    ))
                                }
                                cryptoSearchResults = found
                            }
                            if (cryptoSearchResults.isEmpty()) {
                                cryptoSearchError = "Sonuç bulunamadı"
                            }
                        } catch (_: Exception) {
                            cryptoSearchError = "Arama başarısız, internet bağlantısını kontrol edin"
                        }
                        cryptoSearchLoading = false
                    }
                }
            },
            onAdd = { id, symbol ->
                if (customCryptos.any { it.first == id }) {
                    android.widget.Toast.makeText(context,
                        "$symbol zaten ekli", android.widget.Toast.LENGTH_SHORT).show()
                    return@CryptoSearchDialog
                }
                val colorList = listOf(
                    0xFFF7931A, 0xFF627EEA, 0xFF9C27B0, 0xFF00BCD4,
                    0xFF4CAF50, 0xFFE91E63, 0xFFFF5722, 0xFF607D8B
                )
                val color = colorList[customCryptos.size % colorList.size].toInt()
                val newList = customCryptos + Triple(id, symbol, color)
                customCryptos = newList
                cryptoPrefs.edit()
                    .putStringSet("ids", newList.map { it.first }.toSet())
                    .putString("name_$id", symbol)
                    .putInt("color_$id", color)
                    .apply()
                showCryptoSearch = false
                android.widget.Toast.makeText(context,
                    "✅ $symbol eklendi!", android.widget.Toast.LENGTH_SHORT).show()
            },
            onDismiss = { showCryptoSearch = false }
        )
    }
}

// ── Kripto Arama Diyaloğu ────────────────────────────────────────
@Composable
private fun CryptoSearchDialog(
    query: String,
    onQueryChange: (String) -> Unit,
    results: List<Triple<String, String, String>>, // id, symbol, name
    isLoading: Boolean,
    error: String,
    onSearch: () -> Unit,
    onAdd: (String, String) -> Unit, // id, symbol
    onDismiss: () -> Unit
) {
    val colors = LocalAppColors.current
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Kripto Para Ekle") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                // Arama alanı
                OutlinedTextField(
                    value = query,
                    onValueChange = onQueryChange,
                    label = { Text("Kripto adı veya sembol") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp),
                    trailingIcon = {
                        IconButton(onClick = onSearch) {
                            Icon(Icons.Default.Search, null)
                        }
                    }
                )
                Text("BTC, ETH, SOL, XRP, DOGE... gibi sembol veya tam ad girebilirsiniz.",
                    fontSize = 11.sp, color = colors.textSecondary)

                if (isLoading) {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                }
                if (error.isNotEmpty()) {
                    Text(error, fontSize = 12.sp, color = colors.error)
                }

                // Sonuçlar
                results.forEach { (id, symbol, name) ->
                    Card(
                        modifier = Modifier.fillMaxWidth().clickable { onAdd(id, symbol) },
                        shape = RoundedCornerShape(8.dp),
                        colors = CardDefaults.cardColors(containerColor = colors.cardGray)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(symbol.uppercase(), fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary)
                                Text(name, fontSize = 11.sp, color = colors.textSecondary)
                            }
                            Icon(Icons.Default.Add, null, tint = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onSearch) { Text("Ara") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Kapat") }
        }
    )
}

// ── Skeleton Loader ───────────────────────────────────────────────

@Composable
@androidx.compose.foundation.ExperimentalFoundationApi
private fun CustomCryptoChip(name: String, price: String, color: Color, onLongClick: () -> Unit) {
    val colors = LocalAppColors.current
    Column(
        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
        modifier = Modifier.combinedClickable(onClick = {}, onLongClick = onLongClick)
    ) {
        Text(name, fontSize = 11.sp, color = colors.textSecondary)
        Text(price, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = color)
    }
}

@Composable
private fun SkeletonLoader() {
    val colors = LocalAppColors.current
    val shimmer = colors.cardGray
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            repeat(3) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(modifier = Modifier
                        .width(40.dp).height(10.dp)
                        .clip(RoundedCornerShape(4.dp))
                        .background(shimmer))
                    Spacer(Modifier.height(4.dp))
                    Box(modifier = Modifier
                        .width(60.dp).height(14.dp)
                        .clip(RoundedCornerShape(4.dp))
                        .background(shimmer))
                }
            }
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            repeat(2) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(modifier = Modifier
                        .width(40.dp).height(10.dp)
                        .clip(RoundedCornerShape(4.dp))
                        .background(shimmer))
                    Spacer(Modifier.height(4.dp))
                    Box(modifier = Modifier
                        .width(70.dp).height(14.dp)
                        .clip(RoundedCornerShape(4.dp))
                        .background(shimmer))
                }
            }
        }
    }
}

// ── Fiyat Chip ───────────────────────────────────────────────────
@Composable
private fun PriceChip(name: String, price: String, color: Color) {
    val colors = LocalAppColors.current
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(name,  fontSize = 11.sp, color = colors.textSecondary)
        Text(price, fontSize = 14.sp, fontWeight = FontWeight.Bold, color = color)
    }
}


// ── Mood emoji hesaplama ──────────────────────────────────────────
private fun getMoodInfo(
    daysToSalary: Int?,
    daysToAdvance: Int?,
    daysToPayment: Int?,
    dayOfYear: Int
): Pair<String, String> {
    // Avans bugün veya yarın
    if (daysToAdvance != null && daysToAdvance <= 1) {
        val emojis = listOf("😎", "🥳", "🎉", "💸")
        return Pair(emojis[dayOfYear % emojis.size], if (daysToAdvance == 0) "Avans günü!" else "Yarın avans!")
    }
    // Maaş bugün
    if (daysToSalary == 0) return Pair("🤑", "Maaş günü!")
    // Maaş 1 gün
    if (daysToSalary == 1) return Pair("😁", "Yarın maaş!")
    // Maaş 2-3 gün
    if (daysToSalary != null && daysToSalary <= 3) {
        val emojis = listOf("😊", "😄", "🙌", "🤩")
        return Pair(emojis[dayOfYear % emojis.size], "Az kaldı!")
    }
    // Avans 2-5 gün
    if (daysToAdvance != null && daysToAdvance <= 5) {
        val emojis = listOf("🙂", "😌", "😏", "😋")
        return Pair(emojis[dayOfYear % emojis.size], "Avans yaklaşıyor")
    }
    // Yaklaşan ödeme (ve maaş uzak)
    if (daysToPayment != null && daysToPayment <= 3 && (daysToSalary == null || daysToSalary > 5)) {
        val emojis = listOf("😤", "😠", "🤬", "😡")
        return Pair(emojis[dayOfYear % emojis.size], "Ödeme kapıda!")
    }
    if (daysToPayment != null && daysToPayment <= 7 && (daysToSalary == null || daysToSalary > 10)) {
        val emojis = listOf("😑", "😒", "🫠", "😶")
        return Pair(emojis[dayOfYear % emojis.size], "Ödeme geliyor...")
    }
    // Maaş 4-7 gün
    if (daysToSalary != null && daysToSalary <= 7) {
        val emojis = listOf("🙂", "😌", "🫡", "😏")
        return Pair(emojis[dayOfYear % emojis.size], "Yaklaşıyor!")
    }
    // Maaş 8-14 gün
    if (daysToSalary != null && daysToSalary <= 14) {
        val emojis = listOf("😐", "🤔", "😶", "🙄")
        return Pair(emojis[dayOfYear % emojis.size], "Biraz daha sabret")
    }
    // Maaş 15-20 gün
    if (daysToSalary != null && daysToSalary <= 20) {
        val emojis = listOf("😟", "😔", "😩", "😫")
        return Pair(emojis[dayOfYear % emojis.size], "Uzak biraz...")
    }
    // Maaş 21-25 gün
    if (daysToSalary != null && daysToSalary <= 25) {
        val emojis = listOf("😢", "😞", "😓", "😥")
        return Pair(emojis[dayOfYear % emojis.size], "Cüzdan ağlıyor")
    }
    // 26+ gün
    if (daysToSalary != null) {
        val emojis = listOf("😭", "💀", "🥺", "😰")
        return Pair(emojis[dayOfYear % emojis.size], "Çok uzak...")
    }
    return Pair("😊", "İyi günler!")
}

// ── Maaş & Kullanıcı kartı ───────────────────────────────────────
@Composable
private fun SalaryCard(context: android.content.Context, onNavigate: (String) -> Unit) {
    val colors = LocalAppColors.current
    val profile = remember { ProfileManager(context).load() }

    // Profil boşsa → doldur kartı göster
    if (!profile.isLoggedIn) {
        Card(
            shape = RoundedCornerShape(20.dp),
            elevation = CardDefaults.cardElevation(3.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            modifier = Modifier.fillMaxWidth().clickable { onNavigate("profile") }
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    modifier = Modifier.size(48.dp).background(
                        androidx.compose.ui.graphics.Brush.radialGradient(
                            listOf(com.bluechip.finance.ui.theme.PurplePrimaryLight, com.bluechip.finance.ui.theme.PurplePrimary)
                        ),
                        androidx.compose.foundation.shape.CircleShape
                    ),
                    contentAlignment = Alignment.Center
                ) {
                    Text("👤", fontSize = 22.sp)
                }
                Spacer(Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        "Profili Doldurun →",
                        fontWeight = FontWeight.Bold, fontSize = 14.sp,
                        color = com.bluechip.finance.ui.theme.PurplePrimary
                    )
                    Text(
                        "Maaş günü, avans ve daha fazlası için",
                        fontSize = 12.sp, color = colors.textSecondary
                    )
                }
                Icon(
                    Icons.Default.ChevronRight, null,
                    tint = com.bluechip.finance.ui.theme.PurplePrimary,
                    modifier = Modifier.size(20.dp)
                )
            }
        }
        return
    }

    val cal = Calendar.getInstance()
    val today = cal.get(Calendar.DAY_OF_MONTH)
    val dayOfYear = cal.get(Calendar.DAY_OF_YEAR)

    // Maaş gününe kalan
    val salaryDay = profile.salaryDay
    val daysToSalary: Int? = if (salaryDay > 0) {
        when {
            salaryDay >= today -> salaryDay - today
            else -> {
                val nextMonth = Calendar.getInstance().apply { add(Calendar.MONTH, 1) }
                val nextMax = nextMonth.getActualMaximum(Calendar.DAY_OF_MONTH)
                (nextMax - today) + minOf(salaryDay, nextMax)
            }
        }
    } else null

    // Avans gününe kalan
    val advanceDay = profile.advanceDay
    val daysToAdvance: Int? = if (advanceDay > 0) {
        when {
            advanceDay >= today -> advanceDay - today
            else -> {
                val nextMonth = Calendar.getInstance().apply { add(Calendar.MONTH, 1) }
                val nextMax = nextMonth.getActualMaximum(Calendar.DAY_OF_MONTH)
                (nextMax - today) + minOf(advanceDay, nextMax)
            }
        }
    } else null

    // En yakın ödeme
    val nearestPaymentDay = try {
        com.bluechip.finance.data.PaymentManager.getUpcomingThisMonth(context)
            .firstOrNull()?.dueDayOfMonth
            ?.let { day -> day - today }
            ?.takeIf { it >= 0 }
    } catch (_: Exception) { null }

    val (moodEmoji, moodText) = getMoodInfo(daysToSalary, daysToAdvance, nearestPaymentDay, dayOfYear)

    Card(
        shape = RoundedCornerShape(20.dp),
        elevation = CardDefaults.cardElevation(6.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {

            // Gradient Header
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(
                        brush = androidx.compose.ui.graphics.Brush.linearGradient(
                            colors = listOf(
                                com.bluechip.finance.ui.theme.PurplePrimaryDark,
                                com.bluechip.finance.ui.theme.PurplePrimary,
                                com.bluechip.finance.ui.theme.PurplePrimaryLight.copy(alpha = 0.85f)
                            )
                        ),
                        shape = androidx.compose.foundation.shape.RoundedCornerShape(
                            topStart = 20.dp, topEnd = 20.dp
                        )
                    )
                    .clickable { onNavigate("profile") }
                    .padding(horizontal = 16.dp, vertical = 14.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(58.dp)
                            .background(
                                color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.18f),
                                shape = androidx.compose.foundation.shape.CircleShape
                            ),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(moodEmoji, fontSize = 36.sp, lineHeight = 40.sp)
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        if (profile.name.isNotBlank())
                            Text(
                                "Merhaba, ${profile.name.split(" ").first()} 👋",
                                fontWeight = FontWeight.Bold, fontSize = 15.sp,
                                color = androidx.compose.ui.graphics.Color.White
                            )
                        if (profile.netSalary > 0)
                            Text(
                                "Net Maas: ${formatMoney(profile.netSalary)} ₺",
                                fontSize = 12.sp,
                                color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.80f)
                            )
                    }
                    Icon(
                        Icons.Default.ChevronRight, null,
                        tint = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.7f),
                        modifier = Modifier.size(20.dp)
                    )
                }
            }

            // Icerik bolumu
            Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {

            Spacer(Modifier.height(12.dp))

            val totalIncome = profile.totalIncome()
            val thisMonthPay = try { com.bluechip.finance.data.PaymentManager.getUpcomingThisMonth(context) } catch (_: Exception) { emptyList() }
            val totalExpense = thisMonthPay.sumOf { it.amount }
            val advanceTaken = profile.isAdvanceTaken()
            val advanceDeduct = if (advanceTaken && profile.advanceAmount > 0) profile.advanceAmount else 0.0
            val netRemaining = totalIncome - totalExpense - advanceDeduct
            var showIncomeDetail  by remember { mutableStateOf(false) }
            var showExpenseDetail by remember { mutableStateOf(false) }

            if (showIncomeDetail) {
                androidx.compose.ui.window.Dialog(onDismissRequest = { showIncomeDetail = false }) {
                    Card(shape = RoundedCornerShape(20.dp),
                        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                        elevation = CardDefaults.cardElevation(8.dp)) {
                        Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text("Gelir Detayi", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)
                            HorizontalDivider(color = com.bluechip.finance.ui.theme.PurplePrimary.copy(alpha = 0.15f))
                            if (profile.netSalary > 0)
                                Row(Modifier.fillMaxWidth()) {
                                    Text("💰 Maas", fontSize = 13.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                                    Text("${formatMoney(profile.netSalary)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary)
                                }
                            if (profile.isRetired && profile.retirementSalary > 0)
                                Row(Modifier.fillMaxWidth()) {
                                    Text("🏦 Emekli Maasi", fontSize = 13.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                                    Text("${formatMoney(profile.retirementSalary)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary)
                                }
                            profile.sideIncomes.forEach { side ->
                                Row(Modifier.fillMaxWidth()) {
                                    Text("${side.category.emoji} ${side.label.ifBlank { side.category.label }}", fontSize = 13.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                                    Text("${formatMoney(side.effectiveAmount())} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary)
                                }
                            }
                            // Mesai toplami
                            val otTotal = remember { com.bluechip.finance.data.OvertimeManager.thisMonthTotal(context) }
                            if (otTotal > 0) Row(
                                Modifier.fillMaxWidth().clickable { showIncomeDetail = false },
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text("⏰ Mesai", fontSize = 13.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                                Text("${formatMoney(otTotal)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary)
                            }
                            HorizontalDivider(color = com.bluechip.finance.ui.theme.PurplePrimary.copy(alpha = 0.15f))
                            Row(Modifier.fillMaxWidth()) {
                                Text("Toplam", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary, modifier = Modifier.weight(1f))
                                Text("${formatMoney(totalIncome + otTotal)} ₺", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = com.bluechip.finance.ui.theme.PurplePrimary)
                            }
                            TextButton(onClick = { showIncomeDetail = false }, modifier = Modifier.align(Alignment.End)) { Text("Kapat") }
                        }
                    }
                }
            }

            if (showExpenseDetail) {
                androidx.compose.ui.window.Dialog(onDismissRequest = { showExpenseDetail = false }) {
                    Card(shape = RoundedCornerShape(20.dp),
                        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                        elevation = CardDefaults.cardElevation(8.dp)) {
                        Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text("Bu Ay Giderler", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)
                            HorizontalDivider(color = com.bluechip.finance.ui.theme.PurplePrimary.copy(alpha = 0.15f))
                            if (thisMonthPay.isEmpty())
                                Text("Bu ay odeme yok", fontSize = 13.sp, color = colors.textSecondary)
                            else {
                                thisMonthPay.forEach { p ->
                                    Row(Modifier.fillMaxWidth()) {
                                        Text("${p.category.emoji} ${p.name}", fontSize = 13.sp, color = colors.textPrimary,
                                            modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        Text("${formatMoney(p.amount)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary)
                                    }
                                }
                                HorizontalDivider(color = com.bluechip.finance.ui.theme.PurplePrimary.copy(alpha = 0.15f))
                                Row(Modifier.fillMaxWidth()) {
                                    Text("Toplam", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary, modifier = Modifier.weight(1f))
                                    Text("${formatMoney(totalExpense)} ₺", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = colors.warning)
                                }
                            }
                            TextButton(onClick = { showExpenseDetail = false }, modifier = Modifier.align(Alignment.End)) { Text("Kapat") }
                        }
                    }
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth()
                    .background(com.bluechip.finance.ui.theme.PurplePrimary.copy(alpha = 0.07f), RoundedCornerShape(10.dp)),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    modifier = Modifier.weight(1f).clickable { showIncomeDetail = true }
                        .padding(horizontal = 10.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("💰", fontSize = 14.sp)
                    Spacer(Modifier.width(6.dp))
                    Text("Toplam Gelir", fontSize = 12.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
                    Text("${formatMoney(totalIncome)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = com.bluechip.finance.ui.theme.PurplePrimary)
                    Icon(Icons.Default.KeyboardArrowRight, null, tint = colors.textSecondary, modifier = Modifier.size(14.dp))
                }
                Box(
                    modifier = Modifier
                        .padding(end = 6.dp)
                        .size(28.dp)
                        .background(com.bluechip.finance.ui.theme.PurplePrimary, androidx.compose.foundation.shape.CircleShape)
                        .clickable { onNavigate("profile_income") },
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Default.Add, null, tint = androidx.compose.ui.graphics.Color.White, modifier = Modifier.size(16.dp))
                }
            }

            Spacer(Modifier.height(4.dp))

            Row(
                modifier = Modifier.fillMaxWidth()
                    .background(colors.error.copy(alpha = 0.07f), RoundedCornerShape(10.dp)),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    modifier = Modifier.weight(1f).clickable { showExpenseDetail = true }
                        .padding(horizontal = 10.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("💸", fontSize = 14.sp)
                    Spacer(Modifier.width(6.dp))
                    Text("Toplam Gider", fontSize = 12.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
                    Text("${formatMoney(totalExpense)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.error)
                    Icon(Icons.Default.KeyboardArrowRight, null, tint = colors.textSecondary, modifier = Modifier.size(14.dp))
                }
                Box(
                    modifier = Modifier
                        .padding(end = 6.dp)
                        .size(28.dp)
                        .background(colors.error, androidx.compose.foundation.shape.CircleShape)
                        .clickable { onNavigate("payments_add") },
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Default.Add, null, tint = androidx.compose.ui.graphics.Color.White, modifier = Modifier.size(16.dp))
                }
            }

            if (advanceTaken && advanceDeduct > 0) {
                Spacer(Modifier.height(4.dp))
                Row(modifier = Modifier.fillMaxWidth()
                    .background(Color(0xFFFF9800).copy(alpha = 0.07f), RoundedCornerShape(10.dp))
                    .padding(horizontal = 10.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("💳", fontSize = 14.sp)
                    Spacer(Modifier.width(6.dp))
                    Text("Avans (kullanildi)", fontSize = 12.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
                    Text("-${formatMoney(advanceDeduct)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Color(0xFFFF9800))
                }
            }

            HorizontalDivider(modifier = Modifier.padding(vertical = 6.dp),
                color = com.bluechip.finance.ui.theme.PurplePrimary.copy(alpha = 0.1f))

            Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text("Net Kalan", fontSize = 13.sp, fontWeight = FontWeight.Bold,
                    color = colors.textPrimary, modifier = Modifier.weight(1f))
                Text("${formatMoney(netRemaining)} ₺", fontSize = 15.sp, fontWeight = FontWeight.Bold,
                    color = if (netRemaining >= 0) com.bluechip.finance.ui.theme.PurplePrimary else colors.error)
            }

            Spacer(Modifier.height(10.dp))

            Row(modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(moodText, fontSize = 11.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
                if (daysToSalary != null) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text("💰", fontSize = 13.sp)
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(if (daysToSalary == 0) "Bugun!" else "$daysToSalary gun",
                                fontWeight = FontWeight.Bold, fontSize = 11.sp,
                                color = if (daysToSalary <= 3) com.bluechip.finance.ui.theme.PurplePrimary else colors.textSecondary)
                            Text("maas", fontSize = 9.sp, color = colors.textSecondary)
                        }
                    }
                }
                if (daysToAdvance != null) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text("💸", fontSize = 13.sp)
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(if (daysToAdvance == 0) "Bugun!" else "$daysToAdvance gun",
                                fontWeight = FontWeight.Bold, fontSize = 11.sp,
                                color = if (daysToAdvance <= 2) Color(0xFF00897B) else colors.textSecondary)
                            Text("avans", fontSize = 9.sp, color = colors.textSecondary)
                        }
                    }
                }
            }
            } // end icerik Column
        }
    }
}

// ── Yaklaşan Ödemeler kartı ──────────────────────────────────────
@Composable
private fun UpcomingPaymentsCard(context: android.content.Context, onNavigate: (String) -> Unit) {
    val colors = LocalAppColors.current
    val upcoming = remember { PaymentManager.getUpcomingThisMonth(context).take(2) }
    val thisMonthTotal = remember { PaymentManager.getThisMonthTotal(context) }
    if (PaymentManager.getActivePayments(context).isEmpty()) return

    Card(shape = RoundedCornerShape(20.dp), elevation = CardDefaults.cardElevation(3.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
        modifier = Modifier.fillMaxWidth().clickable { onNavigate("payments") }) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Payment, null, tint = com.bluechip.finance.ui.theme.PurplePrimary, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Yaklaşan Ödemeler", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary, modifier = Modifier.weight(1f))
                Icon(Icons.Default.ChevronRight, null, tint = colors.textSecondary, modifier = Modifier.size(18.dp))
            }
            if (upcoming.isEmpty()) {
                Text("Bu ay kalan ödeme yok 🎉", fontSize = 13.sp, color = colors.textSecondary)
            } else {
                upcoming.forEach { p ->
                    val today = Calendar.getInstance().get(Calendar.DAY_OF_MONTH)
                    val daysLeft = p.dueDayOfMonth - today
                    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text(p.category.emoji, fontSize = 16.sp)
                        Spacer(Modifier.width(8.dp))
                        Text(p.name, fontSize = 13.sp, color = colors.textPrimary, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Column(horizontalAlignment = Alignment.End) {
                            Text("${formatMoney(p.amount)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = com.bluechip.finance.ui.theme.PurplePrimary)
                            Text(if (daysLeft <= 0) "Bugün!" else "$daysLeft gün", fontSize = 10.sp, color = if (daysLeft <= 3) colors.warning else colors.textSecondary)
                        }
                    }
                }
                HorizontalDivider(color = colors.cardGray, modifier = Modifier.padding(vertical = 2.dp))
                Row(modifier = Modifier.fillMaxWidth()) {
                    Text("Bu ay toplam:", fontSize = 12.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
                    Text("${formatMoney(thisMonthTotal)} ₺", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = colors.warning)
                }
            }
        }
    }
}



// ── Birikimler Karti ────────────────────────────────────────────
@Composable
private fun SavingsHomeCard(context: android.content.Context, onNavigate: (String) -> Unit) {
    val colors  = LocalAppColors.current
    val manager = remember { com.bluechip.finance.data.SavingsManager(context) }
    val records = remember { manager.loadAll() }
    val cache   = remember { manager.loadPriceCache() }
    if (records.isEmpty()) return

    val totalValue = manager.totalValueTry(records, cache)
    val totalCost  = manager.totalCostTry(records)
    val profit     = totalValue - totalCost
    val profitPct  = if (totalCost > 0) (profit / totalCost) * 100.0 else 0.0
    val emoji = when { profit > 0 -> "😊"; profit < 0 -> "😢"; else -> "😐" }

    // Kategori bazlı toplamlar
    val catData = com.bluechip.finance.data.SavingsCategory.values().mapNotNull { cat ->
        val catRecs = records.filter { it.category == cat }
        if (catRecs.isEmpty()) return@mapNotNull null
        val value  = manager.totalValueTry(catRecs, cache)
        val cost   = manager.totalCostTry(catRecs)
        Triple(cat, value, value - cost)
    }

    Card(
        modifier = Modifier.fillMaxWidth().clickable { onNavigate("savings") },
        shape = androidx.compose.foundation.shape.RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
        elevation = CardDefaults.cardElevation(3.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            // ── Üst satır: genel toplam ─────────────────────────────
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(emoji, fontSize = 24.sp)
                Spacer(Modifier.width(10.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text("Birikimlerim", fontSize = 12.sp, color = colors.textSecondary)
                    Text("${com.bluechip.finance.ui.components.formatMoney(totalValue)} ₺",
                        fontSize = 16.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        "${if (profit >= 0) "+" else ""}${com.bluechip.finance.ui.components.formatMoney(profit)} ₺",
                        fontSize = 13.sp, fontWeight = FontWeight.Bold,
                        color = if (profit >= 0) colors.success else colors.error
                    )
                    Text("(%${"%.1f".format(profitPct)})", fontSize = 11.sp,
                        color = if (profit >= 0) colors.success else colors.error)
                }
                Spacer(Modifier.width(6.dp))
                Icon(Icons.Default.ChevronRight, null, tint = colors.textSecondary, modifier = Modifier.size(18.dp))
            }

            // ── Kategori satırları ──────────────────────────────────
            if (catData.size > 1) {
                HorizontalDivider(color = com.bluechip.finance.ui.theme.PurplePrimary.copy(alpha = 0.1f))
                catData.forEach { (cat, value, catProfit) ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(cat.emoji, fontSize = 14.sp)
                        Spacer(Modifier.width(6.dp))
                        Text(cat.label, fontSize = 12.sp, color = colors.textSecondary, modifier = Modifier.weight(1f))
                        Text("${com.bluechip.finance.ui.components.formatMoney(value)} ₺",
                            fontSize = 12.sp, color = colors.textPrimary)
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "${if (catProfit >= 0) "+" else ""}${com.bluechip.finance.ui.components.formatMoney(catProfit)} ₺",
                            fontSize = 11.sp,
                            color = if (catProfit >= 0) colors.success else colors.error
                        )
                    }
                }
            }
        }
    }
}

// ── Mesai Takip ana sayfa karti ─────────────────────────────────────
@Composable
private fun OvertimeHomeCard(context: android.content.Context, onNavigate: (String) -> Unit) {
    val colors        = LocalAppColors.current
    val thisMonthRecs = androidx.compose.runtime.remember {
        com.bluechip.finance.data.OvertimeManager.thisMonthRecords(context)
    }
    val totalNet   = thisMonthRecs.sumOf { it.netAmount }
    val totalBrut  = thisMonthRecs.sumOf { it.brutAmount }
    val totalHours = thisMonthRecs.sumOf { it.hours }
    val monthName  = java.text.SimpleDateFormat("MMMM yyyy", java.util.Locale("tr"))
        .format(java.util.Calendar.getInstance().time).replaceFirstChar { it.uppercase() }

    Card(
        modifier = Modifier.fillMaxWidth().clickable { onNavigate("overtime_track") },
        shape = androidx.compose.foundation.shape.RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
        elevation = CardDefaults.cardElevation(3.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Timer, null,
                    tint = com.bluechip.finance.ui.theme.PurplePrimary,
                    modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Mesai Takip", fontWeight = FontWeight.Bold,
                    fontSize = 14.sp, color = colors.textPrimary,
                    modifier = Modifier.weight(1f))
                Icon(Icons.Default.ChevronRight, null,
                    tint = colors.textSecondary, modifier = Modifier.size(18.dp))
            }
            Text(monthName, fontSize = 11.sp, color = colors.textSecondary)
            if (thisMonthRecs.isEmpty()) {
                Text("Bu ay mesai kaydi yok", fontSize = 13.sp, color = colors.textSecondary)
            } else {
                Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Net (ele gecen)", fontSize = 11.sp, color = colors.textSecondary)
                        Text("${com.bluechip.finance.ui.components.formatMoney(totalNet)} TL",
                            fontSize = 20.sp, fontWeight = FontWeight.Bold,
                            color = com.bluechip.finance.ui.theme.PurplePrimary)
                        Text("Brut: ${com.bluechip.finance.ui.components.formatMoney(totalBrut)} TL",
                            fontSize = 11.sp, color = colors.textSecondary)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("Toplam Sure", fontSize = 11.sp, color = colors.textSecondary)
                        Text(
                            if (totalHours == totalHours.toLong().toDouble())
                                "${totalHours.toInt()} saat"
                            else "${String.format("%.1f", totalHours)} saat",
                            fontSize = 16.sp, fontWeight = FontWeight.Bold,
                            color = colors.textPrimary
                        )
                        Text("${thisMonthRecs.size} kayit", fontSize = 11.sp, color = colors.textSecondary)
                    }
                }
            }
        }
    }
}


@Composable
private fun UpcomingSpecialDaysCard(context: android.content.Context, onNavigate: (String) -> Unit) {
    val colors = LocalAppColors.current
    var specialDays by remember { mutableStateOf<List<Pair<SpecialDay, Int>>>(emptyList()) }
    var holidays by remember { mutableStateOf<List<Pair<PublicHoliday, Int>>>(emptyList()) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        specialDays = SpecialDayManager.getUpcoming(context, 30)
        val fetched = HolidayManager.getHolidays(context)
        holidays = HolidayManager.getUpcoming(fetched, 30)
    }

    // Boş olsa bile kartı göster — kullanıcı ekleyebilsin

    Card(
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(3.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("🎉", fontSize = 18.sp)
                    Spacer(Modifier.width(8.dp))
                    Text("Yaklaşan Özel Günler", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary)
                }
                TextButton(onClick = { onNavigate("special_days") }) { Text("Tümü") }
                TextButton(onClick = { onNavigate("special_days_add") }) { Text("+ Ekle", color = MaterialTheme.colorScheme.primary) }
            }
            Spacer(Modifier.height(8.dp))

            // Ikisi de bossa ekle butonu goster
            if (specialDays.isEmpty() && holidays.isEmpty()) {
                Row(
                    Modifier.fillMaxWidth().clickable { onNavigate("special_days") },
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center
                ) {
                    Icon(Icons.Filled.Add, null, modifier = Modifier.size(16.dp), tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(6.dp))
                    Text("Ozel gun ekle", fontSize = 13.sp, color = MaterialTheme.colorScheme.primary)
                }
                Spacer(Modifier.height(4.dp))
                return@Card
            }

            // Özel günler
            specialDays.take(3).forEach { (day, remaining) ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = 0.1f),
                        modifier = Modifier.size(36.dp)
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Text(
                                if (remaining == 0) "🎉" else "$remaining",
                                fontSize = if (remaining == 0) 16.sp else 12.sp,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }
                    }
                    Spacer(Modifier.width(10.dp))
                    Column {
                        Text(day.title, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = colors.textPrimary)
                        if (day.subtitle.isNotEmpty()) Text(day.subtitle, fontSize = 11.sp, color = colors.textSecondary)
                    }
                    Spacer(Modifier.weight(1f))
                    Text("${day.day}/${day.month}", fontSize = 11.sp, color = colors.textSecondary)
                }
            }

            if (specialDays.isNotEmpty() && holidays.isNotEmpty()) {
                Divider(Modifier.padding(vertical = 6.dp))
            }

            // Resmi tatiller
            holidays.take(3).forEach { (holiday, remaining) ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = androidx.compose.ui.graphics.Color(0xFFE53935).copy(alpha = 0.1f),
                        modifier = Modifier.size(36.dp)
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Text(
                                if (remaining == 0) "🇹🇷" else "$remaining",
                                fontSize = if (remaining == 0) 16.sp else 12.sp,
                                fontWeight = FontWeight.Bold,
                                color = androidx.compose.ui.graphics.Color(0xFFE53935)
                            )
                        }
                    }
                    Spacer(Modifier.width(10.dp))
                    Column {
                        Text(holiday.localName, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = colors.textPrimary)
                        Text("Resmi Tatil", fontSize = 11.sp, color = colors.textSecondary)
                    }
                    Spacer(Modifier.weight(1f))
                    Text("${holiday.day}/${holiday.month}", fontSize = 11.sp, color = colors.textSecondary)
                }
            }
        }
    }
}
