package com.bluechip.finance

import android.app.Activity
import android.content.Context
import android.util.Log
import android.widget.FrameLayout
import com.unity3d.ads.IUnityAdsInitializationListener
import com.unity3d.ads.IUnityAdsLoadListener
import com.unity3d.ads.IUnityAdsShowListener
import com.unity3d.ads.UnityAds
import com.unity3d.ads.UnityAdsShowOptions
import com.unity3d.services.banners.BannerErrorInfo
import com.unity3d.services.banners.BannerView
import com.unity3d.services.banners.UnityBannerSize

private const val TAG             = "UnityAdsManager"
private const val GAME_ID         = "6115073"
private const val BANNER_ID       = "Banner_Android_2"
private const val INTERSTITIAL_ID = "Interstitial_Android_2"
private const val REWARDED_ID     = "Rewarded_Android_2"
private const val TEST_MODE       = false

object UnityAdsManager {

    private var initialized       = false
    private var interstitialReady = false
    private var rewardedReady     = false
    private var bannerView: BannerView? = null
    private lateinit var appContext: Context

    fun init(context: Context) {
        if (initialized) return
        initialized = true
        appContext = context.applicationContext
        UnityAds.initialize(context, GAME_ID, TEST_MODE,
            object : IUnityAdsInitializationListener {
                override fun onInitializationComplete() {
                    Log.d(TAG, "Unity Ads baslatildi, 2sn bekleniyor...")
                    android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                        loadInterstitial()
                        loadRewarded()
                    }, 2000)
                }
                override fun onInitializationFailed(
                    error: UnityAds.UnityAdsInitializationError, message: String) {
                    Log.e(TAG, "Unity Ads baslanamadi: $message")
                    android.widget.Toast.makeText(context, "Unity init FAIL: $message", android.widget.Toast.LENGTH_LONG).show()
                    initialized = false
                }
            })
    }

    // ── BANNER ──────────────────────────────────────────────────
    fun showBanner(activity: Activity, container: FrameLayout) {
        destroyBanner()
        val banner = BannerView(activity, BANNER_ID, UnityBannerSize(320, 50))
        banner.listener = object : BannerView.Listener() {
            override fun onBannerLoaded(bannerAdView: BannerView?) {
                Log.d(TAG, "Banner yuklendi")
                activity.runOnUiThread {
                    container.removeAllViews()
                    bannerAdView?.let { container.addView(it) }
                }
            }
            override fun onBannerFailedToLoad(bannerAdView: BannerView?, errorInfo: BannerErrorInfo?) {
                Log.e(TAG, "Banner hatasi: ${errorInfo?.errorMessage}")
            }
            override fun onBannerClick(bannerAdView: BannerView?) {}
            override fun onBannerLeftApplication(bannerAdView: BannerView?) {}
        }
        bannerView = banner
        container.addView(banner)
        banner.load()
    }

    fun destroyBanner() {
        bannerView?.let {
            (it.parent as? FrameLayout)?.removeView(it)
            it.listener = null
        }
        bannerView = null
    }

    // ── INTERSTITIAL ─────────────────────────────────────────────
    fun loadInterstitial() {
        interstitialReady = false
        UnityAds.load(INTERSTITIAL_ID, object : IUnityAdsLoadListener {
            override fun onUnityAdsAdLoaded(placementId: String) {
                Log.d(TAG, "Interstitial yuklendi")
                interstitialReady = true
            }
            override fun onUnityAdsFailedToLoad(placementId: String,
                error: UnityAds.UnityAdsLoadError, message: String) {
                Log.e(TAG, "Interstitial yuklenemedi: $message")
            }
        })
    }

    fun showInterstitial(activity: Activity, onFinished: () -> Unit) {
        if (interstitialReady) {
            interstitialReady = false
            UnityAds.show(activity, INTERSTITIAL_ID, UnityAdsShowOptions(),
                object : IUnityAdsShowListener {
                    override fun onUnityAdsShowComplete(placementId: String,
                        state: UnityAds.UnityAdsShowCompletionState) {
                        onFinished()
                        loadInterstitial()
                    }
                    override fun onUnityAdsShowFailure(placementId: String,
                        error: UnityAds.UnityAdsShowError, message: String) {
                        Log.e(TAG, "Interstitial gosterilemedi: $message")
                        onFinished()
                        loadInterstitial()
                    }
                    override fun onUnityAdsShowStart(placementId: String) {}
                    override fun onUnityAdsShowClick(placementId: String) {}
                })
        } else {
            loadInterstitial()
            onFinished()
        }
    }

    // ── REWARDED ─────────────────────────────────────────────────
    fun loadRewarded() {
        rewardedReady = false
        UnityAds.load(REWARDED_ID, object : IUnityAdsLoadListener {
            override fun onUnityAdsAdLoaded(placementId: String) {
                Log.d(TAG, "Rewarded yuklendi")
                rewardedReady = true
            }
            override fun onUnityAdsFailedToLoad(placementId: String,
                error: UnityAds.UnityAdsLoadError, message: String) {
                Log.e(TAG, "Rewarded FAIL: $error | $message")
                android.widget.Toast.makeText(appContext, "LOAD FAIL: $error | $message", android.widget.Toast.LENGTH_LONG).show()
            }
        })
    }

    fun showRewarded(activity: Activity, onRewarded: () -> Unit, onNotReady: () -> Unit) {
        android.widget.Toast.makeText(activity, "isInit:${UnityAds.isInitialized} rewardedReady:$rewardedReady", android.widget.Toast.LENGTH_LONG).show()
        if (rewardedReady) {
            rewardedReady = false
            UnityAds.show(activity, REWARDED_ID, UnityAdsShowOptions(),
                object : IUnityAdsShowListener {
                    override fun onUnityAdsShowComplete(placementId: String,
                        state: UnityAds.UnityAdsShowCompletionState) {
                        if (state == UnityAds.UnityAdsShowCompletionState.COMPLETED) {
                            onRewarded()
                        }
                        loadRewarded()
                    }
                    override fun onUnityAdsShowFailure(placementId: String,
                        error: UnityAds.UnityAdsShowError, message: String) {
                        Log.e(TAG, "Rewarded gosterilemedi: $message")
                        onNotReady()
                        loadRewarded()
                    }
                    override fun onUnityAdsShowStart(placementId: String) {}
                    override fun onUnityAdsShowClick(placementId: String) {}
                })
        } else {
            loadRewarded()
            onNotReady()
        }
    }
}
