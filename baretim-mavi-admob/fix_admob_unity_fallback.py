#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AdMob + Unity Ads fallback entegrasyonu — Termux patch scripti
Calisma: python3 ~/fix_admob_unity_fallback.py
"""

import os, sys

# Proje kok dizini — ls ~/ ile dogrulayiniz
ROOT = "/data/data/com.termux/files/home/baretim-mavi-admob"
JAVA = f"{ROOT}/app/src/main/java/com/bluechip/finance"

# ─── 1. build.gradle ──────────────────────────────────────────────────────────
BUILD_GRADLE = f"{ROOT}/app/build.gradle"
build_patches = [
    (
        "    // AdMob\n    implementation 'com.android.billingclient:billing-ktx:7.0.0'",
        "    // AdMob SDK (23.3.0 -- Kotlin 1.9.x ile uyumlu)\n    implementation 'com.google.android.gms:play-services-ads:23.3.0'\n    implementation 'com.google.android.ump:user-messaging-platform:3.1.0'\n    // Billing\n    implementation 'com.android.billingclient:billing-ktx:7.0.0'"
    )
]

# ─── 2. UnityAdsManager.kt (debug Toast'lari kaldir) ─────────────────────────
UNITY_MGR = f"{JAVA}/UnityAdsManager.kt"
unity_patches = [
    (
        "                    Log.e(TAG, \"Unity Ads baslanamadi: $message\")\n                    android.widget.Toast.makeText(context, \"Unity init FAIL: $message\", android.widget.Toast.LENGTH_LONG).show()\n                    initialized = false",
        "                    Log.e(TAG, \"Unity Ads baslanamadi: $message\")\n                    initialized = false"
    ),
    (
        "                Log.e(TAG, \"Rewarded FAIL: $error | $message\")\n                android.widget.Toast.makeText(appContext, \"LOAD FAIL: $error | $message\", android.widget.Toast.LENGTH_LONG).show()",
        "                Log.e(TAG, \"Rewarded FAIL: $error | $message\")"
    ),
    (
        "    fun showRewarded(activity: Activity, onRewarded: () -> Unit, onNotReady: () -> Unit) {\n        android.widget.Toast.makeText(activity, \"isInit:${UnityAds.isInitialized} rewardedReady:$rewardedReady\", android.widget.Toast.LENGTH_LONG).show()\n        if (rewardedReady) {",
        "    fun showRewarded(activity: Activity, onRewarded: () -> Unit, onNotReady: () -> Unit) {\n        if (rewardedReady) {"
    )
]

# ─── 3. MainActivity.kt ───────────────────────────────────────────────────────
MAIN_ACT = f"{JAVA}/MainActivity.kt"
main_patches = [
    (
        "import android.os.Bundle\nimport com.google.android.play.core.review.ReviewManagerFactory",
        "import android.os.Bundle\nimport com.google.android.play.core.review.ReviewManagerFactory\nimport com.google.android.ump.ConsentRequestParameters\nimport com.google.android.ump.UserMessagingPlatform"
    ),
    (
        "        // Unity Ads init\n        UnityAdsManager.init(this)",
        "        // AdMob + Unity Ads init (AdMob once, basarisiz olursa Unity fallback)\n        AdManager.init(this)\n        // UMP: kullanici rizasi (AB/ABD kullanicilari icin gerekli)\n        val consentInfo = UserMessagingPlatform.getConsentInformation(this)\n        consentInfo.requestConsentInfoUpdate(this, ConsentRequestParameters.Builder().build(), {\n            UserMessagingPlatform.loadAndShowConsentFormIfRequired(this) {}\n        }, {})"
    ),
    (
        "UnityAdsManager.showRewarded(",
        "AdManager.showRewarded("
    )
]

# ─── 4. BannerAdView.kt ───────────────────────────────────────────────────────
BANNER = f"{JAVA}/ui/components/BannerAdView.kt"
banner_patches = [
    ("import com.bluechip.finance.UnityAdsManager", "import com.bluechip.finance.AdManager"),
    ("UnityAdsManager.showBanner(activity, container)", "AdManager.showBanner(activity, container)")
]

# ─── 5. Screen dosyalari — Interstitial ──────────────────────────────────────
OVERTIME  = f"{JAVA}/ui/screens/OvertimeScreen.kt"
SEVERANCE = f"{JAVA}/ui/screens/SeveranceScreen.kt"
TAX       = f"{JAVA}/ui/screens/TaxScreen.kt"
interstitial_patches = [
    ("import com.bluechip.finance.UnityAdsManager", "import com.bluechip.finance.AdManager"),
    ("UnityAdsManager.showInterstitial", "AdManager.showInterstitial")
]

# ─── 6. SavingsScreen.kt — Rewarded ──────────────────────────────────────────
SAVINGS = f"{JAVA}/ui/screens/SavingsScreen.kt"
savings_patches = [
    ("import com.bluechip.finance.UnityAdsManager", "import com.bluechip.finance.AdManager"),
    ("UnityAdsManager.showRewarded", "AdManager.showSavingsRewarded")
]

# ─── 7. AdManager.kt olustur ─────────────────────────────────────────────────
AD_MANAGER_PATH = f"{JAVA}/AdManager.kt"
AD_MANAGER_CONTENT = '''package com.bluechip.finance

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
import com.google.android.gms.ads.interstitial.InterstitialAd
import com.google.android.gms.ads.interstitial.InterstitialAdLoadCallback
import com.google.android.gms.ads.rewarded.RewardedAd
import com.google.android.gms.ads.rewarded.RewardedAdLoadCallback

private const val TAG = "AdManager"

private const val ADMOB_BANNER_ID           = "ca-app-pub-7820582813827252/8522252459"
private const val ADMOB_INTERSTITIAL_ID     = "ca-app-pub-7820582813827252/5460511169"
private const val ADMOB_REWARDED_ID         = "ca-app-pub-7820582813827252/3824449145"
private const val ADMOB_SAVINGS_REWARDED_ID = "ca-app-pub-7820582813827252/4892694634"

object AdManager {

    private lateinit var appCtx: Context

    private var admobInterstitial: InterstitialAd? = null
    private var admobInterstitialLoading = false

    private var admobRewarded: RewardedAd? = null
    private var admobRewardedLoading = false

    private var admobSavingsRewarded: RewardedAd? = null
    private var admobSavingsRewardedLoading = false

    fun init(context: Context) {
        appCtx = context.applicationContext
        MobileAds.initialize(context) {
            Log.d(TAG, "AdMob baslatildi")
            loadInterstitial()
            loadRewarded()
            loadSavingsRewarded()
        }
        UnityAdsManager.init(context)
    }

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
                Log.e(TAG, "AdMob banner hata (${error.code}) -> Unity")
                UnityAdsManager.showBanner(activity, container)
            }
        }
        adView.loadAd(AdRequest.Builder().build())
    }

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
            ad.show(activity) { _ -> earned = true; onRewarded() }
        } else {
            Log.d(TAG, "AdMob rewarded hazir degil -> Unity")
            loadRewarded()
            UnityAdsManager.showRewarded(activity, onRewarded, onNotReady)
        }
    }

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
            ad.show(activity) { _ -> earned = true; onRewarded() }
        } else {
            Log.d(TAG, "AdMob savings rewarded hazir degil -> Unity")
            loadSavingsRewarded()
            UnityAdsManager.showRewarded(activity, onRewarded, onNotReady)
        }
    }
}
'''

# ─────────────────────────────────────────────────────────────────────────────

def apply_patches(filepath, patches, all_replace=False):
    if not os.path.exists(filepath):
        print(f"[ATLA] Dosya yok: {filepath}")
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    original = content
    for i, (old, new) in enumerate(patches, 1):
        count = content.count(old)
        if count == 0:
            print(f"  Patch {i}: BULUNAMADI (dosya: {os.path.basename(filepath)})")
        elif all_replace:
            content = content.replace(old, new)
            print(f"  Patch {i}: {count} yerde degistirildi")
        else:
            content = content.replace(old, new, 1)
            print(f"  Patch {i}: OK")
    if content == original:
        print(f"  -> Degisiklik yok: {os.path.basename(filepath)}")
        return
    try:
        content.encode("utf-8")
    except UnicodeEncodeError as e:
        print(f"  [HATA] Unicode sorunu, kaydedilmiyor: {e}")
        sys.exit(1)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  -> Kaydedildi: {os.path.basename(filepath)}")


print("=== build.gradle ===")
apply_patches(BUILD_GRADLE, build_patches)

print("\n=== UnityAdsManager.kt (Toast temizle) ===")
apply_patches(UNITY_MGR, unity_patches)

print("\n=== MainActivity.kt ===")
apply_patches(MAIN_ACT, main_patches, all_replace=True)

print("\n=== BannerAdView.kt ===")
apply_patches(BANNER, banner_patches, all_replace=True)

print("\n=== OvertimeScreen.kt ===")
apply_patches(OVERTIME, interstitial_patches, all_replace=True)

print("\n=== SeveranceScreen.kt ===")
apply_patches(SEVERANCE, interstitial_patches, all_replace=True)

print("\n=== TaxScreen.kt ===")
apply_patches(TAX, interstitial_patches, all_replace=True)

print("\n=== SavingsScreen.kt ===")
apply_patches(SAVINGS, savings_patches, all_replace=True)

print("\n=== AdManager.kt olusturuluyor ===")
try:
    AD_MANAGER_CONTENT.encode("utf-8")
except UnicodeEncodeError as e:
    print(f"[HATA] Unicode sorunu: {e}")
    sys.exit(1)
with open(AD_MANAGER_PATH, "w", encoding="utf-8") as f:
    f.write(AD_MANAGER_CONTENT)
print(f"  -> Olusturuldu: {AD_MANAGER_PATH}")

print("\n=== TAMAMLANDI ===")
print("Sonraki adim: gp (gradle build)")
