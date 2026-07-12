#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Namaz Vakitleri - Tam Kurulum Scripti
Calistirmadan once: google-services.json dosyasini app/ klasorune koy!
Calistir: python3 ~/patch_namaz_vakitleri.py
"""

import os, sys

BASE = "/data/data/com.termux/files/home/namazvakitleri"
PKG  = "com.wizaicorp.namazvakitleri"
PP   = "com/wizaicorp/namazvakitleri"
SRC  = f"{BASE}/app/src/main"
JAVA = f"{SRC}/java/{PP}"

def mkdirs(p):
    os.makedirs(p, exist_ok=True)

def write(path, content):
    mkdirs(os.path.dirname(path))
    try:
        content.encode("utf-8")
    except UnicodeEncodeError as e:
        print(f"UNICODE HATASI ({path}): {e}")
        sys.exit(1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [OK] {path.replace(BASE,'')}")

def patch_file(path, changes):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for old, new in changes:
        if old not in content:
            print(f"  [MISS] {repr(old[:50])}")
            sys.exit(1)
        content = content.replace(old, new, 1)
    try:
        content.encode("utf-8")
    except UnicodeEncodeError as e:
        print(f"UNICODE HATASI: {e}")
        sys.exit(1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [PATCH] {path.replace(BASE,'')}")

print("=== Namaz Vakitleri Kurulum ===")

# ── Dizinler ──────────────────────────────────────────────────────────────────
print("\n[1] Dizinler olusturuluyor...")
for d in [f"{JAVA}/api", f"{JAVA}/data", f"{JAVA}/ui/theme", f"{JAVA}/ui/screens"]:
    mkdirs(d)
    print(f"  mkdir {d.replace(BASE,'')}")

# ── data/PrayerTimes.kt ───────────────────────────────────────────────────────
print("\n[2] data/PrayerTimes.kt")
write(f"{JAVA}/data/PrayerTimes.kt", f"""package {PKG}.data

data class PrayerTimes(
    val imsak: String,
    val gunes: String,
    val ogle: String,
    val ikindi: String,
    val aksam: String,
    val yatsi: String,
    val city: String,
    val date: String
) {{
    fun asList(): List<Pair<String, String>> = listOf(
        "İmsak" to imsak,
        "Güneş" to gunes,
        "Öğle" to ogle,
        "İkindi" to ikindi,
        "Akşam" to aksam,
        "Yatsı" to yatsi
    )
}}

data class City(val name: String, val apiName: String)
""")

# ── data/CityManager.kt ───────────────────────────────────────────────────────
print("\n[3] data/CityManager.kt")
write(f"{JAVA}/data/CityManager.kt", f"""package {PKG}.data

import android.content.Context
import com.google.firebase.messaging.FirebaseMessaging

object CityManager {{

    private const val PREF = "namaz_prefs"
    private const val KEY_CITY = "selected_city"
    private const val KEY_CITY_API = "selected_city_api"

    val cities = listOf(
        City("Adana", "Adana"), City("Ankara", "Ankara"), City("Antalya", "Antalya"),
        City("Bursa", "Bursa"), City("Diyarbakır", "Diyarbakir"), City("Erzurum", "Erzurum"),
        City("Eskişehir", "Eskisehir"), City("Gaziantep", "Gaziantep"), City("Hatay", "Hatay"),
        City("İstanbul", "Istanbul"), City("İzmir", "Izmir"), City("Kahramanmaraş", "Kahramanmaras"),
        City("Kayseri", "Kayseri"), City("Kocaeli", "Kocaeli"), City("Konya", "Konya"),
        City("Malatya", "Malatya"), City("Mersin", "Mersin"), City("Samsun", "Samsun"),
        City("Trabzon", "Trabzon"), City("Van", "Van")
    )

    fun getSelected(ctx: Context): City {{
        val prefs = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val name = prefs.getString(KEY_CITY, "İstanbul") ?: "İstanbul"
        val api  = prefs.getString(KEY_CITY_API, "Istanbul") ?: "Istanbul"
        return City(name, api)
    }}

