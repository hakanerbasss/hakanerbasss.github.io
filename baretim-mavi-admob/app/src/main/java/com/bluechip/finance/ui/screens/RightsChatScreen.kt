package com.bluechip.finance.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.ui.components.SectionHeader
import com.bluechip.finance.ui.theme.*

private data class RightsQA(
    val id: String,
    val question: String,
    val answer: String,
    val tags: List<String>,
    val hasHotline: Boolean = false
)

private val ALL_QA = listOf(
    RightsQA(
        "kidem", "Kıdem tazminatı ne zaman hak kazanırım?",
        "Aynı işyerinde kesintisiz 1 yıl çalışmanız gerekir.\n\n" +
        "Kıdem tazminatı alabileceğiniz durumlar:\n" +
        "• İşveren tarafından haksız fesih\n" +
        "• Emeklilik için ayrılma\n" +
        "• Askerlik nedeniyle ayrılma\n" +
        "• Kadın çalışanlar: evlilikten 1 yıl içinde\n" +
        "• Sağlık sorunları (iş kaynaklı)\n\n" +
        "Hesaplama: Her tam yıl için 30 günlük brüt ücret.\n" +
        "2024 tavan: ~35.058₺/yıl (yılda 2 güncellenir).",
        listOf("kıdem", "tazminat", "1 yıl")
    ),
    RightsQA(
        "ihbar", "İhbar süresi nedir?",
        "Çalışma süresine göre minimum ihbar süresi:\n\n" +
        "• 0–6 ay → 2 hafta\n" +
        "• 6–18 ay → 4 hafta\n" +
        "• 18–36 ay → 6 hafta\n" +
        "• 36 ay+ → 8 hafta\n\n" +
        "İşveren ihbar süresi yerine peşin ödeme yapabilir.\n" +
        "İhbar tazminatı = ihbar süresi (gün) × günlük brüt ücret.",
        listOf("ihbar", "süre", "bildirim", "tazminat")
    ),
    RightsQA(
        "yillik_izin", "Yıllık izin hakkım ne kadar?",
        "İş Kanunu'na göre minimum yıllık ücretli izin:\n\n" +
        "• 1–5 yıl → 14 gün\n" +
        "• 5–15 yıl → 20 gün\n" +
        "• 15 yıl+ → 26 gün\n\n" +
        "Özel durumlar:\n" +
        "• 18 yaş altı ve 50 yaş üstü → minimum 20 gün\n" +
        "• Toplu sözleşme veya işveren daha fazlasını verebilir\n\n" +
        "Kullandırılmayan izinler iş bitişinde nakde çevrilir.",
        listOf("izin", "yıllık", "ücretli izin")
    ),
    RightsQA(
        "fazla_mesai", "Fazla mesai ücretim ödenmedi",
        "Haftada 45 saati aşan çalışmalar fazla mesai sayılır.\n\n" +
        "Ödeme zorunluluğu:\n" +
        "• Normal mesai: %50 zam\n" +
        "• Hafta sonu/tatil: %100 zam\n\n" +
        "Ödenmezse adımlar:\n" +
        "1. İşverene yazılı ihtarname gönderin\n" +
        "2. ALO 170'i arayın (Çalışma Bakanlığı)\n" +
        "3. İş Mahkemesi'ne başvurun (3 yıllık zamanaşımı)\n\n" +
        "Delil: bordro, mesai çizelgesi, banka ekstresi.",
        listOf("mesai", "fazla mesai", "ücret", "ödeme"),
        hasHotline = true
    ),
    RightsQA(
        "sgk_eksik", "SGK primim eksik yatırılıyor",
        "İşveren her çalışma günü için SGK bildirimi yapmak zorundadır. Eksik bildirim suçtur.\n\n" +
        "Kontrol:\n" +
        "1. e-Devlet → \"SGK Hizmet Dökümü\" bölümü\n" +
        "2. Eksik günler varsa SGK'ya yazılı başvurun\n" +
        "3. Çalışma Bakanlığı'na şikayet: ALO 170\n\n" +
        "Delil olarak saklayın: banka hesap dökümleri, yazışmalar, tanık isimleri.",
        listOf("sgk", "prim", "sigorta", "eksik"),
        hasHotline = true
    ),
    RightsQA(
        "isten_cikarma", "Haksız yere işten çıkarıldım",
        "30+ çalışanlı işyerlerinde geçerli neden olmadan fesih geçersizdir.\n\n" +
        "Haklarınız:\n" +
        "• Kıdem tazminatı (1 yıl+ ise)\n" +
        "• İhbar tazminatı (süreye uyulmadıysa)\n" +
        "• İşe iade davası: fesihten 30 iş günü içinde arabulucuya başvurun\n\n" +
        "Süreç:\n" +
        "1. Arabuluculuk (zorunlu ön adım)\n" +
        "2. Anlaşma olmazsa → İş Mahkemesi\n\n" +
        "Arabuluculuk başvurusu için son gün: fesih bildiriminden 30 İŞ günü.",
        listOf("işten çıkarma", "fesih", "kovulma", "haksız"),
        hasHotline = true
    ),
    RightsQA(
        "istifa", "İstifa edeceksem haklarım ne?",
        "İstifa durumunda genel kural:\n" +
        "✗ Kıdem tazminatı ALAMAZSINIZ\n" +
        "✓ İhbar süresi beklemeniz gerekir (aksi halde ödeme)\n\n" +
        "İstifada kıdem alabileceğiniz istisnalar:\n" +
        "• Emeklilik için istifa\n" +
        "• Askerlik için istifa\n" +
        "• Evlilik için istifa (kadın, 1 yıl içinde)\n" +
        "• Sağlık sorunları (iş nedeniyle)\n" +
        "• İşverenin koşulları kötüleştirmesi (ispat gerekir)",
        listOf("istifa", "çıkış", "ayrılma")
    ),
    RightsQA(
        "mobbing", "İşyerinde mobbinge veya baskıya uğruyorum",
        "Psikolojik taciz (mobbing) İş Kanunu'nda suçtur.\n\n" +
        "Adımlar:\n" +
        "1. Her şeyi belgeleyin: e-posta, mesaj, tarih-saat notu\n" +
        "2. İK'ya yazılı şikayette bulunun\n" +
        "3. ALO 170 ile Çalışma Bakanlığı'na bildirin\n" +
        "4. Devam ederse haklı nedenle fesih → kıdem tazminatı hakkı\n" +
        "5. Manevi tazminat davası açabilirsiniz\n\n" +
        "Çalışma ortamının çekilmez hale getirilmesi = haklı fesih sebebidir.",
        listOf("mobbing", "baskı", "taciz", "psikolojik"),
        hasHotline = true
    ),
    RightsQA(
        "is_kazasi", "İş kazası geçirdim",
        "Acil adımlar:\n" +
        "1. Önce tıbbi yardım alın\n" +
        "2. İşverene derhal bildirin (3 iş günü içinde SGK'ya bildirme zorunluluğu)\n" +
        "3. Doktor raporu + SGK iş kazası formu\n\n" +
        "Haklar:\n" +
        "• Geçici iş göremezlik ödeneği: günlük kazancın 2/3'ü\n" +
        "• Sürekli iş göremezlik varsa: derecesine göre aylık\n" +
        "• İşveren kusurlu ise: maddi + manevi tazminat davası\n\n" +
        "Kaza SGK'ya bildirilmezse ALO 182'ye bildirebilirsiniz.",
        listOf("iş kazası", "kaza", "yaralanma"),
        hasHotline = true
    ),
    RightsQA(
        "asgari_ucret", "Asgari ücretin altında maaş alıyorum",
        "2024 yılı net asgari ücret ~17.002₺ (brüt ~20.002₺). Yılda 2 güncellenir.\n\n" +
        "Asgari ücret altında ödeme:\n" +
        "• SGK idari para cezası + adli yaptırım\n" +
        "• Şikayet kanalları:\n" +
        "  – ALO 170 (Çalışma Bakanlığı)\n" +
        "  – Bölge Çalışma Müdürlüğü\n" +
        "  – Cumhuriyet Savcılığı\n\n" +
        "Delil: banka ekstresi, yazılı maaş belgesi.",
        listOf("asgari ücret", "düşük maaş", "ücret"),
        hasHotline = true
    ),
    RightsQA(
        "ucretsiz_izin", "Ücretsiz izne zorlandım",
        "İşveren çalışanı zorla ücretsiz izne gönderemez. Bu tek taraflı koşul değişikliğidir.\n\n" +
        "Haklarınız:\n" +
        "• Yazılı teklifi kabul etmek zorunda DEĞİLSİNİZ\n" +
        "• Reddederseniz ve işveren feshederse: kıdem + ihbar tazminatı\n" +
        "• Kabul edip imzalarsanız hakkınızdan büyük ölçüde vazgeçmiş sayılırsınız\n\n" +
        "Tavsiye: İmzalamadan önce hukuki danışmanlık alın.",
        listOf("ücretsiz izin", "zorlama", "izin")
    ),
    RightsQA(
        "izin_kullandirmama", "İşveren yıllık izin kullandırmıyor",
        "İşveren yıllık izni belirli dönemlerde kullandırmak zorundadır.\n\n" +
        "Haklarınız:\n" +
        "• Kullandırılmayan izin birikir, iş bitişinde nakde çevrilir\n" +
        "• Ödeme = birikmiş izin günü × günlük ücret\n\n" +
        "Şikayet:\n" +
        "• Bölge Çalışma Müdürlüğü\n" +
        "• ALO 170",
        listOf("izin", "kullandırmama", "yıllık"),
        hasHotline = true
    )
)

