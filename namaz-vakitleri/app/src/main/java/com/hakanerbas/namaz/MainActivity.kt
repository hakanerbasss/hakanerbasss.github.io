package com.hakanerbas.namaz

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
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
                error = "Vakitler yüklenemedi. Lütfen internet bağlantınızı kontrol edin."
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
