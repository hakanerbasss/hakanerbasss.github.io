package com.wizaicorp.namazvakitleri

import android.Manifest
import android.app.Activity
import android.content.res.Configuration
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import androidx.core.view.WindowInsetsControllerCompat
import com.google.android.gms.ads.MobileAds
import com.google.android.ump.ConsentRequestParameters
import com.google.android.ump.UserMessagingPlatform
import com.wizaicorp.namazvakitleri.data.City
import com.wizaicorp.namazvakitleri.data.CityManager
import com.wizaicorp.namazvakitleri.data.PrayerTimes
import com.wizaicorp.namazvakitleri.data.TimesCache
import com.wizaicorp.namazvakitleri.api.AladhanApi
import com.wizaicorp.namazvakitleri.ui.screens.ApiSettingsScreen
import com.wizaicorp.namazvakitleri.ui.screens.AssistantScreen
import com.wizaicorp.namazvakitleri.ui.screens.CitySelectScreen
import com.wizaicorp.namazvakitleri.ui.screens.EducationDetailScreen
import com.wizaicorp.namazvakitleri.ui.screens.EducationScreen
import com.wizaicorp.namazvakitleri.ui.screens.EsmaScreen
import com.wizaicorp.namazvakitleri.ui.screens.NewsScreen
import com.wizaicorp.namazvakitleri.ui.screens.HolyDaysScreen
import com.wizaicorp.namazvakitleri.ui.screens.KazaScreen
import com.wizaicorp.namazvakitleri.ui.screens.LibraryDetailScreen
import com.wizaicorp.namazvakitleri.ui.screens.LibraryScreen
import com.wizaicorp.namazvakitleri.ui.screens.MainScreen
import com.wizaicorp.namazvakitleri.ui.screens.SettingsScreen
import com.wizaicorp.namazvakitleri.ui.screens.ZikirScreen
import com.wizaicorp.namazvakitleri.ui.theme.NamazTheme
import com.wizaicorp.namazvakitleri.data.Lang
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private val notifPerm =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
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
            { UserMessagingPlatform.loadAndShowConsentFormIfRequired(this) {} },
            {}
        )

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            notifPerm.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        maybeAskReview()

        setContent {
            NamazTheme {
                NamazNavHost()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        AdManager.showAppOpen(this)
    }

    override fun onPause() {
        super.onPause()
        AdManager.notePause()
    }

    /**
     * 7. acilista Play'in resmi uygulama ici degerlendirme penceresini gosterir.
     * Bir kez sorulur; Play kotasi doluysa sessizce gecilir, hata firlatmaz.
     */
    private fun maybeAskReview() {
        try {
            val p = getSharedPreferences("namaz_prefs", MODE_PRIVATE)
            val opens = p.getInt("open_count", 0) + 1
            p.edit().putInt("open_count", opens).apply()
            if (opens < 7 || p.getBoolean("review_asked", false)) return
            p.edit().putBoolean("review_asked", true).apply()

            val mgr = com.google.android.play.core.review.ReviewManagerFactory.create(this)
            mgr.requestReviewFlow().addOnSuccessListener { info ->
                mgr.launchReviewFlow(this, info)
            }
        } catch (e: Exception) { /* degerlendirme akisi kritik degil */ }
    }
}

