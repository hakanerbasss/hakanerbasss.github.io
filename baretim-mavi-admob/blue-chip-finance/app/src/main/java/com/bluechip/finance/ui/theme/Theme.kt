package com.bluechip.finance.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

private val LightColorScheme = lightColorScheme(
    primary = BluePrimary,
    onPrimary = Color.White,
    secondary = GoldAccent,
    surface = SurfaceLight,
    background = SurfaceLight,
    error = ErrorRed,
    surfaceVariant = CardGrayLight,
    onSurface = TextPrimaryLight,
    onBackground = TextPrimaryLight,
    outline = Color(0xFFBDBDBD)
)

private val DarkColorScheme = darkColorScheme(
    primary = BluePrimaryDarkTheme,
    onPrimary = Color.Black,
    secondary = GoldAccent,
    surface = SurfaceDark,
    background = SurfaceDark,
    error = ErrorRedDark,
    surfaceVariant = CardGrayDark,
    onSurface = TextPrimaryDark,
    onBackground = TextPrimaryDark,
    outline = Color(0xFF616161)
)

data class AppColors(
    val textPrimary: Color,
    val textSecondary: Color,
    val cardBg: Color,
    val cardGray: Color,
    val success: Color,
    val error: Color,
    val warning: Color,
    val info: Color,
    val isDark: Boolean
)

val LocalAppColors = compositionLocalOf {
    AppColors(
        textPrimary = TextPrimaryLight,
        textSecondary = TextSecondaryLight,
        cardBg = CardLight,
        cardGray = CardGrayLight,
        success = SuccessGreen,
        error = ErrorRed,
        warning = WarningOrange,
        info = InfoBlue,
        isDark = false
    )
}

@Composable
fun BlueChipTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme

    val appColors = if (darkTheme) {
        AppColors(TextPrimaryDark, TextSecondaryDark, CardDark, CardGrayDark, SuccessGreenDark, ErrorRedDark, WarningOrangeDark, InfoBlueDark, true)
    } else {
        AppColors(TextPrimaryLight, TextSecondaryLight, CardLight, CardGrayLight, SuccessGreen, ErrorRed, WarningOrange, InfoBlue, false)
    }

    androidx.compose.runtime.CompositionLocalProvider(LocalAppColors provides appColors) {
        MaterialTheme(colorScheme = colorScheme, content = content)
    }
}
