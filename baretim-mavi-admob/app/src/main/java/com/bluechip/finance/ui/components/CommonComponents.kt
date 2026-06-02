package com.bluechip.finance.ui.components

import androidx.compose.animation.AnimatedVisibility
import com.commandiron.wheel_picker_compose.WheelDatePicker
import com.commandiron.wheel_picker_compose.core.WheelPickerDefaults
import java.time.LocalDate
import java.time.ZoneId
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.unit.Dp
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.layout.boundsInRoot
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.data.HistoryEntry
import com.bluechip.finance.data.HistoryManager
import com.bluechip.finance.ui.theme.*

@Composable
fun SectionHeader(title: String, icon: ImageVector? = null, onInfoClick: (() -> Unit)? = null) {
    val colors = LocalAppColors.current
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        if (icon != null) { Icon(icon, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(24.dp)); Spacer(Modifier.width(8.dp)) }
        Text(title, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary, modifier = Modifier.weight(1f))
        if (onInfoClick != null) { IconButton(onClick = onInfoClick) { Icon(Icons.Default.Info, "Bilgi", tint = MaterialTheme.colorScheme.primary) } }
    }
}

@Composable
fun CurrencyField(value: String, onValueChange: (String) -> Unit, label: String, modifier: Modifier = Modifier, isQuantity: Boolean = false) {
    val colors = LocalAppColors.current
    val regex  = if (isQuantity) Regex("^\\d*\\.?\\d{0,8}$") else Regex("^\\d*\\.?\\d{0,2}$")
    OutlinedTextField(
        value = value,
        onValueChange = { if (it.isEmpty() || it.matches(regex)) onValueChange(it) },
        label = { Text(label, fontSize = 13.sp) },
        leadingIcon = {
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.12f), RoundedCornerShape(10.dp)),
                contentAlignment = Alignment.Center
            ) {
                Text("₺", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = MaterialTheme.colorScheme.primary)
            }
        },
        modifier = modifier.fillMaxWidth(),
        singleLine = true,
        shape = RoundedCornerShape(16.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = MaterialTheme.colorScheme.primary,
            unfocusedBorderColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.2f),
            focusedContainerColor = colors.cardBg,
            unfocusedContainerColor = colors.cardBg,
            focusedTextColor = colors.textPrimary,
            unfocusedTextColor = colors.textPrimary,
            focusedLabelColor = MaterialTheme.colorScheme.primary,
            unfocusedLabelColor = colors.textSecondary
        )
    )
}

@Composable
fun NumberField(value: String, onValueChange: (String) -> Unit, label: String, modifier: Modifier = Modifier) {
    val colors = LocalAppColors.current
    OutlinedTextField(
        value = value,
        onValueChange = { if (it.isEmpty() || it.matches(Regex("^\\d*\\.?\\d*$"))) onValueChange(it) },
        label = { Text(label, fontSize = 13.sp) },
        modifier = modifier.fillMaxWidth(),
        singleLine = true,
        shape = RoundedCornerShape(16.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = MaterialTheme.colorScheme.primary,
            unfocusedBorderColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.2f),
            focusedContainerColor = colors.cardBg,
            unfocusedContainerColor = colors.cardBg,
            focusedTextColor = colors.textPrimary,
            unfocusedTextColor = colors.textPrimary,
            focusedLabelColor = MaterialTheme.colorScheme.primary,
            unfocusedLabelColor = colors.textSecondary
        )
    )
}

