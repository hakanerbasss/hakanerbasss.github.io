package com.bluechip.finance

import android.app.Activity
import android.app.Application
import android.os.Bundle
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner

class MyApp : Application(),
    Application.ActivityLifecycleCallbacks,
    DefaultLifecycleObserver {

    private var currentActivity: Activity? = null

    override fun onCreate() {
        super<Application>.onCreate()

        registerActivityLifecycleCallbacks(this)
        ProcessLifecycleOwner.get().lifecycle.addObserver(this)
    }

    // Uygulama arka plandan on plana her geldiginde (cold start dahil) App Open reklami dene.
    // ON_RESUME kullanilir cunku ON_START aninda currentActivity henuz set edilmemis olabilir
    // (Activity.onStart() -> onResume() sirasinda, currentActivity onActivityResumed'da set edilir;
    // ON_START'ta tetiklemek currentActivity=null oldugu icin reklamin hicbir zaman gosterilmemesine
    // neden oluyordu).
    override fun onResume(owner: LifecycleOwner) {
        currentActivity?.let { AdManager.showAppOpenAdIfAvailable(it) }
    }

    // ── ActivityLifecycleCallbacks ──────────────────────────────────
    // onActivityStarted'da da set edilir ki currentActivity, o activity'nin
    // onResume'undan once kesin dolu olsun.
    override fun onActivityStarted(activity: Activity) { currentActivity = activity }
    override fun onActivityResumed(activity: Activity) { currentActivity = activity }
    override fun onActivityPaused(activity: Activity)  {}
    override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {}
    override fun onActivityStopped(activity: Activity) {}
    override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) {}
    override fun onActivityDestroyed(activity: Activity) {
        if (currentActivity === activity) currentActivity = null
    }
}
