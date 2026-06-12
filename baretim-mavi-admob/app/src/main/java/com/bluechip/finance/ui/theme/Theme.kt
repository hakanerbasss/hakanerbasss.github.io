package com.bluechip.finance.ui.theme

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

// Aurora arka plan — tüm uygulamanın arkasına çizilir
@Composable
fun AuroraBg(isDark: Boolean) {
    val tr = rememberInfiniteTransition(label = "aurora")
    val t  by tr.animateFloat(0f, 1f,
        infiniteRepeatable(tween(12000, easing = LinearEasing), RepeatMode.Reverse), "t")
    val t2 by tr.animateFloat(0f, 1f,
        infiniteRepeatable(tween(8200,  easing = LinearEasing), RepeatMode.Reverse), "t2")

    Canvas(modifier = Modifier.fillMaxSize()) {
        val w = size.width; val h = size.height
        fun lerp(a: Float, b: Float, f: Float) = a + (b - a) * f
        val a1 = if (isDark) 0.58f else 0.22f
        val a2 = if (isDark) 0.44f else 0.16f
        val a3 = if (isDark) 0.32f else 0.11f

        // Blob 1 — indigo, üst, sağa doğru sürükleniyor
        drawRect(Brush.radialGradient(
            listOf(Color(0xFF4F46E5).copy(alpha = a1), Color.Transparent),
            center = Offset(lerp(0f, w * .45f, t), lerp(0f, h * .24f, t2)),
            radius = w * .75f
        ))
        // Blob 2 — fuşya, sağ alt
        drawRect(Brush.radialGradient(
            listOf(Color(0xFFD946EF).copy(alpha = a2), Color.Transparent),
            center = Offset(lerp(w * .60f, w, 1f - t2), lerp(h * .50f, h * .96f, t)),
            radius = w * .68f
        ))
        // Blob 3 — mor, ortada karşı yönde
        drawRect(Brush.radialGradient(
            listOf(Color(0xFF7C3AED).copy(alpha = a3), Color.Transparent),
            center = Offset(lerp(w * .28f, w * .74f, t2), lerp(h * .20f, h * .70f, 1f - t)),
            radius = w * .55f
        ))
    }
}

private val LightColors = lightColorScheme(
    primary = PurplePrimary, onPrimary = Color.White, secondary = OrangeAccent,
    surface = SurfaceLight, background = SurfaceLight, error = ErrorRed,
    surfaceVariant = CardGrayLight, onSurface = TextPrimaryLight, onBackground = TextPrimaryLight
)
private val DarkColors = darkColorScheme(
    primary = PurplePrimaryLight, onPrimary = Color.Black, secondary = OrangeAccent,
    surface = SurfaceDark, background = SurfaceDark, error = ErrorRed,
    surfaceVariant = CardGrayDark, onSurface = TextPrimaryDark, onBackground = TextPrimaryDark
)

data class AppColors(
    val textPrimary: Color, val textSecondary: Color,
    val cardBg: Color, val cardGray: Color,
    val success: Color, val error: Color, val warning: Color, val info: Color,
    val isDark: Boolean
)

val LocalAppColors = compositionLocalOf {
    AppColors(TextPrimaryLight, TextSecondaryLight, CardLight, CardGrayLight,
              SuccessGreen, ErrorRed, WarningOrange, InfoBlue, false)
}

@Composable
fun BlueChipTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val scheme    = if (darkTheme) DarkColors else LightColors
    val appColors = if (darkTheme)
        AppColors(TextPrimaryDark, TextSecondaryDark, CardDark, CardGrayDark,
                  SuccessGreen, ErrorRed, WarningOrange, InfoBlue, true)
    else
        AppColors(TextPrimaryLight, TextSecondaryLight, CardLight, CardGrayLight,
                  SuccessGreen, ErrorRed, WarningOrange, InfoBlue, false)

    CompositionLocalProvider(LocalAppColors provides appColors) {
        MaterialTheme(colorScheme = scheme) {
            // Tüm uygulamanın arkasındaki yaşayan aurora
            Box(modifier = Modifier
                    .fillMaxSize()
                    .background(if (darkTheme) SurfaceDark else SurfaceLight)) {
                AuroraBg(isDark = darkTheme)
                content()
            }
        }
    }
}
