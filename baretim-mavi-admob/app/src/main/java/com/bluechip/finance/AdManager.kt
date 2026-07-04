package com.bluechip.finance

import android.app.Activity
import android.content.Context
import android.util.Log
import android.widget.FrameLayout
import com.google.android.gms.ads.AdError
import com.google.android.gms.ads.AdListener
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.AdSize
import com.google.android.gms.ads.AdView
import com.google.android.gms.ads.FullScreenContentCallback
import com.google.android.gms.ads.LoadAdError
import com.google.android.gms.ads.MobileAds
import com.google.android.gms.ads.appopen.AppOpenAd
import com.google.android.gms.ads.interstitial.InterstitialAd
import com.google.android.gms.ads.interstitial.InterstitialAdLoadCallback
import com.google.android.gms.ads.rewarded.RewardedAd
import com.google.android.gms.ads.rewarded.RewardedAdLoadCallback

private const val TAG = "AdManager"

private const val ADMOB_BANNER_ID          = "ca-app-pub-7820582813827252/8522252459"
private const val ADMOB_INTERSTITIAL_ID    = "ca-app-pub-7820582813827252/5460511169"
private const val ADMOB_REWARDED_ID        = "ca-app-pub-7820582813827252/3824449145"
private const val ADMOB_SAVINGS_REWARDED_ID = "ca-app-pub-7820582813827252/4892694634"
// TEST ID - AdMob konsolunda gercek App Open reklam birimi olustur ve bu satiri guncelle
private const val ADMOB_APP_OPEN_ID        = "ca-app-pub-3940256099942544/9257395921"

object AdManager {

    private lateinit var appCtx: Context

    private var admobInterstitial: InterstitialAd? = null
    private var admobInterstitialLoading = false

    private var admobRewarded: RewardedAd? = null
    private var admobRewardedLoading = false

    private var admobSavingsRewarded: RewardedAd? = null
    private var admobSavingsRewardedLoading = false

    private var appOpenAd: AppOpenAd? = null
    private var appOpenLoading = false
    private var appOpenShowing = false
    private var appOpenLoadTimeMs = 0L

    fun init(context: Context) {
        appCtx = context.applicationContext

        MobileAds.initialize(context) {
            Log.d(TAG, "AdMob baslatildi")
            loadInterstitial()
            loadRewarded()
            loadSavingsRewarded()
            loadAppOpenAd()
        }

        UnityAdsManager.init(context)
    }

    // ── BANNER ──────────────────────────────────────────────────────────────

    fun showBanner(activity: Activity, container: FrameLayout) {
        val adView = AdView(activity)
        adView.adUnitId = ADMOB_BANNER_ID
        adView.setAdSize(AdSize.BANNER)
        adView.adListener = object : AdListener() {
            override fun onAdLoaded() {
                Log.d(TAG, "AdMob banner yuklendi")
                activity.runOnUiThread {
                    container.removeAllViews()
                    container.addView(adView)
                }
            }
            override fun onAdFailedToLoad(error: LoadAdError) {
                Log.e(TAG, "AdMob banner hata (${error.code}): ${error.message} -> Unity")
                UnityAdsManager.showBanner(activity, container)
            }
        }
        adView.loadAd(AdRequest.Builder().build())
    }

    // ── INTERSTITIAL ─────────────────────────────────────────────────────────

    private fun loadInterstitial() {
        if (admobInterstitialLoading) return
        admobInterstitialLoading = true
        InterstitialAd.load(appCtx, ADMOB_INTERSTITIAL_ID, AdRequest.Builder().build(),
            object : InterstitialAdLoadCallback() {
                override fun onAdLoaded(ad: InterstitialAd) {
                    Log.d(TAG, "AdMob interstitial yuklendi")
                    admobInterstitial = ad
                    admobInterstitialLoading = false
                }
                override fun onAdFailedToLoad(error: LoadAdError) {
                    Log.e(TAG, "AdMob interstitial hata: ${error.message}")
                    admobInterstitial = null
                    admobInterstitialLoading = false
                }
            })
    }

    fun showInterstitial(activity: Activity, onFinished: () -> Unit) {
        val ad = admobInterstitial
        if (ad != null) {
            ad.fullScreenContentCallback = object : FullScreenContentCallback() {
                override fun onAdDismissedFullScreenContent() {
                    admobInterstitial = null
                    loadInterstitial()
                    onFinished()
                }
                override fun onAdFailedToShowFullScreenContent(error: AdError) {
                    Log.e(TAG, "AdMob interstitial gosterilemedi -> Unity: ${error.message}")
                    admobInterstitial = null
                    loadInterstitial()
                    UnityAdsManager.showInterstitial(activity, onFinished)
                }
            }
            ad.show(activity)
        } else {
            Log.d(TAG, "AdMob interstitial hazir degil -> Unity")
            loadInterstitial()
            UnityAdsManager.showInterstitial(activity, onFinished)
        }
    }

    // ── REWARDED (AdFree modu) ───────────────────────────────────────────────

    private fun loadRewarded() {
        if (admobRewardedLoading) return
        admobRewardedLoading = true
        RewardedAd.load(appCtx, ADMOB_REWARDED_ID, AdRequest.Builder().build(),
            object : RewardedAdLoadCallback() {
                override fun onAdLoaded(ad: RewardedAd) {
                    Log.d(TAG, "AdMob rewarded yuklendi")
                    admobRewarded = ad
                    admobRewardedLoading = false
                }
                override fun onAdFailedToLoad(error: LoadAdError) {
                    Log.e(TAG, "AdMob rewarded hata: ${error.message}")
                    admobRewarded = null
                    admobRewardedLoading = false
                }
            })
    }

