package com.bluechip.finance.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.*
import androidx.compose.foundation.background
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.bluechip.finance.data.Article
import com.bluechip.finance.data.NewsApiService
import com.bluechip.finance.ui.components.formatMoney
import com.bluechip.finance.ui.components.formatNumber
import com.bluechip.finance.ui.theme.*
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.URL
import java.text.SimpleDateFormat
import java.util.*

data class InfoCard(val id: Int, val category: String, val icon: String, val text: String)

@Composable
fun HomeScreen(onNavigate: (String) -> Unit) {
    val context = LocalContext.current
    val colors = LocalAppColors.current

    // Piyasa Verileri Değişkenleri (Orijinal Kodundan)
    var usdRate by remember { mutableDoubleStateOf(0.0) }
    var eurRate by remember { mutableDoubleStateOf(0.0) }
    var goldUSD by remember { mutableDoubleStateOf(0.0) }
    var btcUSD by remember { mutableDoubleStateOf(0.0) }
    var ethUSD by remember { mutableDoubleStateOf(0.0) }
    var isTL by remember { mutableStateOf(true) }
    var updateTime by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(true) }
    var articles by remember { mutableStateOf<List<Article>>(emptyList()) }
    var newsStatus by remember { mutableStateOf("Haberler yükleniyor...") }

    // JSON Verileri
    val infoList = remember {
        try {
            val jsonString = context.assets.open("info_cards.json").bufferedReader().use { it.readText() }
            val listType = object : TypeToken<List<InfoCard>>() {}.type
            Gson().fromJson<List<InfoCard>>(jsonString, listType).shuffled()
        } catch (e: Exception) { emptyList<InfoCard>() }
    }
    var currentIndex by remember { mutableIntStateOf(0) }

    // Veri Çekme (Orijinal LaunchedEffect)
    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            try {
                val tcmb = URL("https://www.tcmb.gov.tr/kurlar/today.xml").readText()
                val usdMatch = Regex("<Currency[^>]*CurrencyCode=\"USD\"[^>]*>.*?<ForexSelling>([0-9.]+)</ForexSelling>", RegexOption.DOT_MATCHES_ALL).find(tcmb)
                val eurMatch = Regex("<Currency[^>]*CurrencyCode=\"EUR\"[^>]*>.*?<ForexSelling>([0-9.]+)</ForexSelling>", RegexOption.DOT_MATCHES_ALL).find(tcmb)
                if (usdMatch != null) usdRate = usdMatch.groupValues[1].toDouble()
                if (eurMatch != null) eurRate = eurMatch.groupValues[1].toDouble()
            } catch (_: Exception) { usdRate = 34.2; eurRate = 37.1 }
            
            try {
                val crypto = URL("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether-gold&vs_currencies=usd").readText()
                val json = JSONObject(crypto)
                btcUSD = json.getJSONObject("bitcoin").getDouble("usd")
                ethUSD = json.getJSONObject("ethereum").getDouble("usd")
                goldUSD = json.getJSONObject("tether-gold").getDouble("usd")
            } catch (_: Exception) { btcUSD = 96000.0; ethUSD = 2700.0; goldUSD = 2600.0 }
            
            isLoading = false
            updateTime = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
        }
        withContext(Dispatchers.IO) {
            try {
                val response = NewsApiService.create().getNews()
                articles = response.articles.take(3)
                newsStatus = "Son ${articles.size} haber (${SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())})"
            } catch (e: Exception) { newsStatus = "Haber yüklenemedi" }
        }
    }

    // 10 Saniye Sayacı
    LaunchedEffect(key1 = currentIndex) {
        if (infoList.isNotEmpty()) {
            delay(10000L)
            currentIndex = (currentIndex + 1) % infoList.size
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // 1. Piyasa Verileri Kartı (Orijinal Kodun)
        Card(
            shape = RoundedCornerShape(16.dp),
            elevation = CardDefaults.cardElevation(4.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.TrendingUp, null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(8.dp))
                    Text("Piyasa Verileri", fontWeight = FontWeight.Bold, color = colors.textPrimary, modifier = Modifier.weight(1f))
                    Switch(checked = !isTL, onCheckedChange = { isTL = !it })
                }
                if (isLoading) {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp))
                } else {
                    val s = if (isTL) "₺" else "$"
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                        PriceChip("USD", "${formatMoney(if (isTL) usdRate else 1.0)}$s", Color(0xFF4CAF50))
                        PriceChip("EUR", "${formatMoney(if (isTL) eurRate else eurRate/usdRate)}$s", Color(0xFF2196F3))
                        PriceChip("Altın", "${formatMoney(if (isTL) goldUSD*usdRate else goldUSD)}$s", Color(0xFFFF9800))
                    }
                }
            }
        }

        // 2. YENİ AKILLI BİLGİ KARTI
        if (infoList.isNotEmpty()) {
            AnimatedContent(
                targetState = infoList[currentIndex],
                transitionSpec = { fadeIn() togetherWith fadeOut() },
                label = "InfoAnim"
            ) { card ->
                InfoBanner(card) { currentIndex = (currentIndex + 1) % infoList.size }
            }
        }

        // 3. Haberler Bölümü
        Text("Ekonomi Haberleri", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)
        Text(newsStatus, fontSize = 12.sp, color = colors.textSecondary)

        articles.forEach { article ->
            NewsCard(article = article, onClick = {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(article.url))
                context.startActivity(intent)
            })
        }
    }
}

@Composable
fun InfoBanner(card: InfoCard, onClick: () -> Unit) {
    val gradient = Brush.linearGradient(colors = listOf(Color(0xFF1A237E), Color(0xFF3949AB)))
    Box(
        modifier = Modifier.fillMaxWidth().height(140.dp).clip(RoundedCornerShape(20.dp))
            .background(gradient).clickable { onClick() }.padding(16.dp)
    ) {
        Column {
            Text(card.category.uppercase(), color = Color.White.copy(0.7f), fontWeight = FontWeight.Bold, fontSize = 11.sp)
            Spacer(Modifier.height(8.dp))
            Text(card.text, color = Color.White, fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.Medium)
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.BottomEnd) {
                Text("Değiştirmek için dokun", color = Color.White.copy(0.4f), fontSize = 10.sp)
            }
        }
    }
}

@Composable
private fun PriceChip(name: String, price: String, color: Color) {
    val colors = LocalAppColors.current
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(name, fontSize = 11.sp, color = colors.textSecondary)
        Text(price, fontSize = 14.sp, fontWeight = FontWeight.Bold, color = color)
    }
}

@Composable
private fun NewsCard(article: Article, onClick: () -> Unit) {
    val colors = LocalAppColors.current
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(article.title, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = colors.textPrimary, maxLines = 2)
            Spacer(Modifier.height(4.dp))
            Text(article.description ?: "", fontSize = 12.sp, color = colors.textSecondary, maxLines = 2)
        }
    }
}
