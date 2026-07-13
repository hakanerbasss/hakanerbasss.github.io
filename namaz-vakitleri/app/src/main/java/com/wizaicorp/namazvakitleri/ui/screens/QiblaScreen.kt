package com.wizaicorp.namazvakitleri.ui.screens

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import kotlin.math.*

@SuppressLint("MissingPermission")
@Composable
fun QiblaContent(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val sensorManager = remember {
        context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    }
    val rotationVectorSensor = remember {
        sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
    }
    val locationManager = remember {
        context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    }

    var hasPermission by remember { mutableStateOf(false) }
    var hasLocation   by remember { mutableStateOf(false) }
    var userLat       by remember { mutableStateOf(0.0) }
    var userLon       by remember { mutableStateOf(0.0) }

    // Continuous azimuth tracking — avoids 359→1 wrapping jumps
    var continuousAz by remember { mutableFloatStateOf(0f) }
    val lastRaw      = remember { FloatArray(1) { 0f } }

    val animAzimuth by animateFloatAsState(
        targetValue  = continuousAz,
        animationSpec = tween(150),
        label        = "azimuth"
    )

    // Permission launcher
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        hasPermission = granted
        if (granted) {
            try {
                val loc = locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
                    ?: locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)
                if (loc != null) {
                    userLat = loc.latitude
                    userLon = loc.longitude
                    hasLocation = true
                }
            } catch (_: SecurityException) {}
        }
    }

    // Check permission on first composition
    LaunchedEffect(Unit) {
        val granted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_COARSE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED
        hasPermission = granted
        if (granted) {
            try {
                val loc = locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
                    ?: locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)
                if (loc != null) {
                    userLat = loc.latitude
                    userLon = loc.longitude
                    hasLocation = true
                }
            } catch (_: SecurityException) {}
        }
    }

    // Register rotation vector sensor
    DisposableEffect(sensorManager) {
        val listener = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent) {
                if (event.sensor.type != Sensor.TYPE_ROTATION_VECTOR) return
                val rotMatrix = FloatArray(9)
                SensorManager.getRotationMatrixFromVector(rotMatrix, event.values)
                val orientation = FloatArray(3)
                SensorManager.getOrientation(rotMatrix, orientation)
                val raw = ((Math.toDegrees(orientation[0].toDouble()).toFloat() + 360f) % 360f)
                var d = raw - lastRaw[0]
                if (d > 180f)  d -= 360f
                if (d < -180f) d += 360f
                continuousAz += d
                lastRaw[0] = raw
            }
            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
        }
        rotationVectorSensor?.let {
            sensorManager.registerListener(listener, it, SensorManager.SENSOR_DELAY_GAME)
        }
        onDispose { sensorManager.unregisterListener(listener) }
    }

    // Derived values
    val qibla    = if (hasLocation) qiblaBearing(userLat, userLon) else 0f
    val arrowRot = if (hasLocation) ((qibla - animAzimuth + 720f) % 360f) else 0f
    val isAligned = hasLocation && (arrowRot < 8f || arrowRot > 352f)

    val distance = remember(userLat, userLon, hasLocation) {
        if (!hasLocation) 0f
        else {
            val results = FloatArray(1)
            Location.distanceBetween(userLat, userLon, 21.4225, 39.8262, results)
            results[0] / 1000f
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Spacer(Modifier.height(24.dp))

        // ── Compass box ──────────────────────────────────────────────────────
        Box(modifier = Modifier.size(300.dp)) {

            // Layer 1: Compass rose (rotates opposite to device heading)
            Canvas(
                modifier = Modifier
                    .fillMaxSize()
                    .rotate(-animAzimuth)
            ) {
                val cx     = size.width  / 2f
                val cy     = size.height / 2f
                val radius = size.minDimension / 2f

                // Dark background circle
                drawCircle(color = Color(0xFF0D1B0D), radius = radius)

                // Green border ring
                drawCircle(
                    color  = Color(0xFF1B6B45),
                    radius = radius,
                    style  = Stroke(width = 4.dp.toPx())
                )

                // 72 tick marks (every 5°)
                for (i in 0 until 72) {
                    val isCardinal = i % 18 == 0
                    val isMajor    = i % 6  == 0
                    val angleRad   = Math.toRadians((i * 5.0) - 90.0)
                    val cosA       = cos(angleRad).toFloat()
                    val sinA       = sin(angleRad).toFloat()

                    val tickLen = when {
                        isCardinal -> radius * 0.18f
                        isMajor    -> radius * 0.12f
                        else       -> radius * 0.07f
                    }
                    val tickWidth = when {
                        isCardinal -> 3.dp.toPx()
                        isMajor    -> 2.dp.toPx()
                        else       -> 1.dp.toPx()
                    }
                    val tickColor = when {
                        i == 0     -> Color.Red
                        isCardinal -> Color(0xFFD4AF37)
                        isMajor    -> Color(0xFFD4AF37).copy(alpha = 0.7f)
                        else       -> Color.White.copy(alpha = 0.35f)
                    }

                    val outerR = radius * 0.92f
                    val innerR = outerR - tickLen
                    drawLine(
                        color       = tickColor,
                        start       = Offset(cx + outerR * cosA, cy + outerR * sinA),
                        end         = Offset(cx + innerR * cosA, cy + innerR * sinA),
                        strokeWidth = tickWidth
                    )
                }

                // Cardinal direction labels: K=North(Red), D=East, G=South, B=West (Gold)
                val nativeCanvas = drawContext.canvas.nativeCanvas
                val textPaint = android.graphics.Paint().apply {
                    textSize  = radius * 0.18f
                    textAlign = android.graphics.Paint.Align.CENTER
                    typeface  = android.graphics.Typeface.DEFAULT_BOLD
                    isAntiAlias = true
                }
                val cardinalLabels = listOf("K" to 0, "D" to 18, "G" to 36, "B" to 54)
                for ((label, tick) in cardinalLabels) {
                    val angleRad = Math.toRadians((tick * 5.0) - 90.0)
                    val labelR   = radius * 0.68f
                    val x = cx + labelR * cos(angleRad).toFloat()
                    val y = cy + labelR * sin(angleRad).toFloat() + textPaint.textSize / 3f
                    textPaint.color = if (label == "K") android.graphics.Color.RED
                                      else android.graphics.Color.parseColor("#FFD4AF37")
                    nativeCanvas.drawText(label, x, y, textPaint)
                }
            }

            // Layer 2: Qibla arrow (rotates to point toward Mecca)
            Canvas(
                modifier = Modifier
                    .fillMaxSize()
                    .rotate(arrowRot)
            ) {
                val cx       = size.width  / 2f
                val cy       = size.height / 2f
                val arrowLen = size.minDimension * 0.38f
                val arrowTipY = cy - arrowLen
                val headH    = 20.dp.toPx()
                val headW    = 14.dp.toPx()

                val arrowColor = if (isAligned) Color(0xFFD4AF37) else Color(0xFF1DB36A)

                // Glow line
                drawLine(
                    color       = arrowColor.copy(alpha = 0.25f),
                    start       = Offset(cx, cy),
                    end         = Offset(cx, arrowTipY),
                    strokeWidth = 12.dp.toPx()
                )

                // Arrow body
                drawLine(
                    color       = arrowColor,
                    start       = Offset(cx, cy),
                    end         = Offset(cx, arrowTipY + headH),
                    strokeWidth = 3.dp.toPx()
                )

                // Arrowhead triangle (pointing up)
                val arrowPath = Path().apply {
                    moveTo(cx, arrowTipY)
                    lineTo(cx - headW / 2f, arrowTipY + headH)
                    lineTo(cx + headW / 2f, arrowTipY + headH)
                    close()
                }
                drawPath(arrowPath, color = arrowColor)

                // Kaaba symbol — tiny black square at the arrow tip
                val sq = 7.dp.toPx()
                drawRect(
                    color    = Color.Black,
                    topLeft  = Offset(cx - sq / 2f, arrowTipY - sq / 2f),
                    size     = Size(sq, sq)
                )
            }

            // Layer 3: Center pivot dot
            Surface(
                modifier = Modifier
                    .size(14.dp)
                    .align(Alignment.Center),
                shape = CircleShape,
                color = Color.White
            ) {}
        }

        Spacer(Modifier.height(24.dp))

        // ── Info section ──────────────────────────────────────────────────────
        if (!hasPermission) {
            Button(
                onClick = {
                    permissionLauncher.launch(Manifest.permission.ACCESS_COARSE_LOCATION)
                }
            ) {
                Text("Konum İzni Ver")
            }
        } else {
            if (isAligned) {
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = Color(0xFF1B6B45)
                ) {
                    Text(
                        text     = "✓ Kıbleye Dönüksünüz!",
                        modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp),
                        color    = Color.White,
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp
                    )
                }
            } else {
                Text(
                    text      = "Yeşil oku kıbleye doğrultun",
                    style     = MaterialTheme.typography.bodyMedium,
                    color     = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                    textAlign = TextAlign.Center
                )
            }

            if (hasLocation) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text  = "Kabe'ye ${"%.0f".format(distance)} km",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text  = "Kıble: ${"%.1f".format(qibla)}°",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                )
            }
        }

        Spacer(Modifier.height(24.dp))
    }
}

private fun qiblaBearing(lat: Double, lon: Double): Float {
    val mLat = Math.toRadians(21.4225)
    val mLon = Math.toRadians(39.8262)
    val uLat = Math.toRadians(lat)
    val dLon = mLon - Math.toRadians(lon)
    val y    = sin(dLon) * cos(mLat)
    val x    = cos(uLat) * sin(mLat) - sin(uLat) * cos(mLat) * cos(dLon)
    return ((Math.toDegrees(atan2(y, x)).toFloat() + 360f) % 360f)
}
