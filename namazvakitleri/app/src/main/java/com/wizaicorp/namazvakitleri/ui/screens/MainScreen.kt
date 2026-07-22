package com.wizaicorp.namazvakitleri.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Explore
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.LocationCity
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.R
import com.wizaicorp.namazvakitleri.BannerAd
import com.wizaicorp.namazvakitleri.Screen
import com.wizaicorp.namazvakitleri.data.City
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.PrayerTimes

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    currentTab: Screen,
    onTabChange: (Screen) -> Unit,
    prayerTimes: PrayerTimes?,
    isLoading: Boolean,
    error: String?,
    isOffline: Boolean,
    selectedCity: City,
    onRefresh: () -> Unit,
    onCityClick: () -> Unit,
    onSettingsClick: () -> Unit,
    onOpen: (Screen) -> Unit
) {
    val topBarTitle = when (currentTab) {
        Screen.PrayerTimes -> prayerTimes?.city ?: Lang.get("tab_times")
        Screen.Qibla       -> Lang.get("tab_qibla")
        Screen.Calendar    -> Lang.get("tab_calendar")
        Screen.More        -> Lang.get("tab_more")
        else               -> Lang.get("tab_times")
    }

    Scaffold(
        modifier = Modifier.navigationBarsPadding(),
        topBar = {
            TopAppBar(
                navigationIcon = {
                    Icon(
                        painter = painterResource(R.drawable.mosque_logo),
                        contentDescription = null,
                        modifier = Modifier
                            .padding(start = 8.dp)
                            .size(36.dp)
                            .clip(CircleShape),
                        tint = Color.Unspecified
                    )
                },
                title = { Text(topBarTitle, fontWeight = FontWeight.Bold) },
                actions = {
                    if (currentTab == Screen.PrayerTimes) {
                        IconButton(onClick = onSettingsClick) {
                            Icon(Icons.Default.Notifications, contentDescription = Lang.get("notif_settings"))
                        }
                        IconButton(onClick = onCityClick) {
                            Icon(Icons.Default.LocationCity, contentDescription = Lang.get("change_city"))
                        }
                        IconButton(onClick = onRefresh, enabled = !isLoading) {
                            Icon(Icons.Default.Refresh, contentDescription = null)
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor         = MaterialTheme.colorScheme.primary,
                    titleContentColor      = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        },
        bottomBar = {
            Column {
                NavigationBar {
                    NavigationBarItem(
                        selected = currentTab == Screen.PrayerTimes,
                        onClick  = { onTabChange(Screen.PrayerTimes) },
                        icon     = { Icon(Icons.Default.Home, contentDescription = null) },
                        label    = { Text(Lang.get("tab_times")) }
                    )
                    NavigationBarItem(
                        selected = currentTab == Screen.Qibla,
                        onClick  = { onTabChange(Screen.Qibla) },
                        icon     = { Icon(Icons.Default.Explore, contentDescription = null) },
                        label    = { Text(Lang.get("tab_qibla")) }
                    )
                    NavigationBarItem(
                        selected = currentTab == Screen.Calendar,
                        onClick  = { onTabChange(Screen.Calendar) },
                        icon     = { Icon(Icons.Default.DateRange, contentDescription = null) },
                        label    = { Text(Lang.get("tab_calendar")) }
                    )
                    NavigationBarItem(
                        selected = currentTab == Screen.More,
                        onClick  = { onTabChange(Screen.More) },
                        icon     = { Icon(Icons.Default.Apps, contentDescription = null) },
                        label    = { Text(Lang.get("tab_more")) }
                    )
                }
                BannerAd()
            }
        }
    ) { padding ->
        when (currentTab) {
            Screen.PrayerTimes -> PrayerTimesContent(
                prayerTimes = prayerTimes,
                isLoading   = isLoading,
                error       = error,
                isOffline   = isOffline,
                onRefresh   = onRefresh,
                modifier    = Modifier.padding(padding)
            )
            Screen.Qibla    -> QiblaContent(modifier = Modifier.padding(padding))
            Screen.Calendar -> CalendarContent(city = selectedCity, modifier = Modifier.padding(padding))
            Screen.More     -> MoreContent(
                prayerTimes = prayerTimes,
                onOpen      = onOpen,
                modifier    = Modifier.padding(padding)
            )
            else            -> {}
        }
    }
}
