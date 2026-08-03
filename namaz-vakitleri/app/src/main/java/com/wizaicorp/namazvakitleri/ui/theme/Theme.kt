package com.wizaicorp.namazvakitleri.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColorScheme = darkColorScheme(
    primary             = Emerald500,
    onPrimary           = Color.White,
    primaryContainer    = Emerald900,
    onPrimaryContainer  = Emerald200,
    secondary           = GoldLight,
    onSecondary         = NeutralDark,
    background          = NeutralDark,
    onBackground        = NeutralLight,
    surface             = SurfaceDark,
    onSurface           = NeutralLight,
    surfaceVariant      = NeutralMid,
    onSurfaceVariant    = Emerald200
)

private val LightColorScheme = lightColorScheme(
    primary             = Emerald700,
    onPrimary           = Color.White,
    primaryContainer    = Emerald200,
    onPrimaryContainer  = Emerald900,
    secondary           = GoldDark,
    onSecondary         = Color.White,
    background          = NeutralLight,
    onBackground        = NeutralDark,
    surface             = Surface,
    onSurface           = NeutralDark,
    surfaceVariant      = Color(0xFFDCFCE7),
    onSurfaceVariant    = Emerald900
)

@Composable
fun NamazTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme,
        typography  = Typography(),
        content     = content
    )
}
