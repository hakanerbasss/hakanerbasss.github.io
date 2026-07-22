package com.wizaicorp.namazvakitleri

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.wizaicorp.namazvakitleri.api.AladhanApi
import com.wizaicorp.namazvakitleri.data.CityManager
import com.wizaicorp.namazvakitleri.data.TimesCache
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Uygulama hic acilmasa bile bildirimlerin calismasini saglar:
 * - Her gece 00:05'te yeni gunun alarmlarini kurar
 * - Telefon yeniden basladiginda alarmlari geri yukler
 * - Saat/dilim degisikliklerinde yeniden kurar
 * Vakitler once onbellekten okunur; yoksa aga cikilir.
 */
class DailyReceiver : BroadcastReceiver() {

    companion object {
        const val ACTION_DAILY = "com.wizaicorp.namazvakitleri.DAILY_REFRESH"
    }

    override fun onReceive(ctx: Context, intent: Intent) {
        // Reboot sonrasi haber kontrol zincirinin de ayakta oldugundan emin ol
        AlarmScheduler.scheduleNewsCheck(ctx)

        val cached = TimesCache.getToday(ctx)
        if (cached != null) {
            AlarmScheduler.schedule(ctx, cached)
            TimesCache.cleanup(ctx)
            return
        }

        // Onbellekte yok - aga cikip bugunu cek (goAsync ile ~10 sn suremiz var)
        val pending = goAsync()
        val city = CityManager.getSelected(ctx)
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val times = AladhanApi.getPrayerTimes(city.apiName, city.country)
                    .copy(city = city.name)
                TimesCache.saveDay(ctx, TimesCache.isoToday(), times)
                AlarmScheduler.schedule(ctx, times)
            } catch (e: Exception) {
                // Ag yok - yarin gece tekrar denenir, yine de zinciri koru
                AlarmScheduler.scheduleDailyRefresh(ctx)
            } finally {
                pending.finish()
            }
        }
    }
}