private val CHIPS = listOf(
    "Kıdem" to "kidem",
    "İhbar" to "ihbar",
    "Yıllık İzin" to "yillik_izin",
    "Fazla Mesai" to "fazla_mesai",
    "SGK" to "sgk_eksik",
    "İşten Çıkarma" to "isten_cikarma",
    "İstifa" to "istifa",
    "Mobbing" to "mobbing",
    "İş Kazası" to "is_kazasi",
    "Asgari Ücret" to "asgari_ucret",
    "Ücretsiz İzin" to "ucretsiz_izin",
    "İzin Hakkı" to "izin_kullandirmama"
)

@Composable
fun RightsChatScreen() {
    val context = LocalContext.current
    val colors = LocalAppColors.current
    var query by remember { mutableStateOf("") }
    var expandedIds by remember { mutableStateOf(setOf<String>()) }

    val filtered = remember(query) {
        if (query.isBlank()) ALL_QA
        else {
            val q = query.lowercase()
            ALL_QA.filter { qa ->
                qa.question.lowercase().contains(q) ||
                qa.answer.lowercase().contains(q) ||
                qa.tags.any { it.contains(q) }
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        SectionHeader("HAKLARIM CHATBOT", Icons.Default.Gavel)

        // Disclaimer
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp),
            colors = CardDefaults.cardColors(
                containerColor = colors.warning.copy(alpha = 0.10f))
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                verticalAlignment = Alignment.Top,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(Icons.Default.Info, null, tint = colors.warning,
                    modifier = Modifier.size(18.dp))
                Text(
                    "Bilgilendirme amaçlıdır, hukuki danışmanlık değildir. " +
                    "Hukuki süreçler için avukat veya arabulucuya danışın.",
                    fontSize = 11.sp,
                    color = colors.textPrimary,
                    lineHeight = 16.sp
                )
            }
        }

        // Quick topic chips
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            CHIPS.forEach { (label, id) ->
                val isActive = expandedIds.contains(id)
                Box(
                    modifier = Modifier
                        .background(
                            if (isActive) PurplePrimary else PurplePrimary.copy(alpha = 0.10f),
                            RoundedCornerShape(20.dp)
                        )
                        .clickable {
                            expandedIds = if (isActive) expandedIds - id else expandedIds + id
                            query = ""
                        }
                        .padding(horizontal = 14.dp, vertical = 8.dp)
                ) {
                    Text(
                        label,
                        fontSize = 12.sp,
                        color = if (isActive) Color.White else PurplePrimary,
                        fontWeight = if (isActive) FontWeight.SemiBold else FontWeight.Normal
                    )
                }
            }
        }

        // Search field
        OutlinedTextField(
            value = query,
            onValueChange = { query = it; if (it.isNotBlank()) expandedIds = emptySet() },
            label = { Text("Hakkınızı arayın...", fontSize = 13.sp) },
            leadingIcon = { Icon(Icons.Default.Search, null, tint = PurplePrimary) },
            trailingIcon = {
                if (query.isNotEmpty()) {
                    IconButton(onClick = { query = "" }) {
                        Icon(Icons.Default.Clear, null, tint = colors.textSecondary)
                    }
                }
            },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            shape = RoundedCornerShape(14.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = PurplePrimary,
                unfocusedBorderColor = PurplePrimary.copy(alpha = 0.30f),
                focusedContainerColor = colors.cardBg,
                unfocusedContainerColor = colors.cardBg,
                focusedTextColor = colors.textPrimary,
                unfocusedTextColor = colors.textPrimary,
                focusedLabelColor = PurplePrimary,
                unfocusedLabelColor = colors.textSecondary
            )
        )

        // Results count when searching
        if (query.isNotBlank()) {
            Text(
                "${filtered.size} sonuç bulundu",
                fontSize = 12.sp,
                color = colors.textSecondary
            )
        }

        // Q&A cards
        val displayItems = if (query.isNotBlank()) filtered
        else if (expandedIds.isNotEmpty()) ALL_QA.filter { it.id in expandedIds }
        else ALL_QA

        displayItems.forEach { qa ->
            val isExpanded = query.isNotBlank() || qa.id in expandedIds
            RightsCard(
                qa = qa,
                isExpanded = isExpanded,
                onToggle = {
                    expandedIds = if (qa.id in expandedIds) expandedIds - qa.id
                    else expandedIds + qa.id
                },
                onCallHotline = { number ->
                    context.startActivity(
                        Intent(Intent.ACTION_DIAL, Uri.parse("tel:$number"))
                    )
                }
            )
        }

        // Hotline section
        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
        Text("Önemli Hat Numaraları",
            fontWeight = FontWeight.Bold, fontSize = 15.sp, color = colors.textPrimary)

        listOf(
            Triple(Icons.Default.Phone, "ALO 170 — Çalışma ve Sosyal Güvenlik", "170"),
            Triple(Icons.Default.HealthAndSafety, "ALO 182 — SGK Hizmet Hattı", "182"),
            Triple(Icons.Default.Work, "ALO 150 — Türkiye İş Kurumu", "150")
        ).forEach { (icon, label, number) ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable {
                        context.startActivity(
                            Intent(Intent.ACTION_DIAL, Uri.parse("tel:$number"))
                        )
                    },
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = colors.cardGray)
            ) {
                Row(
                    modifier = Modifier.padding(14.dp).fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(40.dp)
                            .background(PurplePrimary.copy(alpha = 0.12f), RoundedCornerShape(10.dp)),
                        contentAlignment = Alignment.Center
                    ) { Icon(icon, null, tint = PurplePrimary, modifier = Modifier.size(20.dp)) }
                    Column(modifier = Modifier.weight(1f)) {
                        Text(label, fontSize = 13.sp, fontWeight = FontWeight.Medium,
                            color = colors.textPrimary)
                        Text(number, fontSize = 12.sp, color = PurplePrimary,
                            fontWeight = FontWeight.Bold)
                    }
                    Icon(Icons.Default.ChevronRight, null,
                        tint = colors.textSecondary, modifier = Modifier.size(18.dp))
                }
            }
        }

        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun RightsCard(
    qa: RightsQA,
    isExpanded: Boolean,
    onToggle: () -> Unit,
    onCallHotline: (String) -> Unit
) {
    val colors = LocalAppColors.current
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = colors.cardBg),
        elevation = CardDefaults.cardElevation(2.dp)
    ) {
        Column {
            // Question row (always visible)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onToggle() }
                    .padding(14.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(36.dp)
                        .background(PurplePrimary.copy(alpha = 0.10f), RoundedCornerShape(10.dp)),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Default.QuestionAnswer, null,
                        tint = PurplePrimary, modifier = Modifier.size(18.dp))
                }
                Text(
                    qa.question,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 14.sp,
                    color = colors.textPrimary,
                    modifier = Modifier.weight(1f)
                )
                Icon(
                    if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    null,
                    tint = colors.textSecondary,
                    modifier = Modifier.size(20.dp)
                )
            }

            // Answer (expandable)
            AnimatedVisibility(
                visible = isExpanded,
                enter = expandVertically() + fadeIn(),
                exit = shrinkVertically() + fadeOut()
            ) {
                Column(modifier = Modifier.padding(start = 14.dp, end = 14.dp, bottom = 14.dp)) {
                    HorizontalDivider(modifier = Modifier.padding(bottom = 10.dp))
                    Text(
                        qa.answer,
                        fontSize = 13.sp,
                        color = colors.textPrimary,
                        lineHeight = 20.sp
                    )
                    if (qa.hasHotline) {
                        Spacer(Modifier.height(10.dp))
                        OutlinedButton(
                            onClick = { onCallHotline("170") },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(10.dp),
                            border = androidx.compose.foundation.BorderStroke(
                                1.dp, colors.info.copy(alpha = 0.6f))
                        ) {
                            Icon(Icons.Default.Phone, null,
                                modifier = Modifier.size(16.dp), tint = colors.info)
                            Spacer(Modifier.width(6.dp))
                            Text("ALO 170 — Çalışma Bakanlığı",
                                color = colors.info, fontSize = 13.sp)
                        }
                    }
                }
            }
        }
    }
}
