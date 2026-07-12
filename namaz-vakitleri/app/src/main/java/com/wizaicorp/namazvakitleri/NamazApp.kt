package com.wizaicorp.namazvakitleri

import android.app.Application
import com.google.firebase.messaging.FirebaseMessaging
import com.wizaicorp.namazvakitleri.data.CityManager

class NamazApp : Application() {
    override fun onCreate() {
        super.onCreate()
        AdManager.init(this)
        val city = CityManager.getSelected(this)
        FirebaseMessaging.getInstance().subscribeToTopic(CityManager.topicFor(city))
    }
}
