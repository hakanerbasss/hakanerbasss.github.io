package com.hakanerbas.namaz

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
import com.hakanerbas.namaz.api.AladhanApi
import com.hakanerbas.namaz.data.City
import com.hakanerbas.namaz.data.CityManager
import com.hakanerbas.namaz.data.PrayerTimes
import com.hakanerbas.namaz.ui.screens.CitySelectScreen
import com.hakanerbas.namaz.ui.screens.PrayerTimesScreen
import com.hakanerbas.namaz.ui.theme.NamazTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Status bar / nav bar ikon rengi — aydınlık temada siyah, karanlıkta beyaz
        val wic = WindowInsetsControllerCompat(window, window.decorView)
        val isNight = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) ==
                Configuration.UI_MODE_NIGHT_YES
        wic.isAppearanceLightStatusBars = !isNight
        wic.isAppearanceLightNavigationBars = !isNight

        // AdMob — Ad Inspector için burada da başlat
        MobileAds.initialize(this)

        // UMP — kullanıcı rızası (AB/ABD kullanıcıları için No Fill'i önler)
        val consentInfo = UserMessagingPlatform.getConsentInformation(this)
        val consentParams = ConsentRequestParameters.Builder().build()
        consentInfo.requestConsentInfoUpdate(this, consentParams, {
            UserMessagingPlatform.loadAndShowConsentFormIfRequired(this) {}
        }, {})

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
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
            isLoading = true
            error = null
            try {
                prayerTimes = AladhanApi.getPrayerTimes(city.apiName)
            } catch (e: Exception) {
                error = "Vakitler yuklenemedi. Lutfen internet baglantinizi kontrol edin."
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(Unit) { loadTimes() }

    when (screen) {
        Screen.PrayerTimes -> PrayerTimesScreen(
            prayerTimes = prayerTimes,
            isLoading   = isLoading,
            error       = error,
            onRefresh   = { loadTimes() },
            onCityClick = { screen = Screen.CitySelect }
        )
        Screen.CitySelect -> CitySelectScreen(
            selectedCity   = selectedCity,
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
}