    fun save(ctx: Context, city: City) {{
        val prev = getSelected(ctx)
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putString(KEY_CITY, city.name)
            .putString(KEY_CITY_API, city.apiName)
            .apply()
        FirebaseMessaging.getInstance().unsubscribeFromTopic("namaz_\${{prev.apiName.lowercase()}}")
        FirebaseMessaging.getInstance().subscribeToTopic("namaz_\${{city.apiName.lowercase()}}")
    }}
}}
""")

# ── api/AladhanApi.kt ─────────────────────────────────────────────────────────
print("\n[4] api/AladhanApi.kt")
write(f"{JAVA}/api/AladhanApi.kt", f"""package {PKG}.api

import com.google.gson.annotations.SerializedName
import {PKG}.data.PrayerTimes
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Query
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

interface AladhanService {{
    @GET("v1/timingsByCity")
    suspend fun getTimes(
        @Query("city")    city: String,
        @Query("country") country: String = "Turkey",
        @Query("method")  method: Int = 13
    ): AladhanResponse
}}

data class AladhanResponse(val data: AladhanData)
data class AladhanData(val timings: AladhanTimings, val date: AladhanDate)
data class AladhanTimings(
    @SerializedName("Fajr")    val fajr: String,
    @SerializedName("Sunrise") val sunrise: String,
    @SerializedName("Dhuhr")   val dhuhr: String,
    @SerializedName("Asr")     val asr: String,
    @SerializedName("Maghrib") val maghrib: String,
    @SerializedName("Isha")    val isha: String
)
data class AladhanDate(val readable: String)

object AladhanApi {{
    private val service: AladhanService by lazy {{
        Retrofit.Builder()
            .baseUrl("https://api.aladhan.com/")
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(AladhanService::class.java)
    }}

    suspend fun getPrayerTimes(city: String): PrayerTimes {{
        val resp = service.getTimes(city)
        val t = resp.data.timings
        val today = SimpleDateFormat("d MMMM yyyy", Locale("tr")).format(Date())
        return PrayerTimes(
            imsak  = t.fajr.take(5),
            gunes  = t.sunrise.take(5),
            ogle   = t.dhuhr.take(5),
            ikindi = t.asr.take(5),
            aksam  = t.maghrib.take(5),
            yatsi  = t.isha.take(5),
            city   = city,
            date   = today
        )
    }}
}}
""")

# ── NamazFCMService.kt ────────────────────────────────────────────────────────
print("\n[5] NamazFCMService.kt")
write(f"{JAVA}/NamazFCMService.kt", f"""package {PKG}

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import {PKG}.data.CityManager

class NamazFCMService : FirebaseMessagingService() {{

    override fun onMessageReceived(message: RemoteMessage) {{
        val title = message.notification?.title ?: message.data["title"] ?: "Namaz Vakti"
        val body  = message.notification?.body  ?: message.data["body"]  ?: ""
        showNotification(title, body)
    }}

    override fun onNewToken(token: String) {{
        val city = CityManager.getSelected(this)
        com.google.firebase.messaging.FirebaseMessaging.getInstance()
            .subscribeToTopic("namaz_\${{city.apiName.lowercase()}}")
    }}

    private fun showNotification(title: String, body: String) {{
        val channelId = "namaz_vakitleri"
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(channelId, "Namaz Vakitleri",
            NotificationManager.IMPORTANCE_HIGH).apply {{
            description = "Namaz vakti bildirimleri"
            enableVibration(true)
        }}
        nm.createNotificationChannel(channel)
        val intent = Intent(this, MainActivity::class.java).apply {{
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP
        }}
        val pending = PendingIntent.getActivity(this, 0, intent,
            PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(android.R.drawable.ic_menu_recent_history)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pending)
            .build()
        nm.notify(System.currentTimeMillis().toInt(), notification)
    }}
}}
""")

# ── AdManager.kt ──────────────────────────────────────────────────────────────
print("\n[6] AdManager.kt")
write(f"{JAVA}/AdManager.kt", f"""package {PKG}

import android.app.Activity
import android.content.Context
import android.util.Log
import androidx.compose.runtime.Composable
import androidx.compose.ui.viewinterop.AndroidView
import com.google.android.gms.ads.*
import com.google.android.gms.ads.interstitial.InterstitialAd
import com.google.android.gms.ads.interstitial.InterstitialAdLoadCallback
import com.google.android.gms.ads.appopen.AppOpenAd

