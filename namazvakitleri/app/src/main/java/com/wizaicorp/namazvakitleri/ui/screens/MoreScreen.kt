package com.wizaicorp.namazvakitleri.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Article
import androidx.compose.material.icons.filled.Book
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Key
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.LocationCity
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.TouchApp
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.BannerAd
import com.wizaicorp.namazvakitleri.Screen
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.PrayerTimes

private const val PLAY_URL = "https://play.google.com/store/apps/details?id=com.wizaicorp.namazvakitleri"
private const val PRIVACY_URL = "https://hakanerbasss.github.io/namaz-gizlilik.html"

private data class MoreItem(val key: String, val icon: ImageVector, val action: String)

@Composable
fun MoreContent(
    prayerTimes: PrayerTimes?,
    onOpen: (Screen) -> Unit,
    modifier: Modifier = Modifier
) {
    val ctx = LocalContext.current

    // AI Asistan karti yalnizca DeepSeek anahtari girilmisse gorunur
    val hasAi = com.wizaicorp.namazvakitleri.data.ApiPrefs.hasDeepSeek(ctx)

    val items = buildList {
        add(MoreItem("library",        Icons.Filled.Book,          "library"))
        add(MoreItem("education",      Icons.Filled.School,        "education"))
        add(MoreItem("zikir",          Icons.Filled.TouchApp,      "zikir"))
        add(MoreItem("kaza",           Icons.Filled.History,       "kaza"))
        add(MoreItem("holy_days",      Icons.Filled.CalendarMonth, "holy"))
        add(MoreItem("esma",           Icons.Filled.MenuBook,      "esma"))
        add(MoreItem("news",           Icons.Filled.Article,       "news"))
        if (hasAi) add(MoreItem("assistant", Icons.Filled.SmartToy, "assistant"))
        add(MoreItem("notif_settings", Icons.Filled.Notifications, "settings"))
        add(MoreItem("change_city",    Icons.Filled.LocationCity,  "city"))
        add(MoreItem("api_settings",   Icons.Filled.Key,           "api"))
        add(MoreItem("share_app",      Icons.Filled.Share,         "share"))
        add(MoreItem("rate_app",       Icons.Filled.Star,          "rate"))
        add(MoreItem("privacy",        Icons.Filled.Info,          "privacy"))
    }

    LazyVerticalGrid(
        columns = GridCells.Fixed(2),
        modifier = modifier.fillMaxSize().padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        contentPadding = PaddingValues(vertical = 12.dp)
    ) {
        items(items) { item ->
            Surface(
                shape = RoundedCornerShape(16.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.clickable {
                    when (item.action) {
                        "library"  -> onOpen(Screen.Library)
                        "education" -> onOpen(Screen.Education)
                        "zikir"    -> onOpen(Screen.Zikir)
                        "kaza"     -> onOpen(Screen.Kaza)
                        "holy"     -> onOpen(Screen.HolyDays)
                        "esma"     -> onOpen(Screen.Esma)
                        "news"     -> onOpen(Screen.News)
                        "assistant" -> onOpen(Screen.Assistant)
                        "settings" -> onOpen(Screen.Settings)
                        "city"     -> onOpen(Screen.CitySelect)
                        "api"      -> onOpen(Screen.ApiSettings)
                        "share"    -> shareTimes(ctx, prayerTimes)
                        "rate"     -> openUrl(ctx, PLAY_URL)
                        "privacy"  -> openUrl(ctx, PRIVACY_URL)
                    }
                }
            ) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 22.dp, horizontal = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Icon(
                        item.icon, contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(32.dp)
                    )
                    Spacer(Modifier.height(10.dp))
                    Text(
                        Lang.get(item.key),
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                        textAlign = TextAlign.Center,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

private fun shareTimes(ctx: android.content.Context, t: PrayerTimes?) {
    val sb = StringBuilder()
    if (t != null) {
        sb.appendLine("${Lang.get("share_today")} - ${t.city} (${t.date})")
        t.asList().forEach { (name, time) -> sb.appendLine("$name: $time") }
        sb.appendLine()
    }
    sb.append(PLAY_URL)
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, sb.toString())
    }
    try {
        ctx.startActivity(Intent.createChooser(intent, Lang.get("share_app")))
    } catch (e: Exception) { }
}

private fun openUrl(ctx: android.content.Context, url: String) {
    try {
        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    } catch (e: Exception) { }
}

/** Alt ozellik ekranlari icin ortak iskelet: ust bar + geri + altta banner */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeatureScaffold(
    title: String,
    onBack: () -> Unit,
    content: @Composable (PaddingValues) -> Unit
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title, fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = Lang.get("back"))
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor             = MaterialTheme.colorScheme.primary,
                    titleContentColor          = MaterialTheme.colorScheme.onPrimary,
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        },
        bottomBar = { BannerAd() }
    ) { padding -> content(padding) }
}
