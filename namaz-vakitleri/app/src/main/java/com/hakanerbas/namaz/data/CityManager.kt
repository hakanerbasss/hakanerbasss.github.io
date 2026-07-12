package com.hakanerbas.namaz.data

import android.content.Context
import com.google.firebase.messaging.FirebaseMessaging

object CityManager {

    private const val PREF = "namaz_prefs"
    private const val KEY_API     = "city_api"
    private const val KEY_DISPLAY = "city_display"
    private const val KEY_COUNTRY = "city_country"
    private val DEFAULT = City("İstanbul", "Istanbul", "Turkey")

    fun getSelected(ctx: Context): City {
        val p = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val api     = p.getString(KEY_API,     DEFAULT.apiName) ?: DEFAULT.apiName
        val display = p.getString(KEY_DISPLAY, api)             ?: api
        val country = p.getString(KEY_COUNTRY, DEFAULT.country) ?: DEFAULT.country
        return City(display, api, country)
    }

    fun save(ctx: Context, city: City) {
        val prev = getSelected(ctx)
        FirebaseMessaging.getInstance().unsubscribeFromTopic(topicFor(prev))
        FirebaseMessaging.getInstance().subscribeToTopic(topicFor(city))
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putString(KEY_API,     city.apiName)
            .putString(KEY_DISPLAY, city.name)
            .putString(KEY_COUNTRY, city.country)
            .apply()
    }

    fun topicFor(city: City): String =
        "namaz_${city.apiName.lowercase().replace(" ", "_")}_${city.country.lowercase().replace(" ", "_")}"
}