// AdMob konsolundan gercek ID'leri al
private const val BANNER_ID       = "ca-app-pub-XXXXXXXXXXXXXXXX/XXXXXXXXXX"
private const val INTERSTITIAL_ID = "ca-app-pub-XXXXXXXXXXXXXXXX/XXXXXXXXXX"
private const val APP_OPEN_ID     = "ca-app-pub-XXXXXXXXXXXXXXXX/XXXXXXXXXX"

object AdManager {{
    private lateinit var ctx: Context
    private var interstitial: InterstitialAd? = null
    private var appOpen: AppOpenAd? = null
    private var appOpenLoadTime = 0L

    fun init(context: Context) {{
        ctx = context.applicationContext
        MobileAds.initialize(context) {{
            Log.d("AdManager", "AdMob baslatildi")
            loadInterstitial()
            loadAppOpen()
        }}
    }}

    private fun loadInterstitial() {{
        InterstitialAd.load(ctx, INTERSTITIAL_ID, AdRequest.Builder().build(),
            object : InterstitialAdLoadCallback() {{
                override fun onAdLoaded(ad: InterstitialAd) {{ interstitial = ad }}
                override fun onAdFailedToLoad(e: LoadAdError) {{ interstitial = null }}
            }})
    }}

    fun showInterstitial(activity: Activity, onDone: () -> Unit = {{}}) {{
        val ad = interstitial
        if (ad != null) {{
            ad.fullScreenContentCallback = object : FullScreenContentCallback() {{
                override fun onAdDismissedFullScreenContent() {{ interstitial = null; loadInterstitial(); onDone() }}
                override fun onAdFailedToShowFullScreenContent(e: AdError) {{ onDone() }}
            }}
            ad.show(activity)
        }} else {{ onDone() }}
    }}

    private fun loadAppOpen() {{
        AppOpenAd.load(ctx, APP_OPEN_ID, AdRequest.Builder().build(),
            object : AppOpenAd.AppOpenAdLoadCallback() {{
                override fun onAdLoaded(ad: AppOpenAd) {{ appOpen = ad; appOpenLoadTime = System.currentTimeMillis() }}
                override fun onAdFailedToLoad(e: LoadAdError) {{ appOpen = null }}
            }})
    }}

    fun showAppOpen(activity: Activity) {{
        val ad = appOpen ?: return
        if (System.currentTimeMillis() - appOpenLoadTime > 4 * 3600_000) {{ loadAppOpen(); return }}
        ad.fullScreenContentCallback = object : FullScreenContentCallback() {{
            override fun onAdDismissedFullScreenContent() {{ appOpen = null; loadAppOpen() }}
        }}
        ad.show(activity)
    }}
}}

@Composable
fun BannerAd() {{
    AndroidView(factory = {{ ctx ->
        AdView(ctx).apply {{
            setAdSize(AdSize.BANNER)
            adUnitId = BANNER_ID
            loadAd(AdRequest.Builder().build())
        }}
    }})
}}
""")

# ── NamazApp.kt ───────────────────────────────────────────────────────────────
print("\n[7] NamazApp.kt")
write(f"{JAVA}/NamazApp.kt", f"""package {PKG}

import android.app.Application
import com.google.firebase.messaging.FirebaseMessaging
import {PKG}.data.CityManager

class NamazApp : Application() {{
    override fun onCreate() {{
        super.onCreate()
        AdManager.init(this)
        val city = CityManager.getSelected(this)
        FirebaseMessaging.getInstance().subscribeToTopic("namaz_\${{city.apiName.lowercase()}}")
    }}
}}
""")

# ── ui/theme/Color.kt ─────────────────────────────────────────────────────────
print("\n[8] ui/theme/Color.kt")
write(f"{JAVA}/ui/theme/Color.kt", f"""package {PKG}.ui.theme

import androidx.compose.ui.graphics.Color