@Composable
private fun NamazNavHost() {
    val ctx = LocalContext.current
    var screen by remember { mutableStateOf<Screen>(Screen.PrayerTimes) }
    var prayerTimes by remember { mutableStateOf<PrayerTimes?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var isOffline by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var selectedCity by remember { mutableStateOf(CityManager.getSelected(ctx)) }
    val scope = rememberCoroutineScope()

    fun loadTimes(city: City = selectedCity) {
        scope.launch {
            isLoading = true; error = null
            try {
                val t = AladhanApi.getPrayerTimes(city.apiName, city.country).copy(city = city.name)
                prayerTimes = t
                isOffline = false
                TimesCache.saveDay(ctx, TimesCache.isoToday(), t)
                AlarmScheduler.schedule(ctx, t)
            } catch (e: Exception) {
                // Cevrimdisi: onbellekten gosterelim
                val cached = TimesCache.getToday(ctx)
                if (cached != null) {
                    prayerTimes = cached
                    isOffline = true
                    AlarmScheduler.schedule(ctx, cached)
                } else {
                    error = Lang.get("err_load")
                }
            } finally {
                isLoading = false
            }
        }
    }

    // Alt ekrandan ana sekmeye donus + gecislerde frekans korumali interstitial
    fun goTab(tab: Screen) {
        screen = tab
        (ctx as? Activity)?.let { AdManager.maybeShowInterstitial(it) }
    }

    LaunchedEffect(Unit) { loadTimes() }

    // Geri tusu: uygulamadan cikmak yerine ust ekrana doner
    BackHandler(enabled = screen != Screen.PrayerTimes) {
        screen = when (screen) {
            is Screen.LibDetail -> Screen.Library
            is Screen.EduDetail -> Screen.Education
            Screen.Library, Screen.Education, Screen.Zikir, Screen.Kaza,
            Screen.HolyDays, Screen.Esma, Screen.News, Screen.Assistant,
            Screen.ApiSettings, Screen.Settings -> Screen.More
            else -> Screen.PrayerTimes
        }
    }

    when (screen) {
        Screen.PrayerTimes,
        Screen.Qibla,
        Screen.Calendar,
        Screen.More -> MainScreen(
            currentTab      = screen,
            onTabChange     = { goTab(it) },
            prayerTimes     = prayerTimes,
            isLoading       = isLoading,
            error           = error,
            isOffline       = isOffline,
            selectedCity    = selectedCity,
            onRefresh       = { loadTimes() },
            onCityClick     = { screen = Screen.CitySelect },
            onSettingsClick = { screen = Screen.Settings },
            onOpen          = { screen = it }
        )
        Screen.Settings -> SettingsScreen(onBack = { goTab(Screen.More) })
        Screen.Library  -> LibraryScreen(
            onOpen = { item -> screen = Screen.LibDetail(item) },
            onBack = { goTab(Screen.More) }
        )
        is Screen.LibDetail -> LibraryDetailScreen(
            item = (screen as Screen.LibDetail).item,
            onBack = { screen = Screen.Library }
        )
        Screen.Education -> EducationScreen(
            onOpen = { topic -> screen = Screen.EduDetail(topic) },
            onBack = { goTab(Screen.More) }
        )
        is Screen.EduDetail -> EducationDetailScreen(
            topic = (screen as Screen.EduDetail).topic,
            onBack = { screen = Screen.Education }
        )
        Screen.News        -> NewsScreen(onBack = { goTab(Screen.More) })
        Screen.Assistant   -> AssistantScreen(onBack = { goTab(Screen.More) })
        Screen.ApiSettings -> ApiSettingsScreen(onBack = { goTab(Screen.More) })
        Screen.Zikir    -> ZikirScreen(onBack = { goTab(Screen.More) })
        Screen.Kaza     -> KazaScreen(onBack = { goTab(Screen.More) })
        Screen.HolyDays -> HolyDaysScreen(onBack = { goTab(Screen.More) })
        Screen.Esma     -> EsmaScreen(onBack = { goTab(Screen.More) })
        Screen.CitySelect -> CitySelectScreen(
            selectedCity = selectedCity,
            onCitySelected = { city ->
                CityManager.save(ctx, city)
                selectedCity = city
                loadTimes(city)
                screen = Screen.PrayerTimes
            },
            onBack = { goTab(Screen.PrayerTimes) }
        )
    }
}

sealed class Screen {
    object PrayerTimes : Screen()
    object Qibla       : Screen()
    object Calendar    : Screen()
    object More        : Screen()
    object CitySelect  : Screen()
    object Settings    : Screen()
    object Zikir       : Screen()
    object Kaza        : Screen()
    object HolyDays    : Screen()
    object Esma        : Screen()
    object Library     : Screen()
    object News        : Screen()
    object Assistant   : Screen()
    object ApiSettings : Screen()
    data class LibDetail(val item: com.wizaicorp.namazvakitleri.data.LibraryItem) : Screen()
    object Education   : Screen()
    data class EduDetail(val topic: com.wizaicorp.namazvakitleri.data.EduTopic) : Screen()
}
