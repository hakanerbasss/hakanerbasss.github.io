package com.bluechip.finance.util

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys

object DeepSeekKeyManager {

    private const val PREFS = "deepseek_secure_prefs"
    private const val KEY   = "api_key"

    private fun prefs(context: Context) = EncryptedSharedPreferences.create(
        PREFS,
        MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC),
        context,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    fun getKey(context: Context): String =
        runCatching { prefs(context).getString(KEY, "") ?: "" }.getOrDefault("")

    fun saveKey(context: Context, apiKey: String) {
        runCatching { prefs(context).edit().putString(KEY, apiKey.trim()).apply() }
    }

    fun hasKey(context: Context): Boolean = getKey(context).isNotBlank()

    fun clearKey(context: Context) {
        runCatching { prefs(context).edit().remove(KEY).apply() }
    }
}
