package com.bluechip.finance

import android.app.Activity
import android.content.Context
import android.util.Log
import android.widget.FrameLayout
import com.ironsource.mediationsdk.IronSource
import com.ironsource.mediationsdk.IronSourceBannerLayout
import com.ironsource.mediationsdk.adunit.interfaces.BannerAdListener
import com.ironsource.mediationsdk.logger.IronSourceError
import com.ironsource.mediationsdk.model.Placement
import com.ironsource.mediationsdk.sdk.InterstitialListener
import com.ironsource.mediationsdk.sdk.RewardedVideoListener

private const val TAG = "LevelPlayAdManager"
private const val APP_KEY = "bk0ln8pyk5ux28xj"

object LevelPlayAdManager {

    private var initialized = false
    private var bannerLayout: IronSourceBannerLayout? = null

    // LevelPlay'i baslatir - MainActivity.onCreate'de cagir
    fun init(activity: Activity) {
        if (initialized) return
        IronSource.init(activity, APP_KEY,
            IronSource.AD_UNIT.REWARDED_VIDEO,
            IronSource.AD_UNIT.INTERSTITIAL,
            IronSource.AD_UNIT.BANNER
        )
        initialized = true
        Log.d(TAG, "LevelPlay initialized")
        // Interstitial on yukle
        IronSource.loadInterstitial()
    }

    // Activity lifecycle - onResume/onPause'da cagir
    fun onResume(activity: Activity) = IronSource.onResume(activity)
    fun onPause(activity: Activity)  = IronSource.onPause(activity)

    // ── BANNER ──────────────────────────────────────────────────
    fun showBanner(activity: Activity, container: FrameLayout) {
        val banner = IronSource.createBanner(activity, IronSource.AD_SIZE.BANNER)
            ?: return
        bannerLayout = banner
        banner.bannerAdListener = object : BannerAdListener {
            override fun onBannerAdLoaded() {
                Log.d(TAG, "Banner yuklendi")
                activity.runOnUiThread {
                    container.removeAllViews()
                    container.addView(banner)
                }
            }
            override fun onBannerAdLoadFailed(error: IronSourceError) {
                Log.e(TAG, "Banner hatasi: ${error.errorMessage}")
            }
            override fun onBannerAdClicked() {}
            override fun onBannerAdScreenPresented() {}
            override fun onBannerAdScreenDismissed() {}
            override fun onBannerAdLeftApplication() {}
        }
        IronSource.loadBanner(banner)
    }

    fun destroyBanner() {
        bannerLayout?.let { IronSource.destroyBanner(it) }
        bannerLayout = null
    }

    // ── INTERSTITIAL ─────────────────────────────────────────────
    fun showInterstitial(activity: Activity, onFinished: () -> Unit) {
        if (IronSource.isInterstitialReady()) {
            IronSource.setInterstitialListener(object : InterstitialListener {
                override fun onInterstitialAdReady() {}
                override fun onInterstitialAdLoadFailed(error: IronSourceError) {
                    Log.e(TAG, "Interstitial yuklenemedi: ${error.errorMessage}")
                }
                override fun onInterstitialAdOpened() {}
                override fun onInterstitialAdClosed() {
                    onFinished()
                    IronSource.loadInterstitial()
                }
                override fun onInterstitialAdShowSucceeded() {}
                override fun onInterstitialAdShowFailed(error: IronSourceError) {
                    Log.e(TAG, "Interstitial gosterilemedi: ${error.errorMessage}")
                    onFinished()
                }
                override fun onInterstitialAdClicked() {}
            })
            IronSource.showInterstitial()
        } else {
            IronSource.loadInterstitial()
            onFinished()
        }
    }

    // ── REWARDED ─────────────────────────────────────────────────
    fun showRewarded(
        activity: Activity,
        onRewarded: () -> Unit,
        onNotReady: () -> Unit
    ) {
        if (IronSource.isRewardedVideoAvailable()) {
            IronSource.setRewardedVideoListener(object : RewardedVideoListener {
                override fun onRewardedVideoAvailabilityChanged(available: Boolean) {}
                override fun onRewardedVideoAdOpened() {}
                override fun onRewardedVideoAdClosed() {}
                override fun onRewardedVideoAdStarted() {}
                override fun onRewardedVideoAdEnded() {}
                override fun onRewardedVideoAdRewarded(placement: Placement) {
                    Log.d(TAG, "Odullu reklam tamamlandi")
                    onRewarded()
                }
                override fun onRewardedVideoAdShowFailed(error: IronSourceError) {
                    Log.e(TAG, "Rewarded gosterilemedi: ${error.errorMessage}")
                    onNotReady()
                }
            })
            IronSource.showRewardedVideo()
        } else {
            Log.d(TAG, "Rewarded hazir degil")
            onNotReady()
        }
    }
}
