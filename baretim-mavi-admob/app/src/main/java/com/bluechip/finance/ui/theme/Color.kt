package com.bluechip.finance.ui.theme

import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

// ── Mor Tema ──────────────────────────────────────────────────────────
val PurplePrimary      = Color(0xFF7C3AED)
val PurplePrimaryDark  = Color(0xFF5B21B6)
val PurplePrimaryLight = Color(0xFFA78BFA)
val OrangeAccent       = Color(0xFFF97316)
val FuchsiaAccent      = Color(0xFFD946EF)
val IndigoDeep         = Color(0xFF4F46E5)

// ── Ortak Gradientler — tum uygulamada kullan ────────────────────────
val GradientPrimary = Brush.linearGradient(listOf(IndigoDeep, PurplePrimary, FuchsiaAccent))
val GradientButton  = Brush.horizontalGradient(listOf(IndigoDeep, PurplePrimary))
val GradientSuccess = Brush.horizontalGradient(listOf(Color(0xFF059669), Color(0xFF10B981)))

// Light
val SurfaceLight     = Color(0xFFF5F3FF)
val CardLight        = Color(0xFFFFFFFF)
val CardGrayLight    = Color(0xFFEDE9FE)
val TextPrimaryLight = Color(0xFF1F1235)
val TextSecondaryLight = Color(0xFF6B7280)

// Dark — derin gece moru
val SurfaceDark      = Color(0xFF130C20)
val CardDark         = Color(0xFF241740)
val CardGrayDark     = Color(0xFF31215A)
val TextPrimaryDark  = Color(0xFFF3F0FF)
val TextSecondaryDark = Color(0xFFB8A9D9)

val SuccessGreen  = Color(0xFF10B981)
val ErrorRed      = Color(0xFFEF4444)
val WarningOrange = Color(0xFFF97316)
val InfoBlue      = Color(0xFF3B82F6)
