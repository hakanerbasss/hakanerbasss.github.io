package com.wizaicorp.namazvakitleri

import android.app.Application
import com.google.firebase.messaging.FirebaseMessaging
import com.wizaicorp.namazvakitleri.data.CityManager
import com.wizaicorp.namazvakitleri.data.Lang

class NamazApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Lang.init(this)
        AdManager.init(this)
        val city = CityManager.getSelected(this)
        FirebaseMessaging.getInstance().subscribeToTopic(CityManager.topicFor(city))
        // Gece yarisi yenileme zinciri her acilista garanti altina alinir
        AlarmScheduler.scheduleDailyRefresh(this)
    }
}
