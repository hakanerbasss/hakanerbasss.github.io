package com.bluechip.finance.ui.components

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

private const val PREFS_NAME = "support_card_prefs"
private const val KEY_SHOWN  = "support_card_shown"

@Composable
fun SupportUsCard(
    visible: Boolean = true,
    forceShow: Boolean = false,
    onForceDismiss: (() -> Unit)? = null
) {
    val context = LocalContext.current
    val prefs   = remember { context.getSharedPreferences(PREFS_NAME, android.content.Context.MODE_PRIVATE) }
    var alreadyShown by remember { mutableStateOf(prefs.getBoolean(KEY_SHOWN, false)) }

    if (!visible || (!forceShow && alreadyShown)) return

    LaunchedEffect(Unit) {
        if (!forceShow) prefs.edit().putBoolean(KEY_SHOWN, true).apply()
    }

    fun dismiss() {
        if (forceShow) { onForceDismiss?.invoke() }
        else { alreadyShown = true; prefs.edit().putBoolean(KEY_SHOWN, true).apply() }
    }

    var selectedStar by remember { mutableIntStateOf(0) }
    val inf = rememberInfiniteTransition(label = "sup")
    val sparkleAngle by inf.animateFloat(
        initialValue = 0f, targetValue = 360f,
        animationSpec = infiniteRepeatable(tween(10000, easing = LinearEasing)), label = "ang"
    )
    val sparkleAlpha by inf.animateFloat(
        initialValue = 0.25f, targetValue = 0.7f,
        animationSpec = infiniteRepeatable(tween(1800, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "alp"
    )
    val pulse by inf.animateFloat(
        initialValue = 1f, targetValue = 1.05f,
        animationSpec = infiniteRepeatable(tween(2000, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "pls"
    )

    LaunchedEffect(Unit) {
        delay(350)
        for (i in 1..5) { selectedStar = i; delay(110) }
    }

    Card(
        modifier  = Modifier.fillMaxWidth().padding(top = 14.dp),
        shape     = RoundedCornerShape(24.dp),
        elevation = CardDefaults.cardElevation(10.dp)
    ) {
        Box(
            modifier = Modifier.fillMaxWidth().background(
                brush = Brush.linearGradient(
                    colors = listOf(Color(0xFF3A0068), Color(0xFF6A1B9A), Color(0xFF8E24AA), Color(0xFFAB47BC)),
                    start = Offset(0f, 0f),
                    end = Offset(Float.POSITIVE_INFINITY, Float.POSITIVE_INFINITY)
                )
            )
        ) {
            Canvas(modifier = Modifier.matchParentSize()) {
                val w = size.width; val h = size.height
                drawCircle(color = Color.White.copy(alpha = 0.06f), radius = h * 0.9f, center = Offset(-h * 0.2f, -h * 0.2f))
                drawCircle(color = Color.White.copy(alpha = 0.05f), radius = h * 0.75f, center = Offset(w + h * 0.1f, h + h * 0.1f))
                val stars = listOf(
                    Offset(w*0.06f, h*0.18f) to 10f, Offset(w*0.94f, h*0.12f) to 8f,
                    Offset(w*0.12f, h*0.82f) to 7f,  Offset(w*0.87f, h*0.78f) to 9f,
                    Offset(w*0.50f, h*0.08f) to 6f,  Offset(w*0.22f, h*0.52f) to 5f,
                    Offset(w*0.78f, h*0.52f) to 7f,  Offset(w*0.65f, h*0.25f) to 4f
                )
                stars.forEachIndexed { idx, (pos, sz) ->
                    rotate(degrees = sparkleAngle + idx * 45f, pivot = pos) {
                        val path = Path().apply {
                            moveTo(pos.x, pos.y - sz)
                            lineTo(pos.x + sz*0.22f, pos.y - sz*0.22f); lineTo(pos.x + sz, pos.y)
                            lineTo(pos.x + sz*0.22f, pos.y + sz*0.22f); lineTo(pos.x, pos.y + sz)
                            lineTo(pos.x - sz*0.22f, pos.y + sz*0.22f); lineTo(pos.x - sz, pos.y)
                            lineTo(pos.x - sz*0.22f, pos.y - sz*0.22f); close()
                        }
                        drawPath(path = path, color = Color(0xFFFFD700).copy(alpha = sparkleAlpha * (0.4f + idx * 0.04f)))
                    }
                }
            }

            Column(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 22.dp, vertical = 20.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Surface(
                    shape = RoundedCornerShape(30.dp),
                    color = Color.White.copy(alpha = 0.18f)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 5.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        Text(text = "\uD83D\uDC68\u200D\uD83D\uDCBB", fontSize = 15.sp)
                        Text(text = "Solo Gelistirici",
                            color = Color.White, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    }
                }

                Text(text = "Bu uygulamay\u0131 tek ba\u015f\u0131ma",
                    fontSize = 17.sp, fontWeight = FontWeight.ExtraBold,
                    color = Color.White, textAlign = TextAlign.Center)
                Text(text = "geli\u015ftiriyorum \uD83D\uDE4F",
                    fontSize = 17.sp, fontWeight = FontWeight.ExtraBold,
                    color = Color.White, textAlign = TextAlign.Center)
                Text(text = "Bir yorum veya y\u0131ld\u0131z \u00e7ok b\u00fcy\u00fck destek olur!",
                    fontSize = 13.sp, color = Color.White.copy(alpha = 0.88f),
                    textAlign = TextAlign.Center, lineHeight = 19.sp)

                Spacer(modifier = Modifier.height(2.dp))

                Row(
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    (1..5).forEach { star ->
                        val filled = star <= selectedStar
                        val sc by animateFloatAsState(
                            targetValue = if (filled) pulse else 1f,
                            animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy),
                            label = "s$star"
                        )
                        Icon(
                            imageVector = Icons.Default.Star,
                            contentDescription = "$star yildiz",
                            tint = if (filled) Color(0xFFFFD700) else Color.White.copy(alpha = 0.35f),
                            modifier = Modifier.size((30f * sc).dp).clickable { selectedStar = star }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(4.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Button(
                        onClick = {
                            dismiss()
                            try { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.bluechip.finance"))) }
                            catch (_: Exception) { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=com.bluechip.finance"))) }
                        },
                        modifier = Modifier.weight(1f).height(46.dp),
                        shape    = RoundedCornerShape(14.dp),
                        colors   = ButtonDefaults.buttonColors(containerColor = Color(0xFFFFD700), contentColor = Color(0xFF3A0068)),
                        elevation = ButtonDefaults.buttonElevation(6.dp)
                    ) { Text(text = "\u2B50 Yorum B\u0131rak", fontWeight = FontWeight.ExtraBold, fontSize = 13.sp) }

                    OutlinedButton(
                        onClick  = { dismiss() },
                        modifier = Modifier.weight(1f).height(46.dp),
                        shape    = RoundedCornerShape(14.dp),
                        colors   = ButtonDefaults.outlinedButtonColors(contentColor = Color.White),
                        border   = androidx.compose.foundation.BorderStroke(width = 1.5.dp, color = Color.White.copy(alpha = 0.55f))
                    ) { Text(text = "\uD83D\uDE4F Simdi Degil", fontWeight = FontWeight.Bold, fontSize = 12.sp) }
                }
            }
        }
    }
}