val Emerald700   = Color(0xFF047857)
val Emerald500   = Color(0xFF10B981)
val Emerald200   = Color(0xFFA7F3D0)
val Emerald900   = Color(0xFF064E3B)
val GoldLight    = Color(0xFFFBBF24)
val GoldDark     = Color(0xFFD97706)
val NeutralDark  = Color(0xFF0F1A16)
val NeutralMid   = Color(0xFF1C2B24)
val NeutralLight = Color(0xFFF0FDF4)
val Surface      = Color(0xFFFFFFFF)
val SurfaceDark  = Color(0xFF162820)
""")

# ── ui/theme/Theme.kt ─────────────────────────────────────────────────────────
print("\n[9] ui/theme/Theme.kt")
write(f"{JAVA}/ui/theme/Theme.kt", f"""package {PKG}.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColorScheme = darkColorScheme(
    primary             = Emerald500,
    onPrimary           = Color.White,
    primaryContainer    = Emerald900,
    onPrimaryContainer  = Emerald200,
    secondary           = GoldLight,
    onSecondary         = NeutralDark,
    background          = NeutralDark,
    onBackground        = NeutralLight,
    surface             = SurfaceDark,
    onSurface           = NeutralLight,
    surfaceVariant      = NeutralMid,
    onSurfaceVariant    = Emerald200
)

private val LightColorScheme = lightColorScheme(
    primary             = Emerald700,
    onPrimary           = Color.White,
    primaryContainer    = Emerald200,
    onPrimaryContainer  = Emerald900,
    secondary           = GoldDark,
    onSecondary         = Color.White,
    background          = NeutralLight,
    onBackground        = NeutralDark,
    surface             = Surface,
    onSurface           = NeutralDark,
    surfaceVariant      = Color(0xFFDCFCE7),
    onSurfaceVariant    = Emerald900
)

@Composable
fun NamazTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {{
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme,
        typography  = Typography(),
        content     = content
    )
}}
""")

# ── ui/screens/PrayerTimesScreen.kt ──────────────────────────────────────────
print("\n[10] ui/screens/PrayerTimesScreen.kt")
write(f"{JAVA}/ui/screens/PrayerTimesScreen.kt", f"""package {PKG}.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocationCity
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import {PKG}.BannerAd
import {PKG}.data.PrayerTimes
import kotlinx.coroutines.delay
import java.util.Calendar

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PrayerTimesScreen(
    prayerTimes: PrayerTimes?,
    isLoading: Boolean,
    error: String?,
    onRefresh: () -> Unit,
    onCityClick: () -> Unit
) {{
    Scaffold(
        topBar = {{
            TopAppBar(
                title = {{ Text(prayerTimes?.city ?: "Namaz Vakitleri", fontWeight = FontWeight.Bold) }},
                actions = {{
                    IconButton(onClick = onCityClick) {{
                        Icon(Icons.Default.LocationCity, contentDescription = "şehir seç")
                    }}
                    IconButton(onClick = onRefresh, enabled = !isLoading) {{
                        Icon(Icons.Default.Refresh, contentDescription = "Yenile")
                    }}
                }},
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor      = MaterialTheme.colorScheme.primary,
                    titleContentColor   = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        }},
        bottomBar = {{ BannerAd() }}
    ) {{ padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp)
        ) {{
            Spacer(Modifier.height(12.dp))
            when {{
                isLoading -> Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {{
                    CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                }}
                error != null -> ErrorCard(error, onRefresh)
                prayerTimes != null -> {{
                    DateCard(prayerTimes.date)
                    Spacer(Modifier.height(12.dp))
                    NextPrayerCard(prayerTimes)
                    Spacer(Modifier.height(12.dp))
                    PrayerList(prayerTimes)
                }}
            }}
        }}
    }}
}}

@Composable
private fun DateCard(date: String) {{
    Surface(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.primaryContainer) {{
        Text(text = date, modifier = Modifier.padding(12.dp),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onPrimaryContainer,
            textAlign = TextAlign.Center)
    }}
}}

@Composable
private fun NextPrayerCard(times: PrayerTimes) {{
    val (label, timeStr) = remember(times) {{ nextPrayer(times) }}
    var countdown by remember {{ mutableStateOf("") }}
    LaunchedEffect(timeStr) {{
        while (true) {{ countdown = remainingTime(timeStr); delay(1000) }}
    }}
    Surface(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.primary) {{
        Column(modifier = Modifier.padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {{
            Text("Sıradaki Vakit", style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.8f))
            Spacer(Modifier.height(4.dp))
            Text(label, style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onPrimary)
            Spacer(Modifier.height(8.dp))
            Text(countdown, style = MaterialTheme.typography.displaySmall,
                fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.secondary)
        }}
    }}
}}

