package com.bluechip.finance.ui.components

import androidx.compose.runtime.mutableStateOf
import com.google.firebase.ktx.Firebase
import com.google.firebase.remoteconfig.ktx.remoteConfig
import com.google.firebase.remoteconfig.ktx.remoteConfigSettings

object RemoteConfigManager {

    private val remoteConfig = Firebase.remoteConfig
    var isAdEnabled = mutableStateOf(false)
    var bannerUnitId = mutableStateOf("ca-app-pub-7820582813827252/8522252459")

    init {
        val settings = remoteConfigSettings {
            minimumFetchIntervalInSeconds = 3600
        }
        remoteConfig.setConfigSettingsAsync(settings)
        remoteConfig.setDefaultsAsync(
            mapOf(
                "admob_enabled" to true,
                "admob_banner_unit_id" to "ca-app-pub-7820582813827252/8522252459"
            )
        )
        remoteConfig.fetchAndActivate().addOnCompleteListener { task ->
            if (task.isSuccessful) {
                isAdEnabled.value = remoteConfig.getBoolean("admob_enabled")
                bannerUnitId.value = remoteConfig.getString("admob_banner_unit_id")
            }
        }
    }
}
