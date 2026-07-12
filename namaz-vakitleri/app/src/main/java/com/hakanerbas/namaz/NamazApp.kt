package com.hakanerbas.namaz

import android.app.Application
import com.google.firebase.messaging.FirebaseMessaging
import com.hakanerbas.namaz.data.CityManager

class NamazApp : Application() {

    override fun onCreate() {
        super.onCreate()
        AdManager.init(this)
        subscribeToCity()
    }

    private fun subscribeToCity() {
        val city = CityManager.getSelected(this)
        FirebaseMessaging.getInstance()
            .subscribeToTopic("namaz_${city.apiName.lowercase()}")
    }
}