@Composable
fun ActionButtons(onCalculate: () -> Unit, onReset: () -> Unit) {
    val colors = LocalAppColors.current
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(
            modifier = Modifier
                .weight(1f)
                .height(54.dp)
                .background(
                    Brush.horizontalGradient(listOf(PurplePrimary, PurplePrimaryDark)),
                    RoundedCornerShape(16.dp)
                )
                .then(Modifier.border(0.dp, Color.Transparent, RoundedCornerShape(16.dp))),
            contentAlignment = Alignment.Center
        ) {
            androidx.compose.material3.TextButton(
                onClick = onCalculate,
                modifier = Modifier.fillMaxSize(),
                shape = RoundedCornerShape(16.dp)
            ) {
                Icon(Icons.Default.Calculate, null, modifier = Modifier.size(20.dp), tint = Color.White)
                Spacer(Modifier.width(8.dp))
                Text("HESAPLA", fontWeight = FontWeight.Bold, color = Color.White, fontSize = 15.sp)
            }
        }
        OutlinedButton(
            onClick = onReset,
            modifier = Modifier.weight(1f).height(54.dp),
            shape = RoundedCornerShape(16.dp),
            border = androidx.compose.foundation.BorderStroke(1.5.dp, MaterialTheme.colorScheme.primary)
        ) {
            Text("TEMİZLE", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
        }
    }
}

@Composable
fun ResultCard(visible: Boolean, content: @Composable ColumnScope.() -> Unit) {
    val colors = LocalAppColors.current
    val context = LocalContext.current
    val view = LocalView.current
    var cardBounds by remember { mutableStateOf<android.graphics.Rect?>(null) }
    AnimatedVisibility(visible = visible, enter = fadeIn() + expandVertically()) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 16.dp)
                .onGloballyPositioned { coords ->
                    val r = coords.boundsInRoot()
                    cardBounds = android.graphics.Rect(
                        r.left.toInt(), r.top.toInt(),
                        r.right.toInt(), r.bottom.toInt()
                    )
                },
            shape = RoundedCornerShape(16.dp),
            elevation = CardDefaults.cardElevation(8.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardGray)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                content()
                Spacer(Modifier.height(4.dp))
                HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                OutlinedButton(
                    onClick = { cardBounds?.let { captureAndShareCard(context, view, it) } },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Icon(Icons.Default.CameraAlt, null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Gorsel Paylas")
                }
            }
        }
    }
}

@Composable
fun ResultLine(label: String, value: String, color: Color = LocalAppColors.current.textPrimary, bold: Boolean = false) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, fontSize = if (bold) 15.sp else 13.sp, fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal, color = color)
        Text(value, fontSize = if (bold) 15.sp else 13.sp, fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal, color = color)
    }
}

@Composable
fun BigResult(label: String, value: String, color: Color = LocalAppColors.current.success) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, fontSize = 13.sp, color = color); Text(value, fontSize = 24.sp, fontWeight = FontWeight.Bold, color = color)
    }
}

@Composable
fun ShareButton(onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp)) { Text("PAYLAŞ 📤") }
}

@Composable
fun DatePickerButton(text: String, onClick: () -> Unit) {
    val colors = LocalAppColors.current
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth().height(54.dp),
        shape = RoundedCornerShape(16.dp),
        border = androidx.compose.foundation.BorderStroke(1.5.dp, PurplePrimary.copy(alpha = 0.4f)),
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = PurplePrimary.copy(alpha = 0.06f),
            contentColor = PurplePrimary
        )
    ) {
        Box(
            modifier = Modifier
                .size(32.dp)
                .background(PurplePrimary.copy(alpha = 0.12f), RoundedCornerShape(8.dp)),
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Default.DateRange, null, modifier = Modifier.size(18.dp), tint = PurplePrimary)
        }
        Spacer(Modifier.width(10.dp))
        Text(text, color = if (text == "Tarih Seç") colors.textSecondary else colors.textPrimary, fontSize = 14.sp)
        Spacer(Modifier.weight(1f))
    }
}

@Composable
fun SelectorButton(text: String, onClick: () -> Unit) {
    val colors = LocalAppColors.current
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth().height(54.dp),
        shape = RoundedCornerShape(16.dp),
        border = androidx.compose.foundation.BorderStroke(1.5.dp, PurplePrimary.copy(alpha = 0.4f)),
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = PurplePrimary.copy(alpha = 0.06f),
            contentColor = PurplePrimary
        )
    ) {
        Text(text, color = colors.textPrimary, fontSize = 14.sp)
        Spacer(Modifier.weight(1f))
        Icon(Icons.Default.KeyboardArrowDown, null, modifier = Modifier.size(20.dp), tint = PurplePrimary)
    }
}

