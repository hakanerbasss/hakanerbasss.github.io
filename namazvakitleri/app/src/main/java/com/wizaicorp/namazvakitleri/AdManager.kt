package com.wizaicorp.namazvakitleri

import android.app.Activity
import android.content.Context
import android.util.Log
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.google.android.gms.ads.*
import com.google.android.gms.ads.interstitial.InterstitialAd
import com.google.android.gms.ads.interstitial.InterstitialAdLoadCallback
import com.google.android.gms.ads.appopen.AppOpenAd

// AdMob konsolundan gercek ID'leri al
private const val BANNER_ID       = "ca-app-pub-7820582813827252/8866344025"
private const val INTERSTITIAL_ID = "ca-app-pub-7820582813827252/8159767013"
private const val APP_OPEN_ID     = "ca-app-pub-7820582813827252/8953973937"

object AdManager {
    private lateinit var ctx: Context
    private var interstitial: InterstitialAd? = null
    private var appOpen: AppOpenAd? = null
    private var appOpenLoadTime = 0L

    fun init(context: Context) {
        ctx = context.applicationContext
        MobileAds.initialize(context) {
            Log.d("AdManager", "AdMob baslatildi")
            loadInterstitial()
            loadAppOpen()
        }
    }

    private fun loadInterstitial() {
        InterstitialAd.load(ctx, INTERSTITIAL_ID, AdRequest.Builder().build(),
            object : InterstitialAdLoadCallback() {
                override fun onAdLoaded(ad: InterstitialAd) { interstitial = ad }
                override fun onAdFailedToLoad(e: LoadAdError) { interstitial = null }
            })
    }

    // Ekran gecislerinde frekans korumali gosterim:
    // en az 4 gecis VE son gosterimden 2 dk gecmis olmali
    private var lastInterstitialMs = 0L
    private var actionCount = 0

    fun maybeShowInterstitial(activity: Activity) {
        actionCount++
        val now = System.currentTimeMillis()
        if (actionCount >= 4 && now - lastInterstitialMs > 120_000 && interstitial != null) {
            actionCount = 0
            lastInterstitialMs = now
            showInterstitial(activity)
        }
    }

    fun showInterstitial(activity: Activity, onDone: () -> Unit = {}) {
        val ad = interstitial
        if (ad != null) {
            ad.fullScreenContentCallback = object : FullScreenContentCallback() {
                override fun onAdDismissedFullScreenContent() { interstitial = null; loadInterstitial(); onDone() }
                override fun onAdFailedToShowFullScreenContent(e: AdError) { onDone() }
            }
            ad.show(activity)
        } else { onDone() }
    }

    // App Open koruma: ilk acilista, interstitial'dan hemen sonra ve
    // kisa kesintilerde (izin diyalogu, UMP formu) gosterme
    private val appStartMs = System.currentTimeMillis()
    private var lastPauseMs = 0L

    fun notePause() { lastPauseMs = System.currentTimeMillis() }

    private fun loadAppOpen() {
        AppOpenAd.load(ctx, APP_OPEN_ID, AdRequest.Builder().build(),
            object : AppOpenAd.AppOpenAdLoadCallback() {
                override fun onAdLoaded(ad: AppOpenAd) { appOpen = ad; appOpenLoadTime = System.currentTimeMillis() }
                override fun onAdFailedToLoad(e: LoadAdError) { appOpen = null }
            })
    }

    fun showAppOpen(activity: Activity) {
        val now = System.currentTimeMillis()
        if (now - appStartMs < 15_000) return                       // ilk acilis
        if (now - lastInterstitialMs < 60_000) return               // interstitial yeni kapandi
        if (lastPauseMs == 0L || now - lastPauseMs < 30_000) return // kisa kesinti
        val ad = appOpen ?: return
        if (now - appOpenLoadTime > 4 * 3600_000) { loadAppOpen(); return }
        ad.fullScreenContentCallback = object : FullScreenContentCallback() {
            override fun onAdDismissedFullScreenContent() { appOpen = null; loadAppOpen() }
        }
        ad.show(activity)
    }
}

@Composable
fun BannerAd() {
    Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        AndroidView(factory = { ctx ->
            AdView(ctx).apply {
                setAdSize(AdSize.BANNER)
                adUnitId = BANNER_ID
                loadAd(AdRequest.Builder().build())
            }
        })
    }
}
