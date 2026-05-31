package com.bluechip.finance

import android.content.Context

// WorkManager yerine AlarmManager kullanılıyor
// Bu dosya geriye dönük uyumluluk için tutuldu
object NotificationWorker {
    const val CHANNEL_SALARY  = NotificationReceiver.CHANNEL_SALARY
    const val CHANNEL_PAYMENT = NotificationReceiver.CHANNEL_PAYMENT
    const val CHANNEL_INCOME  = NotificationReceiver.CHANNEL_INCOME

    fun createChannels(context: Context) = NotificationReceiver.createChannels(context)
    fun schedule(context: Context) = NotificationScheduler.schedule(context)
    fun runNow(context: Context) = NotificationScheduler.scheduleTest(context)
}