@Composable
fun UpdateStatusBar(lastUpdate: String, onRefresh: () -> Unit) {
    val colors = LocalAppColors.current
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text("📅 Son güncelleme: $lastUpdate", fontSize = 12.sp, color = colors.success, modifier = Modifier.weight(1f))
        IconButton(onClick = onRefresh, modifier = Modifier.size(32.dp)) {
            Icon(Icons.Default.Refresh, "Güncelle", tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
fun DisclaimerText() {
    val colors = LocalAppColors.current
    Text(
        "⚠️ Bu hesaplama bilgilendirme amaçlıdır, resmi bordro yerine geçmez. Kesin sonuçlar için mali müşavirinize danışınız.",
        fontSize = 11.sp, color = colors.textSecondary, lineHeight = 15.sp, modifier = Modifier.padding(top = 12.dp)
    )
}

@Composable
fun ProfileAutoFillNote() {
    Text("✓ Profilden yuklendi", fontSize = 10.sp, color = LocalAppColors.current.success)
}

// Profilden Doldur butonu - her ekranda ActionButtons'in ustune koy
@Composable
fun ProfileFillButton(onClick: () -> Unit) {
    val colors = LocalAppColors.current
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, PurplePrimary.copy(alpha = 0.4f)),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = PurplePrimary)
    ) {
        Icon(Icons.Default.Person, contentDescription = null, modifier = Modifier.size(16.dp))
        Spacer(Modifier.width(6.dp))
        Text("Profilden Doldur", fontSize = 13.sp, fontWeight = FontWeight.Medium)
    }
}

// Scrollable ay seçim dialog - Aralık ayı fix
@Composable
fun MonthPickerDialog(
    selectedMonth: Int,
    onSelect: (Int) -> Unit,
    onDismiss: () -> Unit
) {
    val colors = LocalAppColors.current
    val months = listOf("Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık")
    var tempSelected by remember { mutableIntStateOf(selectedMonth) }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            elevation = CardDefaults.cardElevation(8.dp)
        ) {
            Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text("Ay Seçin", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = colors.textPrimary)

                // 3'lü grid buton seçici
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    months.chunked(3).forEachIndexed { rowIdx, rowMonths ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            rowMonths.forEachIndexed { colIdx, month ->
                                val idx = rowIdx * 3 + colIdx
                                val isSelected = tempSelected == idx
                                Box(
                                    modifier = Modifier
                                        .weight(1f)
                                        .background(
                                            if (isSelected) PurplePrimary
                                            else PurplePrimary.copy(alpha = 0.08f),
                                            RoundedCornerShape(12.dp)
                                        )
                                        .clickable { tempSelected = idx }
                                        .padding(vertical = 10.dp),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        month,
                                        fontSize = 13.sp,
                                        fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                        color = if (isSelected) Color.White else colors.textPrimary,
                                        textAlign = TextAlign.Center
                                    )
                                }
                            }
                        }
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)
                    ) { Text("İptal") }
                    Button(
                        onClick = { onSelect(tempSelected); onDismiss() },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PurplePrimary)
                    ) { Text("Seç") }
                }
            }
        }
    }
}

@Composable
fun HistoryCard(
    screenId: String,
    onRestore: (salary: String) -> Unit
) {
    val context = LocalContext.current
    val colors  = LocalAppColors.current
    var entries by remember { mutableStateOf<List<HistoryEntry>>(emptyList()) }
    var expanded by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        entries = HistoryManager.load(context, screenId)
    }

    if (entries.isEmpty()) return

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardGray),
        elevation = CardDefaults.cardElevation(2.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.History, null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Son Hesaplamalar", fontSize = 13.sp,
                        fontWeight = FontWeight.Bold, color = colors.textPrimary)
                }
                IconButton(
                    onClick = { expanded = !expanded },
                    modifier = Modifier.size(28.dp)
                ) {
                    Icon(
                        if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        null, tint = colors.textSecondary,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }

            if (expanded) {
                Spacer(Modifier.height(8.dp))
                entries.forEach { entry ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(entry.label, fontSize = 12.sp,
                                color = colors.textPrimary, fontWeight = FontWeight.Medium)
                            Text(entry.resultSummary, fontSize = 11.sp,
                                color = colors.textSecondary)
                        }
                        TextButton(
                            onClick = { onRestore(entry.salary) },
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                        ) {
                            Text("Yukle", fontSize = 11.sp,
                                color = MaterialTheme.colorScheme.primary)
                        }
                    }
                    HorizontalDivider(modifier = Modifier.padding(vertical = 2.dp))
                }
            }
        }
    }
}