@Composable
private fun PrayerList(times: PrayerTimes) {{
    val now = remember {{ currentTimeStr() }}
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {{
        times.asList().forEach {{ (name, time) ->
            PrayerRow(name = name, time = time, isPassed = time <= now)
        }}
    }}
}}

@Composable
private fun PrayerRow(name: String, time: String, isPassed: Boolean) {{
    val alpha = if (isPassed) 0.5f else 1f
    Surface(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = if (isPassed) 0.5f else 1f)) {{
        Row(modifier = Modifier.padding(horizontal = 20.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically) {{
            Text(name, style = MaterialTheme.typography.titleMedium,
                fontWeight = if (!isPassed) FontWeight.SemiBold else FontWeight.Normal,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = alpha),
                modifier = Modifier.weight(1f))
            Text(time, style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary.copy(alpha = alpha))
        }}
    }}
}}

@Composable
private fun ErrorCard(error: String, onRetry: () -> Unit) {{
    Surface(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.errorContainer) {{
        Column(modifier = Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {{
            Text(error, color = MaterialTheme.colorScheme.onErrorContainer, textAlign = TextAlign.Center)
            Spacer(Modifier.height(8.dp))
            Button(onClick = onRetry) {{ Text("Tekrar Dene") }}
        }}
    }}
}}

private fun currentTimeStr(): String {{
    val cal = Calendar.getInstance()
    return "%02d:%02d".format(cal.get(Calendar.HOUR_OF_DAY), cal.get(Calendar.MINUTE))
}}

private fun nextPrayer(t: PrayerTimes): Pair<String, String> {{
    val now = currentTimeStr()
    return t.asList().firstOrNull {{ (_, time) -> time > now }} ?: t.asList().first()
}}

private fun remainingTime(target: String): String {{
    val cal = Calendar.getInstance()
    val nowMin = cal.get(Calendar.HOUR_OF_DAY) * 60 + cal.get(Calendar.MINUTE)
    val (h, m) = target.split(":").map {{ it.toInt() }}
    var diff = h * 60 + m - nowMin
    if (diff < 0) diff += 24 * 60
    return "%d:%02d".format(diff / 60, diff % 60)
}}
""")

# ── ui/screens/CitySelectScreen.kt ───────────────────────────────────────────
print("\n[11] ui/screens/CitySelectScreen.kt")
write(f"{JAVA}/ui/screens/CitySelectScreen.kt", f"""package {PKG}.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import {PKG}.data.City
import {PKG}.data.CityManager

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CitySelectScreen(
    selectedCity: City,
    onCitySelected: (City) -> Unit,
    onBack: () -> Unit
) {{
    Scaffold(
        topBar = {{
            TopAppBar(
                title = {{ Text("şehir Seç", fontWeight = FontWeight.Bold) }},
                navigationIcon = {{
                    IconButton(onClick = onBack) {{
                        Icon(Icons.Default.ArrowBack, contentDescription = "Geri")
                    }}
                }},
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor      = MaterialTheme.colorScheme.primary,
                    titleContentColor   = MaterialTheme.colorScheme.onPrimary,
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        }}
    ) {{ padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {{
            items(CityManager.cities) {{ city ->
                CityItem(city = city, isSelected = city.apiName == selectedCity.apiName,
                    onClick = {{ onCitySelected(city) }})
            }}
        }}
    }}
}}

@Composable
private fun CityItem(city: City, isSelected: Boolean, onClick: () -> Unit) {{
    Surface(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(12.dp),
        color = if (isSelected) MaterialTheme.colorScheme.primaryContainer
                else MaterialTheme.colorScheme.surfaceVariant
    ) {{
        Row(modifier = Modifier.padding(horizontal = 20.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically) {{
            Text(city.name, style = MaterialTheme.typography.titleMedium,
                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                color = if (isSelected) MaterialTheme.colorScheme.onPrimaryContainer
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f))
            if (isSelected) {{
                Icon(Icons.Default.Check, contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary)
            }}
        }}
    }}
}}
""")

# ── MainActivity.kt ───────────────────────────────────────────────────────────
print("\n[12] MainActivity.kt (guncelleniyor)")
write(f"{JAVA}/MainActivity.kt", f"""package {PKG}

import android.Manifest
import android.content.res.Configuration
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import androidx.core.view.WindowInsetsControllerCompat
import com.google.android.gms.ads.MobileAds
import com.google.android.ump.ConsentRequestParameters
import com.google.android.ump.UserMessagingPlatform
import {PKG}.data.City
import {PKG}.data.CityManager
import {PKG}.data.PrayerTimes
import {PKG}.api.AladhanApi
import {PKG}.ui.screens.CitySelectScreen
import {PKG}.ui.screens.PrayerTimesScreen
import {PKG}.ui.theme.NamazTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {{

    private val notifPerm =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) {{}}

    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)

        // Status bar / nav bar ikon rengi
        val wic = WindowInsetsControllerCompat(window, window.decorView)
        val isNight = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) ==
                Configuration.UI_MODE_NIGHT_YES
        wic.isAppearanceLightStatusBars = !isNight
        wic.isAppearanceLightNavigationBars = !isNight

        // AdMob - Ad Inspector icin burada da baslatiliyor
        MobileAds.initialize(this)

        // UMP - kullanici rizasi (AB/ABD No Fill onleme)
        val consentInfo = UserMessagingPlatform.getConsentInformation(this)
        consentInfo.requestConsentInfoUpdate(
            this, ConsentRequestParameters.Builder().build(),
            {{ UserMessagingPlatform.loadAndShowConsentFormIfRequired(this) {{}} }},
            {{}}
        )

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {{
            notifPerm.launch(Manifest.permission.POST_NOTIFICATIONS)
        }}

        setContent {{
            NamazTheme {{
                NamazNavHost()
            }}
        }}
    }}

    override fun onResume() {{
        super.onResume()
        AdManager.showAppOpen(this)
    }}
}}

