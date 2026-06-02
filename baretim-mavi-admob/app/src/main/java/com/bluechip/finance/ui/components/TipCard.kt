package com.bluechip.finance.ui.components

import android.content.Context
import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.ui.theme.LocalAppColors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.URL

data class Tip(
    val category: String,
    val icon: String,
    val title: String,
    val text: String,
    val law: String
)

fun iconForTip(iconName: String): ImageVector = when (iconName) {
    "clock" -> Icons.Default.AccessTime
    "bank" -> Icons.Default.AccountBalance
    "receipt" -> Icons.Default.Receipt
    "calendar" -> Icons.Default.DateRange
    "gavel" -> Icons.Default.Gavel
    "shield" -> Icons.Default.Shield
    else -> Icons.Default.Lightbulb
}

fun categoryColor(category: String, isDark: Boolean): Pair<Color, Color> = when (category) {
    "overtime" -> if (isDark) Pair(Color(0xFF0D47A1), Color(0xFF1565C0)) else Pair(Color(0xFF1565C0), Color(0xFF42A5F5))
    "severance" -> if (isDark) Pair(Color(0xFF1B5E20), Color(0xFF2E7D32)) else Pair(Color(0xFF2E7D32), Color(0xFF66BB6A))
    "tax" -> if (isDark) Pair(Color(0xFFBF360C), Color(0xFFE65100)) else Pair(Color(0xFFE65100), Color(0xFFFF8A65))
    "leave" -> if (isDark) Pair(Color(0xFF4A148C), Color(0xFF6A1B9A)) else Pair(Color(0xFF6A1B9A), Color(0xFFAB47BC))
    else -> if (isDark) Pair(Color(0xFF263238), Color(0xFF37474F)) else Pair(Color(0xFF37474F), Color(0xFF78909C))
}

fun loadTipsFromCache(context: Context): List<Tip> {
    val prefs = context.getSharedPreferences("tips_cache", Context.MODE_PRIVATE)
    val json = prefs.getString("tips_json", null) ?: return emptyList()
    return parseTips(json)
}

fun saveTipsToCache(context: Context, json: String) {
    context.getSharedPreferences("tips_cache", Context.MODE_PRIVATE)
        .edit().putString("tips_json", json).apply()
}

fun parseTips(json: String): List<Tip> {
    return try {
        val obj = JSONObject(json)
        val arr = obj.getJSONArray("tips")
        val list = mutableListOf<Tip>()
        for (i in 0 until arr.length()) {
            val t = arr.getJSONObject(i)
            list.add(Tip(
                t.getString("category"), t.getString("icon"),
                t.getString("title"), t.getString("text"), t.getString("law")
            ))
        }
        list
    } catch (_: Exception) { emptyList() }
}

@Composable
fun TipCard() {
    val context = LocalContext.current
    val appColors = LocalAppColors.current
    var tips by remember { mutableStateOf<List<Tip>>(emptyList()) }
    var currentIndex by remember { mutableIntStateOf(0) }
    var isVisible by remember { mutableStateOf(true) }

    // Load tips
    LaunchedEffect(Unit) {
        // 1. Cache'den yükle
        val cached = loadTipsFromCache(context)
        if (cached.isNotEmpty()) {
            tips = cached.shuffled()
        }

        // 2. Sunucudan güncelle
        withContext(Dispatchers.IO) {
            try {
                val json = URL("https://raw.githubusercontent.com/hakanerbasss/baretim-mavi/main/tips.json?t=${System.currentTimeMillis()}").readText()
                val newTips = parseTips(json)
                if (newTips.isNotEmpty()) {
                    saveTipsToCache(context, json)
                    tips = newTips.shuffled()
                    currentIndex = 0
                }
            } catch (_: Exception) {
                // Cache zaten yüklü, hata olursa devam
            }
        }

        // Fallback: hiç tip yoksa hardcoded
        if (tips.isEmpty()) {
            tips = listOf(
                Tip("general", "gavel", "Biliyor muydunuz?", "Kıdem tazminatı için en az 1 yıl çalışmak gerekir.", "İş Kanunu"),
                Tip("overtime", "clock", "Fazla Mesai", "Haftalık 45 saati aşan çalışma %50 zamlı ödenir.", "Mad. 41"),
                Tip("leave", "calendar", "Yıllık İzin", "İlk 5 yıl için 14 gün yıllık izin hakkınız var.", "Mad. 53")
            )
        }
    }

    // Otomatik geçiş - 8 saniye
    LaunchedEffect(tips, currentIndex) {
        if (tips.isNotEmpty()) {
            delay(8000)
            isVisible = false
            delay(300)
            currentIndex = (currentIndex + 1) % tips.size
            isVisible = true
        }
    }

    if (tips.isEmpty()) return

    val tip = tips[currentIndex % tips.size]
    val (startColor, endColor) = categoryColor(tip.category, appColors.isDark)

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .clickable {
                isVisible = false
                currentIndex = (currentIndex + 1) % tips.size
                isVisible = true
            },
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(6.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.linearGradient(listOf(startColor, endColor)))
                .padding(20.dp)
        ) {
            this@Column.AnimatedVisibility(
                visible = isVisible,
                enter = fadeIn() + slideInHorizontally(),
                exit = fadeOut() + slideOutHorizontally()
            ) {
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            iconForTip(tip.icon), null,
                            tint = Color.White.copy(alpha = 0.9f),
                            modifier = Modifier.size(28.dp)
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(
                            "Biliyor muydunuz?",
                            color = Color.White,
                            fontWeight = FontWeight.Bold,
                            fontSize = 16.sp
                        )
                    }

                    Spacer(Modifier.height(12.dp))

                    Text(
                        tip.title,
                        color = Color.White,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 15.sp
                    )

                    Spacer(Modifier.height(6.dp))

                    Text(
                        tip.text,
                        color = Color.White.copy(alpha = 0.9f),
                        fontSize = 13.sp,
                        lineHeight = 19.sp
                    )

                    Spacer(Modifier.height(10.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            "📜 ${tip.law}",
                            color = Color.White.copy(alpha = 0.7f),
                            fontSize = 11.sp
                        )

                        // Dot indicators (max 5)
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            val totalDots = minOf(tips.size, 5)
                            val activeDot = currentIndex % totalDots
                            repeat(totalDots) { i ->
                                Box(
                                    modifier = Modifier
                                        .size(if (i == activeDot) 8.dp else 6.dp)
                                        .clip(CircleShape)
                                        .background(
                                            if (i == activeDot) Color.White
                                            else Color.White.copy(alpha = 0.4f)
                                        )
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
