package com.wizaicorp.namazvakitleri

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import com.wizaicorp.namazvakitleri.data.HolyDays
import com.wizaicorp.namazvakitleri.data.Lang
import com.wizaicorp.namazvakitleri.data.TimesCache
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

class PrayerWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(ctx: Context, mgr: AppWidgetManager, ids: IntArray) {
        ids.forEach { render(ctx, mgr, it) }
    }

    override fun onEnabled(ctx: Context) {
        AlarmScheduler.scheduleDailyRefresh(ctx)
    }

    companion object {

        fun updateAll(ctx: Context) {
            try {
                val mgr = AppWidgetManager.getInstance(ctx)
                val ids = mgr.getAppWidgetIds(ComponentName(ctx, PrayerWidgetProvider::class.java))
                ids.forEach { render(ctx, mgr, it) }
            } catch (e: Exception) { /* widget yoksa sessizce gec */ }
        }

        private fun render(ctx: Context, mgr: AppWidgetManager, widgetId: Int) {
            val rv = RemoteViews(ctx.packageName, R.layout.widget_prayer)
            val times = TimesCache.getToday(ctx)

            // Tarih satiri: miladi + hicri
            try {
                val locale = if (Lang.code == "tr") Locale("tr") else Locale.ENGLISH
                val miladi = SimpleDateFormat("d MMMM", locale).format(Date())
                rv.setTextViewText(R.id.w_date, "$miladi  •  ${HolyDays.hijriToday()}")
            } catch (e: Exception) {
                rv.setTextViewText(R.id.w_date, "")
            }

            if (times == null) {
                rv.setTextViewText(R.id.w_header, ctx.getString(R.string.app_name))
            } else {
                val list = listOf(
                    "p_imsak"  to times.imsak,
                    "p_gunes"  to times.gunes,
                    "p_ogle"   to times.ogle,
                    "p_ikindi" to times.ikindi,
                    "p_aksam"  to times.aksam,
                    "p_yatsi"  to times.yatsi
                )
                val nameIds = listOf(R.id.w_n1, R.id.w_n2, R.id.w_n3, R.id.w_n4, R.id.w_n5, R.id.w_n6)
                val timeIds = listOf(R.id.w_t1, R.id.w_t2, R.id.w_t3, R.id.w_t4, R.id.w_t5, R.id.w_t6)

                val cal = Calendar.getInstance()
                val now = "%02d:%02d".format(cal.get(Calendar.HOUR_OF_DAY), cal.get(Calendar.MINUTE))
                val nextIdx = list.indexOfFirst { it.second > now }.let { if (it < 0) 0 else it }

                list.forEachIndexed { i, (nameKey, time) ->
                    rv.setTextViewText(nameIds[i], Lang.get(nameKey))
                    rv.setTextViewText(timeIds[i], time)
                    val highlight = i == nextIdx
                    rv.setTextColor(timeIds[i], if (highlight) 0xFFFBBF24.toInt() else 0xFFFFFFFF.toInt())
                    rv.setTextColor(nameIds[i], if (highlight) 0xFFFBBF24.toInt() else 0xFFB7E4C7.toInt())
                }

                val (nextKey, nextTime) = list[nextIdx]
                rv.setTextViewText(
                    R.id.w_header,
                    "${times.city}  •  ${Lang.get("w_next")}: ${Lang.get(nextKey)} $nextTime"
                )
            }

            val pi = PendingIntent.getActivity(
                ctx, 0,
                Intent(ctx, MainActivity::class.java),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            rv.setOnClickPendingIntent(R.id.w_root, pi)

            mgr.updateAppWidget(widgetId, rv)
        }
    }
}