@Composable
fun PdfDownloadButton(
    label: String,
    assetFileName: String,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current

    OutlinedButton(
        onClick = {
            try {
                val inputStream = context.assets.open(assetFileName)
                val bytes = inputStream.readBytes()
                inputStream.close()

                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
                    // Android 10+ — MediaStore ile kaydet
                    val values = android.content.ContentValues().apply {
                        put(android.provider.MediaStore.Downloads.DISPLAY_NAME, assetFileName)
                        put(android.provider.MediaStore.Downloads.MIME_TYPE, "application/pdf")
                        put(android.provider.MediaStore.Downloads.IS_PENDING, 1)
                    }
                    val resolver = context.contentResolver
                    val uri = resolver.insert(
                        android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    if (uri != null) {
                        resolver.openOutputStream(uri)?.use { it.write(bytes) }
                        values.clear()
                        values.put(android.provider.MediaStore.Downloads.IS_PENDING, 0)
                        resolver.update(uri, values, null, null)
                        android.widget.Toast.makeText(
                            context,
                            "✅ İndirildi: $assetFileName",
                            android.widget.Toast.LENGTH_LONG
                        ).show()
                    }
                } else {
                    // Android 9 ve altı
                    val downloadsDir = android.os.Environment.getExternalStoragePublicDirectory(
                        android.os.Environment.DIRECTORY_DOWNLOADS)
                    downloadsDir.mkdirs()
                    val outFile = java.io.File(downloadsDir, assetFileName)
                    outFile.writeBytes(bytes)
                    android.widget.Toast.makeText(
                        context,
                        "✅ İndirildi: Downloads/$assetFileName",
                        android.widget.Toast.LENGTH_LONG
                    ).show()
                }
            } catch (e: Exception) {
                android.widget.Toast.makeText(
                    context,
                    "Hata: ${e.message}",
                    android.widget.Toast.LENGTH_SHORT
                ).show()
            }
        },
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(10.dp)
    ) {
        Icon(Icons.Default.Download, null, modifier = Modifier.size(16.dp))
        Spacer(Modifier.width(6.dp))
        Text(label, fontSize = 12.sp)
    }
}

fun formatMoney(amount: Double): String = String.format("%,.2f", amount).replace(',', 'X').replace('.', ',').replace('X', '.')
fun formatNumber(amount: Double): String = String.format("%,.0f", amount).replace(',', '.')

// Kripto ve metal miktar gosterimi: trailing zero yok, max 8 decimal
fun formatQuantity(amount: Double): String {
    if (amount == 0.0) return "0"
    // Tam sayiysa nokta gosterme
    if (amount == kotlin.math.floor(amount) && amount < 1_000_000_000.0) {
        return String.format("%,.0f", amount).replace(',', '.')
    }
    // Ondalikli: gereksiz sifirları kes, max 8 basamak
    val s = "%.8f".format(amount).trimEnd('0').trimEnd('.')
    // Tam kismi binlik noktalı yap
    val dotIdx = s.indexOf('.')
    return if (dotIdx < 0) {
        String.format("%,.0f", amount).replace(',', '.')
    } else {
        val intPart = String.format("%,.0f", s.substring(0, dotIdx).toDouble()).replace(',', '.')
        val decPart = s.substring(dotIdx) // ".00001" gibi
        intPart + decPart
    }
}

