package com.hakanerbas.namaz.data

import android.content.Context
import com.google.firebase.messaging.FirebaseMessaging

object CityManager {

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

    fun getSelected(ctx: Context): City {
        val prefs = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val name = prefs.getString(KEY_CITY, "İstanbul") ?: "İstanbul"
        val api  = prefs.getString(KEY_CITY_API, "Istanbul") ?: "Istanbul"
        return City(name, api)
    }

    fun save(ctx: Context, city: City) {
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putString(KEY_CITY, city.name)
            .putString(KEY_CITY_API, city.apiName)
            .apply()

        // FCM topic: önceki şehirden çık, yenisine gir
        val prev = getSelected(ctx)
        FirebaseMessaging.getInstance().unsubscribeFromTopic("namaz_${prev.apiName.lowercase()}")
        FirebaseMessaging.getInstance().subscribeToTopic("namaz_${city.apiName.lowercase()}")
    }
}
