package com.bluechip.finance.ui.components

import android.widget.FrameLayout
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import com.bluechip.finance.AdManager

@Composable
fun BannerAd(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    if (com.bluechip.finance.data.AdFreeManager.isAdFree(context)) return

    val container = remember { FrameLayout(context) }

    AndroidView(
        factory = { ctx ->
            container.also {
                val activity = ctx as? android.app.Activity ?: return@also
                AdManager.showBanner(activity, container)
            }
        },
        modifier = modifier.fillMaxWidth()
    )
}