    fun showRewarded(activity: Activity, onRewarded: () -> Unit, onNotReady: () -> Unit) {
        val ad = admobRewarded
        if (ad != null) {
            var earned = false
            ad.fullScreenContentCallback = object : FullScreenContentCallback() {
                override fun onAdDismissedFullScreenContent() {
                    admobRewarded = null
                    loadRewarded()
                    if (!earned) onNotReady()
                }
                override fun onAdFailedToShowFullScreenContent(error: AdError) {
                    Log.e(TAG, "AdMob rewarded gosterilemedi -> Unity: ${error.message}")
                    admobRewarded = null
                    loadRewarded()
                    UnityAdsManager.showRewarded(activity, onRewarded, onNotReady)
                }
            }
            ad.show(activity) { _ ->
                earned = true
                onRewarded()
            }
        } else {
            Log.d(TAG, "AdMob rewarded hazir degil -> Unity")
            loadRewarded()
            UnityAdsManager.showRewarded(activity, onRewarded, onNotReady)
        }
    }

    // ── REWARDED (Birikim yenile butonu) ─────────────────────────────────────

    private fun loadSavingsRewarded() {
        if (admobSavingsRewardedLoading) return
        admobSavingsRewardedLoading = true
        RewardedAd.load(appCtx, ADMOB_SAVINGS_REWARDED_ID, AdRequest.Builder().build(),
            object : RewardedAdLoadCallback() {
                override fun onAdLoaded(ad: RewardedAd) {
                    Log.d(TAG, "AdMob savings rewarded yuklendi")
                    admobSavingsRewarded = ad
                    admobSavingsRewardedLoading = false
                }
                override fun onAdFailedToLoad(error: LoadAdError) {
                    Log.e(TAG, "AdMob savings rewarded hata: ${error.message}")
                    admobSavingsRewarded = null
                    admobSavingsRewardedLoading = false
                }
            })
    }

    fun showSavingsRewarded(activity: Activity, onRewarded: () -> Unit, onNotReady: () -> Unit) {
        val ad = admobSavingsRewarded
        if (ad != null) {
            var earned = false
            ad.fullScreenContentCallback = object : FullScreenContentCallback() {
                override fun onAdDismissedFullScreenContent() {
                    admobSavingsRewarded = null
                    loadSavingsRewarded()
                    if (!earned) onNotReady()
                }
                override fun onAdFailedToShowFullScreenContent(error: AdError) {
                    Log.e(TAG, "AdMob savings rewarded gosterilemedi -> Unity: ${error.message}")
                    admobSavingsRewarded = null
                    loadSavingsRewarded()
                    UnityAdsManager.showRewarded(activity, onRewarded, onNotReady)
                }
            }
            ad.show(activity) { _ ->
                earned = true
                onRewarded()
            }
        } else {
            Log.d(TAG, "AdMob savings rewarded hazir degil -> Unity")
            loadSavingsRewarded()
            UnityAdsManager.showRewarded(activity, onRewarded, onNotReady)
        }
    }

    // ── APP OPEN ──────────────────────────────────────────────────────────────

    private fun loadAppOpenAd() {
        if (appOpenLoading || isAppOpenAdAvailable()) return
        appOpenLoading = true
        AppOpenAd.load(appCtx, ADMOB_APP_OPEN_ID, AdRequest.Builder().build(),
            object : AppOpenAd.AppOpenAdLoadCallback() {
                override fun onAdLoaded(ad: AppOpenAd) {
                    Log.d(TAG, "AdMob app open yuklendi")
                    appOpenAd = ad
                    appOpenLoading = false
                    appOpenLoadTimeMs = System.currentTimeMillis()
                }
                override fun onAdFailedToLoad(error: LoadAdError) {
                    Log.e(TAG, "AdMob app open hata: ${error.message}")
                    appOpenAd = null
                    appOpenLoading = false
                }
            })
    }

    private fun isAppOpenAdAvailable(): Boolean {
        val ad = appOpenAd ?: return false
        val fourHoursMs = 4L * 60 * 60 * 1000
        return (System.currentTimeMillis() - appOpenLoadTimeMs) < fourHoursMs
    }

    /** Uygulama on plana her gelisinde (cold start dahil) cagir. */
    fun showAppOpenAdIfAvailable(activity: Activity) {
        if (appOpenShowing) return
        if (com.bluechip.finance.data.AdFreeManager.isAdFree(activity)) return
        val ad = appOpenAd
        if (ad == null || !isAppOpenAdAvailable()) {
            loadAppOpenAd()
            return
        }
        ad.fullScreenContentCallback = object : FullScreenContentCallback() {
            override fun onAdShowedFullScreenContent() {
                appOpenShowing = true
            }
            override fun onAdDismissedFullScreenContent() {
                appOpenAd = null
                appOpenShowing = false
                loadAppOpenAd()
            }
            override fun onAdFailedToShowFullScreenContent(error: AdError) {
                Log.e(TAG, "AdMob app open gosterilemedi: ${error.message}")
                appOpenAd = null
                appOpenShowing = false
                loadAppOpenAd()
            }
        }
        ad.show(activity)
    }
}
