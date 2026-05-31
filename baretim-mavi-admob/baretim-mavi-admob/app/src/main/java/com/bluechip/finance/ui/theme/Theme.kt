package com.bluechip.finance.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.graphics.Color

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
    AppColors(TextPrimaryLight, TextSecondaryLight, CardLight, CardGrayLight, SuccessGreen, ErrorRed, WarningOrange, InfoBlue, false)
}

@Composable
fun BlueChipTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val scheme = if (darkTheme) DarkColors else LightColors
    val appColors = if (darkTheme) {
        AppColors(TextPrimaryDark, TextSecondaryDark, CardDark, CardGrayDark, SuccessGreen, ErrorRed, WarningOrange, InfoBlue, true)
    } else {
        AppColors(TextPrimaryLight, TextSecondaryLight, CardLight, CardGrayLight, SuccessGreen, ErrorRed, WarningOrange, InfoBlue, false)
    }
    androidx.compose.runtime.CompositionLocalProvider(LocalAppColors provides appColors) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
