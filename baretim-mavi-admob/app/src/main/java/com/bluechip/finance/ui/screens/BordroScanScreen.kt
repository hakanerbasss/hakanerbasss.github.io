package com.bluechip.finance.ui.screens

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.bluechip.finance.ui.components.SectionHeader
import com.bluechip.finance.ui.theme.*
import com.bluechip.finance.util.BordroOcrParser
import com.bluechip.finance.util.BordroScanResult

@Composable
fun BordroScanner(
    onDismiss: () -> Unit,
    onResult: (BordroScanResult) -> Unit
) {
    val context = LocalContext.current
    val colors = LocalAppColors.current

    var selectedUri by remember { mutableStateOf<Uri?>(null) }
    var processing by remember { mutableStateOf(false) }
    var scanResult by remember { mutableStateOf<BordroScanResult?>(null) }
    var errorMsg by remember { mutableStateOf<String?>(null) }

    var editGross     by remember { mutableStateOf("") }
    var editNet       by remember { mutableStateOf("") }
    var editMeal      by remember { mutableStateOf("") }
    var editTransport by remember { mutableStateOf("") }
    var editMonth     by remember { mutableIntStateOf(-1) }

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri ->
        uri ?: return@rememberLauncherForActivityResult
        selectedUri = uri
        processing  = true
        errorMsg    = null
        scanResult  = null
        try {
            val image = InputImage.fromFilePath(context, uri)
            TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
                .process(image)
                .addOnSuccessListener { visionText ->
                    val result = BordroOcrParser.parse(visionText.text)
                    scanResult    = result
                    editGross     = BordroOcrParser.toSalaryString(result.grossSalary)
                    editNet       = BordroOcrParser.toSalaryString(result.netSalary)
                    editMeal      = BordroOcrParser.toSalaryString(result.mealAllowance)
                    editTransport = BordroOcrParser.toSalaryString(result.transportAllowance)
                    if (result.month >= 0) editMonth = result.month
                    processing = false
                }
                .addOnFailureListener { e ->
                    errorMsg  = "OCR hatası: ${e.localizedMessage}"
                    processing = false
                }
        } catch (e: Exception) {
            errorMsg  = "Görsel okunamadı: ${e.localizedMessage}"
            processing = false
        }
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnClickOutside = false)
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(colors.cardBg)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                // ─── Header ───────────────────────────────────────
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.ArrowBack, null, tint = colors.textPrimary)
                    }
                    Text(
                        "Bordro Tara",
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 20.sp,
                        color = colors.textPrimary,
                        modifier = Modifier.weight(1f)
                    )
                }

                // ─── Info card ────────────────────────────────────
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = PurplePrimary.copy(alpha = 0.08f))
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.Top,
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        Icon(Icons.Default.Info, null, tint = PurplePrimary, modifier = Modifier.size(18.dp))
                        Text(
                            "Bordro görselini galeriden seç. Brüt maaş, net maaş ve yardım tutarları " +
                            "otomatik tanınır. Hatalı alanları aktar öncesinde düzeltebilirsin.",
                            fontSize = 12.sp,
                            color = colors.textPrimary,
                            lineHeight = 17.sp
                        )
                    }
                }

                SectionHeader("Görsel Seç", Icons.Default.PhotoLibrary)

                // ─── Pick button ──────────────────────────────────
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(110.dp)
                        .background(
                            if (selectedUri == null) PurplePrimary.copy(alpha = 0.06f)
                            else colors.success.copy(alpha = 0.08f),
                            RoundedCornerShape(16.dp)
                        )
                        .border(
                            1.5.dp,
                            if (selectedUri == null) PurplePrimary.copy(alpha = 0.30f)
                            else colors.success.copy(alpha = 0.50f),
                            RoundedCornerShape(16.dp)
                        )
                        .clickable { launcher.launch("image/*") },
                    contentAlignment = Alignment.Center
                ) {
                    if (selectedUri == null) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            Icon(Icons.Default.FileUpload, null,
                                tint = PurplePrimary, modifier = Modifier.size(36.dp))
                            Text("Bordro görselini seç", color = PurplePrimary,
                                fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                            Text("JPG veya PNG", fontSize = 11.sp, color = colors.textSecondary)
                        }
                    } else {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            Icon(Icons.Default.CheckCircle, null,
                                tint = colors.success, modifier = Modifier.size(32.dp))
                            Text("Görsel seçildi", color = colors.success, fontWeight = FontWeight.SemiBold)
                            Text("Farklı seçmek için tekrar dokun", fontSize = 11.sp,
                                color = colors.textSecondary)
                        }
                    }
                }

                // ─── Processing ───────────────────────────────────
                AnimatedVisibility(visible = processing, enter = fadeIn(), exit = fadeOut()) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = colors.cardGray)
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp).fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(22.dp),
                                color = PurplePrimary,
                                strokeWidth = 2.dp
                            )
                            Column {
                                Text("Bordro okunuyor...", fontWeight = FontWeight.Medium,
                                    color = colors.textPrimary, fontSize = 14.sp)
                                Text("Yazılar tanınıyor, lütfen bekleyin",
                                    fontSize = 11.sp, color = colors.textSecondary)
                            }
                        }
                    }
                }

                // ─── Error ────────────────────────────────────────
                errorMsg?.let { msg ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = colors.error.copy(alpha = 0.10f))
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Icon(Icons.Default.Error, null, tint = colors.error,
                                modifier = Modifier.size(20.dp))
                            Text(msg, color = colors.error, fontSize = 12.sp)
                        }
                    }
                }

                // ─── Extracted fields ─────────────────────────────
                AnimatedVisibility(
                    visible = scanResult != null && !processing,
                    enter = fadeIn() + slideInVertically(initialOffsetY = { it / 4 }),
                    exit  = fadeOut()
                ) {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        SectionHeader("Tanınan Veriler", Icons.Default.FindInPage)

                        Text(
                            "Hatalı alanları düzeltip 'Aktarım Yap' butonuna bas.",
                            fontSize = 12.sp,
                            color = colors.textSecondary
                        )

                        // Gross
                        ScanField(
                            value = editGross,
                            onValueChange = { editGross = it },
                            label = "Brüt Maaş (₺)",
                            iconTint = PurplePrimary,
                            icon = Icons.Default.TrendingUp
                        )

                        // Net — readonly hint
                        ScanField(
                            value = editNet,
                            onValueChange = { editNet = it },
                            label = "Net Maaş (₺) — bilgi amaçlı",
                            iconTint = colors.success,
                            icon = Icons.Default.AccountBalanceWallet
                        )

                        if (editMeal.isNotEmpty()) {
                            ScanField(
                                value = editMeal,
                                onValueChange = { editMeal = it },
                                label = "Yemek Yardımı (₺)",
                                iconTint = colors.warning,
                                icon = Icons.Default.Restaurant
                            )
                        }

                        if (editTransport.isNotEmpty()) {
                            ScanField(
                                value = editTransport,
                                onValueChange = { editTransport = it },
                                label = "Yol Yardımı (₺)",
                                iconTint = colors.info,
                                icon = Icons.Default.DirectionsBus
                            )
                        }

                        if (editMonth >= 0) {
                            val monthNames = listOf(
                                "Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
                                "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"
                            )
                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(12.dp),
                                colors = CardDefaults.cardColors(
                                    containerColor = PurplePrimary.copy(alpha = 0.08f))
                            ) {
                                Row(
                                    modifier = Modifier.padding(12.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    Icon(Icons.Default.DateRange, null,
                                        tint = PurplePrimary, modifier = Modifier.size(18.dp))
                                    Text(
                                        "Bordro dönemi: ${monthNames[editMonth]}",
                                        color = PurplePrimary,
                                        fontWeight = FontWeight.Medium,
                                        fontSize = 13.sp
                                    )
                                }
                            }
                        }

                        // ─── Confirm button ────────────────────────
                        Spacer(Modifier.height(4.dp))
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(54.dp)
                                .shadow(10.dp, RoundedCornerShape(14.dp),
                                    spotColor = PurplePrimary, ambientColor = PurplePrimary)
                                .background(GradientButton, RoundedCornerShape(14.dp))
                                .clickable {
                                    onResult(
                                        BordroScanResult(
                                            grossSalary        = editGross,
                                            netSalary          = editNet,
                                            mealAllowance      = editMeal,
                                            transportAllowance = editTransport,
                                            month              = editMonth
                                        )
                                    )
                                },
                            contentAlignment = Alignment.Center
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.ArrowForward, null,
                                    tint = Color.White, modifier = Modifier.size(20.dp))
                                Spacer(Modifier.width(8.dp))
                                Text("Bordro Ekranına Aktar",
                                    fontWeight = FontWeight.Bold,
                                    color = Color.White,
                                    fontSize = 15.sp)
                            }
                        }

                        Text(
                            "⚠️ Hesaplama sonuçları bordrondaki değerlerden küçük farklılıklar gösterebilir. " +
                            "Brüt maaş ve ay bilgisi aktarılır.",
                            fontSize = 11.sp,
                            color = colors.textSecondary,
                            lineHeight = 15.sp
                        )
                        Spacer(Modifier.height(20.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun ScanField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    iconTint: Color,
    icon: androidx.compose.ui.graphics.vector.ImageVector
) {
    val colors = LocalAppColors.current
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label, fontSize = 12.sp) },
        leadingIcon = { Icon(icon, null, tint = iconTint, modifier = Modifier.size(20.dp)) },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
        shape = RoundedCornerShape(12.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor   = iconTint,
            unfocusedBorderColor = iconTint.copy(alpha = 0.30f),
            focusedContainerColor   = colors.cardBg,
            unfocusedContainerColor = colors.cardBg,
            focusedTextColor   = colors.textPrimary,
            unfocusedTextColor = colors.textPrimary,
            focusedLabelColor   = iconTint,
            unfocusedLabelColor = colors.textSecondary
        )
    )
}