fun captureAndShareCard(
    context: android.content.Context,
    view: android.view.View,
    bounds: android.graphics.Rect
) {
    val window = (context as? android.app.Activity)?.window ?: return
    val insetsController = androidx.core.view.WindowInsetsControllerCompat(window, window.decorView)

    // 1. Sistem UI'yi gizle (status bar + navigation bar)
    insetsController.hide(
        androidx.core.view.WindowInsetsCompat.Type.statusBars() or
        androidx.core.view.WindowInsetsCompat.Type.navigationBars()
    )
    insetsController.systemBarsBehavior =
        androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE

    // 2. UI render icin kisa gecikme, sonra screenshot al
    view.postDelayed({
        try {
            view.setLayerType(android.view.View.LAYER_TYPE_SOFTWARE, null)
            val full = android.graphics.Bitmap.createBitmap(
                view.width, view.height, android.graphics.Bitmap.Config.ARGB_8888
            )
            view.draw(android.graphics.Canvas(full))
            view.setLayerType(android.view.View.LAYER_TYPE_HARDWARE, null)

            val l = bounds.left.coerceAtLeast(0)
            val t = bounds.top.coerceAtLeast(0)
            val w = minOf(bounds.width(), full.width - l).coerceAtLeast(1)
            val h = minOf(bounds.height(), full.height - t).coerceAtLeast(1)
            val cropped = android.graphics.Bitmap.createBitmap(full, l, t, w, h)

            val values = android.content.ContentValues().apply {
                put(android.provider.MediaStore.Images.Media.DISPLAY_NAME,
                    "baretim_${System.currentTimeMillis()}.png")
                put(android.provider.MediaStore.Images.Media.MIME_TYPE, "image/png")
                if (android.os.Build.VERSION.SDK_INT >= 29)
                    put(android.provider.MediaStore.Images.Media.RELATIVE_PATH, "Pictures/BaretimMavi")
            }
            val uri = context.contentResolver.insert(
                android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values
            ) ?: return@postDelayed

            context.contentResolver.openOutputStream(uri)?.use {
                cropped.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
            }

            // 3. Sistem UI'yi geri ac
            insetsController.show(
                androidx.core.view.WindowInsetsCompat.Type.statusBars() or
                androidx.core.view.WindowInsetsCompat.Type.navigationBars()
            )

            // 4. Paylas
            context.startActivity(
                android.content.Intent.createChooser(
                    android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                        type = "image/png"
                        putExtra(android.content.Intent.EXTRA_STREAM, uri)
                        addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }, "Sonucu Paylas"
                )
            )
        } catch (e: Exception) {
            insetsController.show(
                androidx.core.view.WindowInsetsCompat.Type.statusBars() or
                androidx.core.view.WindowInsetsCompat.Type.navigationBars()
            )
            android.widget.Toast.makeText(context,
                "Gorsel alinamadi: ${e.message}", android.widget.Toast.LENGTH_SHORT).show()
        }
    }, 300L) // 300ms sistem UI kaybolmasi icin bekle
}

@Composable
fun WheelDatePickerDialog(
    title: String = "Tarih Seçin",
    onDismiss: () -> Unit,
    onDateSelected: (java.util.Calendar) -> Unit
) {
    val colors = LocalAppColors.current
    var selectedDate by remember { mutableStateOf(LocalDate.now()) }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg),
            elevation = CardDefaults.cardElevation(8.dp)
        ) {
            Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text(title, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = colors.textPrimary)

                WheelDatePicker(
                    startDate = selectedDate,
                    textColor = colors.textPrimary,
                    rowCount = 5,
                    selectorProperties = WheelPickerDefaults.selectorProperties(
                        color = PurplePrimary.copy(alpha = 0.12f),
                        border = androidx.compose.foundation.BorderStroke(1.dp, PurplePrimary.copy(alpha = 0.3f))
                    ),
                    onSnappedDate = { selectedDate = it }
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)
                    ) { Text("İptal") }
                    Button(
                        onClick = {
                            val cal = java.util.Calendar.getInstance()
                            cal.set(selectedDate.year, selectedDate.monthValue - 1, selectedDate.dayOfMonth)
                            onDateSelected(cal)
                            onDismiss()
                        },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PurplePrimary)
                    ) { Text("Tamam") }
                }
            }
        }
    }
}