@Composable
private fun NamazNavHost() {{
    val ctx = LocalContext.current
    var screen by remember {{ mutableStateOf<Screen>(Screen.PrayerTimes) }}
    var prayerTimes by remember {{ mutableStateOf<PrayerTimes?>(null) }}
    var isLoading by remember {{ mutableStateOf(false) }}
    var error by remember {{ mutableStateOf<String?>(null) }}
    var selectedCity by remember {{ mutableStateOf(CityManager.getSelected(ctx)) }}
    val scope = rememberCoroutineScope()

    fun loadTimes(city: City = selectedCity) {{
        scope.launch {{
            isLoading = true; error = null
            try {{
                prayerTimes = AladhanApi.getPrayerTimes(city.apiName)
            }} catch (e: Exception) {{
                error = "Vakitler yuklenemedi. Internet baglantinizi kontrol edin."
            }} finally {{
                isLoading = false
            }}
        }}
    }}

    LaunchedEffect(Unit) {{ loadTimes() }}

    when (screen) {{
        Screen.PrayerTimes -> PrayerTimesScreen(
            prayerTimes = prayerTimes, isLoading = isLoading, error = error,
            onRefresh = {{ loadTimes() }}, onCityClick = {{ screen = Screen.CitySelect }}
        )
        Screen.CitySelect -> CitySelectScreen(
            selectedCity = selectedCity,
            onCitySelected = {{ city ->
                CityManager.save(ctx, city)
                selectedCity = city
                loadTimes(city)
                screen = Screen.PrayerTimes
            }},
            onBack = {{ screen = Screen.PrayerTimes }}
        )
    }}
}}

private sealed class Screen {{
    object PrayerTimes : Screen()
    object CitySelect  : Screen()
}}
""")

# ── app/build.gradle ──────────────────────────────────────────────────────────
print("\n[13] app/build.gradle (guncelleniyor)")
new_app_build = f"""plugins {{
    id 'com.android.application'
    id 'org.jetbrains.kotlin.android'
    id 'com.google.gms.google-services'
}}

