package com.wizaicorp.namazvakitleri

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
import com.wizaicorp.namazvakitleri.data.City
import com.wizaicorp.namazvakitleri.data.CityManager
import com.wizaicorp.namazvakitleri.data.PrayerTimes
import com.wizaicorp.namazvakitleri.AlarmScheduler
import com.wizaicorp.namazvakitleri.api.AladhanApi
import com.wizaicorp.namazvakitleri.ui.screens.CitySelectScreen
import com.wizaicorp.namazvakitleri.ui.screens.SettingsScreen
import com.wizaicorp.namazvakitleri.ui.screens.PrayerTimesScreen
import com.wizaicorp.namazvakitleri.ui.theme.NamazTheme
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
}

@Composable
private fun NamazNavHost() {
    val ctx = LocalContext.current
    var screen by remember { mutableStateOf<Screen>(Screen.PrayerTimes) }
    var prayerTimes by remember { mutableStateOf<PrayerTimes?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var selectedCity by remember { mutableStateOf(CityManager.getSelected(ctx)) }
    val scope = rememberCoroutineScope()

    fun loadTimes(city: City = selectedCity) {
        scope.launch {
            isLoading = true; error = null
            try {
                prayerTimes = AladhanApi.getPrayerTimes(city.apiName, city.country)
                AlarmScheduler.schedule(ctx, prayerTimes!!)
            } catch (e: Exception) {
                error = "Vakitler yuklenemedi. Internet baglantinizi kontrol edin."
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(Unit) { loadTimes() }

    when (screen) {
        Screen.PrayerTimes -> PrayerTimesScreen(
            prayerTimes = prayerTimes, isLoading = isLoading, error = error,
            onRefresh = { loadTimes() },
            onCityClick = { screen = Screen.CitySelect },
            onSettingsClick = { screen = Screen.Settings }
        )
        Screen.Settings    -> SettingsScreen(onBack = { screen = Screen.PrayerTimes })
        Screen.CitySelect -> CitySelectScreen(
            selectedCity = selectedCity,
            onCitySelected = { city ->
                CityManager.save(ctx, city)
                selectedCity = city
                loadTimes(city)
                screen = Screen.PrayerTimes
            },
            onBack = { screen = Screen.PrayerTimes }
        )
    }
}

private sealed class Screen {
    object PrayerTimes : Screen()
    object CitySelect  : Screen()
    object Settings    : Screen()
}
