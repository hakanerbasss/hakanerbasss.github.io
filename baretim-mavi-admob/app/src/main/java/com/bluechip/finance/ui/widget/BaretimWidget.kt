package com.bluechip.finance.ui.widget

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import com.bluechip.finance.R
import com.bluechip.finance.data.ProfileManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.net.URL
import java.text.SimpleDateFormat
import java.util.*

class BaretimWidget : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        appWidgetIds.forEach { updateWidget(context, appWidgetManager, it) }
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
    }
}

fun updateWidget(context: Context, appWidgetManager: AppWidgetManager, widgetId: Int) {
    val views = RemoteViews(context.packageName, R.layout.widget_layout)

    // Aninda goster: saat + placeholder
    val time = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
    views.setTextViewText(R.id.widget_time, time)
    views.setTextViewText(R.id.widget_usd,  "...")
    views.setTextViewText(R.id.widget_eur,  "...")
    views.setTextViewText(R.id.widget_gold,  "...")

    // Profil bilgisi
    val profile = ProfileManager(context).load()
    if (profile.isLoggedIn && profile.grossSalary > 0) {
        val name   = if (profile.name.isNotBlank()) profile.name else "Profil"
        val salary = String.format("%,.0f", profile.grossSalary).replace(',', '.')
        views.setTextViewText(R.id.widget_profile, "$name — ${salary}\u20ba brut")
        views.setViewVisibility(R.id.widget_profile, android.view.View.VISIBLE)
    } else {
        views.setViewVisibility(R.id.widget_profile, android.view.View.GONE)
    }

    appWidgetManager.updateAppWidget(widgetId, views)

    // Arka planda doviz cek — IO thread, Main thread yok
    CoroutineScope(Dispatchers.IO).launch {
        var usd  = "?"
        var eur  = "?"
        var gold = "?"
        var usdRate = 38.5

        try {
            val tcmb = URL("https://www.tcmb.gov.tr/kurlar/today.xml").readText()
            val usdMatch = Regex(
                "<Currency[^>]*CurrencyCode=\"USD\"[^>]*>.*?<ForexSelling>([0-9.]+)</ForexSelling>",
                RegexOption.DOT_MATCHES_ALL
            ).find(tcmb)
            val eurMatch = Regex(
                "<Currency[^>]*CurrencyCode=\"EUR\"[^>]*>.*?<ForexSelling>([0-9.]+)</ForexSelling>",
                RegexOption.DOT_MATCHES_ALL
            ).find(tcmb)
            if (usdMatch != null) {
                usdRate = usdMatch.groupValues[1].toDouble()
                usd = "USD: " + formatW(usdRate) + "TL"
            }
            if (eurMatch != null) {
                eur = "EUR: " + formatW(eurMatch.groupValues[1].toDouble()) + "TL"
            }
        } catch (_: Exception) {}

        try {
            val crypto = URL(
                "https://api.coingecko.com/api/v3/simple/price?ids=tether-gold&vs_currencies=usd"
            ).readText()
            val obj     = JSONObject(crypto)
            val goldUsd = obj.getJSONObject("tether-gold").getDouble("usd")
            gold = "Altin: " + formatW(goldUsd * usdRate) + "TL"
        } catch (_: Exception) {}

        // withContext(Main) YOK — appWidgetManager thread-safe
        val updated = RemoteViews(context.packageName, R.layout.widget_layout)
        val t2 = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
        updated.setTextViewText(R.id.widget_time, t2)
        updated.setTextViewText(R.id.widget_usd,  usd)
        updated.setTextViewText(R.id.widget_eur,  eur)
        updated.setTextViewText(R.id.widget_gold, gold)

        // Profil tekrar set et (yeni views objesi)
        if (profile.isLoggedIn && profile.grossSalary > 0) {
            val name   = if (profile.name.isNotBlank()) profile.name else "Profil"
            val salary = String.format("%,.0f", profile.grossSalary).replace(',', '.')
            updated.setTextViewText(R.id.widget_profile, "$name — ${salary}\u20ba brut")
            updated.setViewVisibility(R.id.widget_profile, android.view.View.VISIBLE)
        } else {
            updated.setViewVisibility(R.id.widget_profile, android.view.View.GONE)
        }

        appWidgetManager.updateAppWidget(widgetId, updated)
    }
}

private fun formatW(v: Double): String =
    String.format("%,.2f", v).replace(',', 'X').replace('.', ',').replace('X', '.')