android {{
    namespace '{PKG}'
    compileSdk 35

    defaultConfig {{
        applicationId "{PKG}"
        minSdk 26
        targetSdk 35
        versionCode 1
        versionName "1.0"
    }}

    buildTypes {{
        release {{
            minifyEnabled false
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt')
        }}
    }}

    compileOptions {{
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }}
    kotlinOptions {{ jvmTarget = '17' }}

    buildFeatures {{
        compose true
        buildConfig true
    }}
    composeOptions {{ kotlinCompilerExtensionVersion '1.5.14' }}

    packaging {{
        resources {{ excludes += '/META-INF/{{AL2.0,LGPL2.1}}' }}
        jniLibs {{ useLegacyPackaging = false }}
    }}
}}

configurations.all {{
    resolutionStrategy {{
        force 'androidx.graphics:graphics-path:1.1.0-rc01'
    }}
}}

dependencies {{
    implementation platform('androidx.compose:compose-bom:2024.09.00')
    implementation 'androidx.compose.ui:ui'
    implementation 'androidx.compose.material3:material3'
    implementation 'androidx.compose.material:material-icons-extended'
    implementation 'androidx.activity:activity-compose:1.8.2'
    implementation 'androidx.lifecycle:lifecycle-runtime-ktx:2.7.0'
    implementation 'androidx.core:core-ktx:1.12.0'

    // Firebase FCM
    implementation platform('com.google.firebase:firebase-bom:33.7.0')
    implementation 'com.google.firebase:firebase-messaging-ktx'

    // AdMob - 23.3.0 kullan (23.6+ uyumsuz)
    implementation 'com.google.android.gms:play-services-ads:23.3.0'

    // UMP - kullanici rizasi
    implementation 'com.google.android.ump:user-messaging-platform:3.1.0'

    // Retrofit + Gson
    implementation 'com.squareup.retrofit2:retrofit:2.9.0'
    implementation 'com.squareup.retrofit2:converter-gson:2.9.0'

    // Coroutines
    implementation 'org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3'
    implementation 'org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.7.3'
}}
"""
write(f"{BASE}/app/build.gradle", new_app_build)

# ── build.gradle (proje) ──────────────────────────────────────────────────────
print("\n[14] build.gradle (google-services ekleniyor)")
patch_file(f"{BASE}/build.gradle", [(
    "    id 'org.jetbrains.kotlin.android' version '1.9.24' apply false\n}",
    "    id 'org.jetbrains.kotlin.android' version '1.9.24' apply false\n    id 'com.google.gms.google-services' version '4.4.1' apply false\n}"
)])

# ── AndroidManifest.xml ───────────────────────────────────────────────────────
print("\n[15] AndroidManifest.xml (guncelleniyor)")
new_manifest = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />

    <application
        android:name=".NamazApp"
        android:allowBackup="true"
        android:extractNativeLibs="false"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:theme="@style/Theme.App">

        <meta-data
            android:name="com.google.android.gms.ads.APPLICATION_ID"
            android:value="ca-app-pub-XXXXXXXXXXXXXXXX~XXXXXXXXXX"/>

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:screenOrientation="portrait"
            android:windowSoftInputMode="adjustResize">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <service
            android:name=".NamazFCMService"
            android:exported="false">
            <intent-filter>
                <action android:name="com.google.firebase.MESSAGING_EVENT" />
            </intent-filter>
        </service>

    </application>
</manifest>
"""
write(f"{SRC}/AndroidManifest.xml", new_manifest)

# ── res/values/strings.xml ────────────────────────────────────────────────────
print("\n[16] res/values/strings.xml")
write(f"{SRC}/res/values/strings.xml", """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Namaz Vakitleri</string>
</resources>
""")

# ── res/values/themes.xml ─────────────────────────────────────────────────────
print("\n[17] res/values/themes.xml (Material3)")
write(f"{SRC}/res/values/themes.xml", """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.App" parent="Theme.Material3.DayNight.NoActionBar">
        <item name="android:statusBarColor">@android:color/transparent</item>
    </style>
</resources>
""")

print("""
=== TAMAMLANDI ===

SONRAKI ADIM:
  google-services.json dosyasini Firebase konsolundan indir:
  cp /sdcard/Download/google-services.json app/

Sonra build al:
  cd ~/namazvakitleri && ./gradlew assembleDebug
  (veya: prj d)
""")
