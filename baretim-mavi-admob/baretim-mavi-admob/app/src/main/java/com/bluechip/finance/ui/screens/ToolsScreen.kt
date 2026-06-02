package com.bluechip.finance.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.data.OvertimeManager
import com.bluechip.finance.data.PaymentManager
import com.bluechip.finance.ui.theme.*

data class ToolItem(val route: String, val title: String, val desc: String, val icon: ImageVector, val color: Color)

@Composable
fun ToolsScreen(onNavigate: (String) -> Unit) {
    val colors = LocalAppColors.current

    val featured = listOf(
        ToolItem("severance", "Kıdem & İhbar Tazminatı", "Tazminat hesapla", Icons.Default.AccountBalance, PurplePrimary),
        ToolItem("tax", "Vergi & Bordro", "Net maaş hesapla", Icons.Default.Receipt, Color(0xFF1565C0)),
        ToolItem("overtime", "Fazla Mesai", "Mesai ücreti hesapla", Icons.Default.AccessTime, Color(0xFFE65100)),
    )

    val otherTools = listOf(
        ToolItem("leave", "Yıllık İzin", "İzin hakkı hesapla", Icons.Default.DateRange, Color(0xFF6A1B9A)),
        ToolItem("bordro", "Bordro", "Tam bordro simülasyonu", Icons.Default.Description, Color(0xFF1565C0)),
        ToolItem("unemployment", "İşsizlik Maaşı", "İşsizlik ödeneği", Icons.Default.MoneyOff, Color(0xFFE65100)),
        ToolItem("retirement", "Emeklilik", "Ne zaman emekli olurum?", Icons.Default.Elderly, Color(0xFF2E7D32)),
        ToolItem("inflation", "Enflasyon", "Paranın gerçek değeri", Icons.Default.TrendingDown, Color(0xFFC62828)),
        ToolItem("comparison", "Maaş Karşılaştır", "İki teklifi karşılaştır", Icons.Default.CompareArrows, Color(0xFF00838F)),
        ToolItem("rights", "Hakkımı Arıyorum", "Tazminatlı ayrılabilir miyim?", Icons.Default.Gavel, Color(0xFFC62828)),
        ToolItem("payments", "Ödeme Takip", "Fatura ve kira takibi", Icons.Default.Payment, Color(0xFF00838F)),
        ToolItem("special_days", "Özel Günler", "Doğum günü, yıldönümü takip et", Icons.Default.Celebration, Color(0xFFAD1457)),
        ToolItem("savings",  "Birikimlerim", "Kripto, metal ve doviz", Icons.Default.Savings, Color(0xFF7C3AED)),
    )

    val context2b = LocalContext.current
    val thisMonthOtTotal = remember { OvertimeManager.thisMonthTotal(context2b) }
    val thisMonthOtCount = remember { OvertimeManager.thisMonthRecords(context2b).size }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        ProfileSummaryCard(onNavigate)

        Text("Önemli Araçlar", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)

        featured.forEach { tool ->
            Card(
                modifier = Modifier.fillMaxWidth().height(90.dp).clickable { onNavigate(tool.route) },
                shape = RoundedCornerShape(20.dp),
                elevation = CardDefaults.cardElevation(2.dp),
                colors = CardDefaults.cardColors(containerColor = colors.cardBg)
            ) {
                Row(
                    modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier.size(52.dp).background(tool.color.copy(alpha = 0.12f), RoundedCornerShape(16.dp)),
                        contentAlignment = Alignment.Center
                    ) { Icon(tool.icon, null, tint = tool.color, modifier = Modifier.size(28.dp)) }
                    Spacer(Modifier.width(16.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(tool.title, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary)
                        Text(tool.desc, fontSize = 12.sp, color = colors.textSecondary)
                    }
                    Icon(Icons.Default.ChevronRight, null, tint = colors.textSecondary, modifier = Modifier.size(22.dp))
                }
            }
        }

        // Mesai Takip widget karti
        Card(
            modifier = Modifier.fillMaxWidth().clickable { onNavigate("overtime_track") },
            shape = RoundedCornerShape(20.dp),
            elevation = CardDefaults.cardElevation(2.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    modifier = Modifier.size(52.dp).background(Color(0xFFE65100).copy(alpha = 0.12f), RoundedCornerShape(16.dp)),
                    contentAlignment = Alignment.Center
                ) { Icon(Icons.Default.Timer, null, tint = Color(0xFFE65100), modifier = Modifier.size(28.dp)) }
                Spacer(Modifier.width(16.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text("Mesai Takip", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary)
                    if (thisMonthOtCount > 0)
                        Text("Bu ay: $thisMonthOtCount kayit  •  ${com.bluechip.finance.ui.components.formatMoney(thisMonthOtTotal)} TL",
                            fontSize = 12.sp, color = colors.textSecondary)
                    else
                        Text("Gunluk mesailerinizi kaydedin", fontSize = 12.sp, color = colors.textSecondary)
                }
                Icon(Icons.Default.ChevronRight, null, tint = colors.textSecondary, modifier = Modifier.size(22.dp))
            }
        }

        Text("Diğer Araçlar", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)

        otherTools.chunked(2).forEach { row ->
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                row.forEach { tool ->
                    Card(
                        modifier = Modifier.weight(1f).height(120.dp).clickable { onNavigate(tool.route) },
                        shape = RoundedCornerShape(20.dp),
                        elevation = CardDefaults.cardElevation(2.dp),
                        colors = CardDefaults.cardColors(containerColor = colors.cardBg)
                    ) {
                        Column(
                            modifier = Modifier.fillMaxSize().padding(14.dp),
                            verticalArrangement = Arrangement.Center,
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Box(
                                modifier = Modifier.size(44.dp).background(tool.color.copy(alpha = 0.12f), RoundedCornerShape(14.dp)),
                                contentAlignment = Alignment.Center
                            ) { Icon(tool.icon, null, tint = tool.color, modifier = Modifier.size(24.dp)) }
                            Spacer(Modifier.height(8.dp))
                            Text(tool.title, fontWeight = FontWeight.Bold, fontSize = 12.sp, color = colors.textPrimary, textAlign = TextAlign.Center)
                            Text(tool.desc, fontSize = 10.sp, color = colors.textSecondary, textAlign = TextAlign.Center, maxLines = 2)
                        }
                    }
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }

        Text("Ayarlar", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.textPrimary)

        var showClearDialog by remember { mutableStateOf(false) }
        val context2 = LocalContext.current

        Card(
            modifier = Modifier.fillMaxWidth().clickable { showClearDialog = true },
            shape = RoundedCornerShape(16.dp),
            elevation = CardDefaults.cardElevation(2.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardBg)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    modifier = Modifier.size(44.dp).background(
                        androidx.compose.ui.graphics.Color(0xFFD32F2F).copy(alpha = 0.12f),
                        RoundedCornerShape(14.dp)
                    ),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Default.Delete, null,
                        tint = androidx.compose.ui.graphics.Color(0xFFD32F2F),
                        modifier = Modifier.size(22.dp))
                }
                Spacer(Modifier.width(14.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text("Ödeme takip verilerini temizle",
                        fontWeight = FontWeight.Medium, fontSize = 14.sp, color = colors.textPrimary)
                    Text("Tüm ödeme geçmişini sil",
                        fontSize = 12.sp, color = colors.textSecondary)
                }
                Icon(Icons.Default.ChevronRight, null,
                    tint = colors.textSecondary, modifier = Modifier.size(22.dp))
            }
        }

        if (showClearDialog) {
            androidx.compose.ui.window.Dialog(onDismissRequest = { showClearDialog = false }) {
                Card(
                    shape = RoundedCornerShape(20.dp),
                    colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                    elevation = CardDefaults.cardElevation(8.dp)
                ) {
                    Column(modifier = Modifier.padding(24.dp)) {
                        Text("Geçmişi Temizle",
                            fontWeight = FontWeight.Bold, fontSize = 17.sp, color = colors.textPrimary)
                        Spacer(Modifier.height(8.dp))
                        Text("Tüm ödeme geçmişi silinecek. Emin misiniz?",
                            fontSize = 14.sp, color = colors.textSecondary)
                        Spacer(Modifier.height(20.dp))
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                            TextButton(onClick = { showClearDialog = false }) {
                                Text("İptal", color = colors.textSecondary)
                            }
                            Spacer(Modifier.width(8.dp))
                            TextButton(onClick = {
                                PaymentManager.clearRecords(context2)
                                showClearDialog = false
                            }) {
                                Text("Temizle",
                                    color = androidx.compose.ui.graphics.Color(0xFFD32F2F),
                                    fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))
    }
}

@Composable
fun ProfileSummaryCard(onNavigate: (String) -> Unit) {
    val colors = LocalAppColors.current
    val context = LocalContext.current
    val profile = remember { com.bluechip.finance.data.ProfileManager(context).load() }

    Card(
        modifier = Modifier.fillMaxWidth().clickable { onNavigate("profile") },
        shape = RoundedCornerShape(20.dp),
        elevation = CardDefaults.cardElevation(2.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier.size(52.dp).background(
                    Brush.radialGradient(listOf(PurplePrimaryLight, PurplePrimary)), CircleShape
                ),
                contentAlignment = Alignment.Center
            ) { Icon(Icons.Default.Person, null, tint = Color.White, modifier = Modifier.size(28.dp)) }
            Spacer(Modifier.width(14.dp))
            Column(modifier = Modifier.weight(1f)) {
                if (profile.isLoggedIn && profile.name.isNotBlank()) {
                    Text(profile.name, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary)
                    if (profile.netSalary > 0)
                        Text("Net: ${profile.netSalary.toInt()} ₺", fontSize = 13.sp, color = colors.textSecondary)
                    else
                        Text("Maas bilgisi eksik", fontSize = 12.sp, color = colors.warning)
                } else {
                    Text("Profilim", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary)
                    Text("Bilgilerini kaydet, hesaplamalar otomatik dolsun", fontSize = 12.sp, color = colors.textSecondary)
                }
            }
            Icon(Icons.Default.ChevronRight, null, tint = colors.textSecondary, modifier = Modifier.size(22.dp))
        }
    }
}
