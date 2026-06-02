package com.bluechip.finance.ui.screens

import android.content.Intent
import android.net.Uri
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.ui.components.SectionHeader
import com.bluechip.finance.ui.theme.LocalAppColors

data class RightItem(
    val id: String,
    val title: String,
    val description: String,
    val detail: String,
    val lawRef: String,
    val actionSteps: List<String>,
    val severity: Severity
)

enum class Severity { KESIN, MUHTEMEL, BILGI }

@Composable
fun RightsScreen() {
    val context = LocalContext.current
    val colors  = LocalAppColors.current
    var expandedId by remember { mutableStateOf<String?>(null) }
    var showWarningDialog by remember { mutableStateOf(false) }

    val rights = listOf(
        RightItem(
            id = "maas",
            title = "Maaşım ödenmedi veya geç ödendi",
            description = "İşveren maaşı zamanında ödemezse haklı fesih hakkı doğar.",
            detail = "Maaş ödeme gününden itibaren 20 gün içinde ödenmezse 21. günden itibaren haklı fesih hakkı doğar. Fesihten önce işverene noterden ihtarname çekilmesi ispat açısından kritik önem taşır.",
            lawRef = "4857 Md.24/II-e, Md.34",
            actionSteps = listOf(
                "Maaş yatmadıysa önce yazılı olarak işverene bildirin",
                "20 gün bekleyin, hâlâ ödenmezse noterden ihtarname çekin",
                "Banka dekontları ve mesaj kayıtlarını saklayın",
                "ALO 170'i arayın veya e-Devlet üzerinden SGK'ya şikayet edin",
                "Arabulucuya başvurun (dava öncesi zorunlu)"
            ),
            severity = Severity.KESIN
        ),
        RightItem(
            id = "sgk",
            title = "SGK primim eksik veya hiç yatırılmıyor",
            description = "Eksik veya sigortasız çalıştırılmak haklı fesih sebebidir.",
            detail = "e-Devlet'ten SGK hizmet dökümünüzü kontrol edin. Gerçek ücretinizden daha düşük prim bildirilmesi (elden para alma) hem haklı fesih sebebi hem de suçtur. SGK'ya şikayet ettiğinizde 5 yıl geriye dönük prim farkı tahsil edilebilir.",
            lawRef = "4857 Md.24/II-e, SGK 5510",
            actionSteps = listOf(
                "e-Devlet > SGK Hizmet Dökümü'nü kontrol edin",
                "Eksik prim varsa ALO 170 veya e-Devlet'ten şikayet edin",
                "Elden aldığınız paraları belgeleyin (WhatsApp, tanık vb.)",
                "Noterden ihtarname ile haklı fesih yapabilirsiniz"
            ),
            severity = Severity.KESIN
        ),
        RightItem(
            id = "mesai",
            title = "Mesai ücretim ödenmiyor",
            description = "Haftalık 45 saati aşan her çalışma zamlı ödenmek zorundadır.",
            detail = "Yıllık 270 saat mesai sınırı vardır. Bu sınır aşılırsa tüm fazla mesai ayrıca ödenmek zorundadır. İş sözleşmesine 'fazla mesai ücrete dahildir' yazılması Yargıtay kararlarına göre sınırsız geçerli değildir. Mesai yaptığınızı tanık, mesaj veya kamera kayıtlarıyla ispat edebilirsiniz.",
            lawRef = "4857 Md.41, Md.24/II-e",
            actionSteps = listOf(
                "Çalışma saatlerinizi kayıt altına alın (ekran görüntüsü, mesaj vb.)",
                "İşverene yazılı olarak ödeme talep edin",
                "Yanıt gelmezse noterden ihtarname çekin",
                "ALO 170'i arayın",
                "Arabulucuya başvurun"
            ),
            severity = Severity.KESIN
        ),
        RightItem(
            id = "yanhak",
            title = "Yol/yemek/prim gibi yan haklar kaldırıldı",
            description = "Yerleşmiş yan haklar işçinin yazılı onayı olmadan kaldırılamaz.",
            detail = "Yargıtay 9. HD kararına göre yol, yemek, devamsızlık primi gibi süregelen ödemeler 'kazanılmış hak' sayılır. İşveren bu hakları kaldırmak için işçiye yazılı bildirmek ve 6 iş günü içinde yazılı onay almak zorundadır. Onay vermezseniz değişiklik sizi bağlamaz ve haklı fesih hakkı doğar.",
            lawRef = "4857 Md.22, Md.24/II-f, Yargıtay 9.HD 2016/5644E",
            actionSteps = listOf(
                "Değişikliği 6 iş günü içinde yazılı olarak reddedin",
                "Reddinizi işverene iadeli taahhütlü mektupla gönderin",
                "Ödeme yapılmazsa noterden ihtarname ile haklı fesih yapın",
                "Önceki ödemelerin banka dekontlarını saklayın"
            ),
            severity = Severity.KESIN
        ),
        RightItem(
            id = "gorev",
            title = "Görevim/pozisyonum düşürüldü veya değiştirildi",
            description = "Rızanız olmadan görev, unvan veya maaş değişikliği yapılamaz.",
            detail = "Nitelikli bir pozisyondan daha alt göreye atanmak, unvan düşürülmesi veya çalışma koşullarının ağırlaştırılması esaslı değişiklik sayılır. İşveren bunu yazılı bildirmek zorundadır. 6 iş günü içinde yazılı onay vermezseniz değişiklik geçersizdir.",
            lawRef = "4857 Md.22, Md.24/II",
            actionSteps = listOf(
                "Değişikliği 6 iş günü içinde yazılı olarak reddedin",
                "Eski görev tanımınızı belgeleyin (sözleşme, mail, zimmet)",
                "Reddi işverene iadeli taahhütlü mektupla bildirin",
                "Gerekirse noterden haklı fesih ihtarnamesi çekin"
            ),
            severity = Severity.KESIN
        ),
        RightItem(
            id = "sehir",
            title = "Rızam olmadan başka şehre/şubeye atandım",
            description = "İşçinin onayı olmadan il değişikliği esaslı değişikliktir.",
            detail = "Sözleşmede nakil hükmü yoksa veya uygulamada hiç nakil yapılmamışsa, rızanız olmadan başka ile gönderilmek esaslı değişikliktir. 6 iş günü içinde yazılı reddinizi bildirirseniz değişiklik geçersizdir.",
            lawRef = "4857 Md.22",
            actionSteps = listOf(
                "Sözleşmenizde nakil hükmü olup olmadığını kontrol edin",
                "6 iş günü içinde yazılı olarak reddedin",
                "Reddi iadeli taahhütlü mektupla gönderin",
                "Gerekirse haklı fesih yapabilirsiniz"
            ),
            severity = Severity.KESIN
        ),
        RightItem(
            id = "hakaret",
            title = "Hakaret, tehdit veya psikolojik baskıya maruz kaldım",
            description = "İşveren veya amirinizin hakareti haklı fesih sebebidir.",
            detail = "İşverenin veya işveren vekilinin (müdür, amir vb.) size ya da ailenize hakaret etmesi, tehdit etmesi, sürekli küçük düşürmesi (mobbing) haklı fesih sebebidir. Başka bir işçi hakaretinde ise önce işverene bildirmeniz, işveren önlem almazsa fesih hakkı doğar. Manevi tazminat da talep edilebilir.",
            lawRef = "4857 Md.24/II-b, Md.24/II-c",
            actionSteps = listOf(
                "Olayları tarihleriyle not alın, varsa kayıt yapın",
                "Tanıkları not alın",
                "İşverene yazılı şikayet edin (hakaret başka işçidense)",
                "Önlem alınmazsa veya işveren yaptıysa noterden haklı fesih",
                "Manevi tazminat davası açabilirsiniz"
            ),
            severity = Severity.KESIN
        ),
        RightItem(
            id = "cinsel",
            title = "Cinsel tacize uğradım",
            description = "İşyerinde cinsel taciz ve işverenin önlem almaması haklı fesih sebebidir.",
            detail = "İşveren tarafından veya başka bir çalışan tarafından cinsel tacize uğradıysanız ve durumu işverene bildirmenize rağmen önlem alınmadıysa haklı fesih hakkı doğar. Ayrıca savcılığa suç duyurusunda bulunabilirsiniz.",
            lawRef = "4857 Md.24/II-b, Md.24/II-d",
            actionSteps = listOf(
                "Güvendiğiniz birine veya İK'ya bildirin (yazılı)",
                "Önlem alınmazsa noterden haklı fesih ihtarnamesi çekin",
                "Savcılığa suç duyurusunda bulunabilirsiniz",
                "CİMER veya ALO 170'e şikayet edebilirsiniz"
            ),
            severity = Severity.KESIN
        ),
        RightItem(
            id = "saglik",
            title = "İş sağlığı ve güvenliği önlemleri alınmıyor",
            description = "Sağlığınızı tehdit eden ortamda çalışmak zorunda değilsiniz.",
            detail = "İşin niteliğinden kaynaklanan ciddi sağlık riski varsa (zehirli madde, yükseklik, ağır makine vb.) ve gerekli önlemler alınmıyorsa haklı fesih hakkı doğar. Tıbbi rapor, işyeri kayıtları veya bilirkişiyle ispat edilebilir.",
            lawRef = "4857 Md.24/I-a, 6331 İSG Kanunu",
            actionSteps = listOf(
                "İşverene yazılı olarak tehlikeyi bildirin",
                "Doktor raporu alın",
                "Çalışma Bakanlığı iş müfettişine şikayet edin (ALO 170)",
                "Önlem alınmazsa haklı fesih yapabilirsiniz"
            ),
            severity = Severity.KESIN
        ),
        RightItem(
            id = "yaniltma",
            title = "İşe girerken söylenenler gerçek çıkmadı",
            description = "İşveren sizi yanıltarak işe aldıysa haklı fesih hakkı doğabilir.",
            detail = "İşe girişte vaat edilen maaş, pozisyon, yan haklar veya çalışma koşulları gerçeği yansıtmıyorsa bu yanıltma haklı fesih sebebi olabilir. Öğrendiğiniz günden itibaren 6 iş günü içinde feshetmeniz gerekir.",
            lawRef = "4857 Md.24/II-a",
            actionSteps = listOf(
                "Vaat edilenleri belgeleyin (mail, mesaj, ilan)",
                "6 iş günü içinde haklı fesih yapın",
                "Noterden ihtarname gönderin"
            ),
            severity = Severity.MUHTEMEL
        ),
        RightItem(
            id = "rapor",
            title = "Raporlu olduğumda devamsız sayıldım",
            description = "Raporlu dönem yasal bir haktır, devamsızlık sayılamaz.",
            detail = "SGK'dan alınan istirahat raporu (doktor raporu) yasal bir haktır. Bu süreyi devamsızlık sayıp devamsızlık primini kesmek hukuka aykırıdır. Ancak işe dönüşte raporu işverene bildirmemeniz sorun yaratabilir.",
            lawRef = "4857 Md.24/II-e, SGK 5510",
            actionSteps = listOf(
                "Raporunuzu işverene zamanında bildirin (SMS/mail ile belgeleyin)",
                "Yine de kesinti yapılırsa yazılı itiraz edin",
                "Yanıt gelmezse ALO 170'e şikayet edin"
            ),
            severity = Severity.MUHTEMEL
        ),
        RightItem(
            id = "noterihtar",
            title = "Haklı fesih nasıl yapılır?",
            description = "Haklı fesihte doğru adımlar tazminatınızı güvence altına alır.",
            detail = "Haklı fesih yazılı yapılmalıdır. En güvenli yol noterden ihtarname çekmektir. İhtarnamede fesih gerekçesi (hangi madde, ne zaman olduğu) açıkça yazılmalıdır. Fesih hakkı, olayı öğrendiğiniz günden itibaren 6 iş günü içinde kullanılmalıdır (ahlak kurallarına aykırılıkta). Haklı fesihte kıdem tazminatı alınır, ihbar tazminatı alınamaz.",
            lawRef = "4857 Md.24, Md.26",
            actionSteps = listOf(
                "Olayı öğrendiğiniz günden itibaren 6 iş günü içinde hareket edin",
                "Notere gidin, gerekçeli ihtarname çekin",
                "İhtarnamede ilgili maddeyi (Md.24/II-e gibi) belirtin",
                "Kıdem tazminatı + diğer alacaklarınızı talep edin",
                "İşveren ödemezse arabulucuya başvurun"
            ),
            severity = Severity.BILGI
        )
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        SectionHeader("HAKKIMI ARIYORUM", Icons.Default.Gavel)

        // Uyari banner
        Card(
            shape = RoundedCornerShape(12.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF3E0))
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                verticalAlignment = Alignment.Top
            ) {
                Icon(Icons.Default.Warning, null,
                    tint = Color(0xFFE65100),
                    modifier = Modifier.size(20.dp).padding(top = 2.dp))
                Spacer(Modifier.width(8.dp))
                Text(
                    "Bu bilgiler genel rehber niteliğindedir. Kesin karar için bir is hukuku avukatina danismaniz onemle tavsiye edilir.",
                    fontSize = 12.sp,
                    color = Color(0xFF5D4037),
                    lineHeight = 17.sp
                )
            }
        }

        // ALO 170 hizli erisim
        Card(
            shape = RoundedCornerShape(12.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xFFE3F2FD)),
            modifier = Modifier.clickable {
                context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:170")))
            }
        ) {
            Row(
                modifier = Modifier.padding(12.dp).fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Default.Phone, null,
                    tint = Color(0xFF1565C0),
                    modifier = Modifier.size(24.dp))
                Spacer(Modifier.width(10.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text("ALO 170 - Calisma Bakanligi",
                        fontWeight = FontWeight.Bold, fontSize = 13.sp,
                        color = Color(0xFF1565C0))
                    Text("Ucretsiz danisma hatti - 7/24",
                        fontSize = 11.sp, color = Color(0xFF1565C0))
                }
                Icon(Icons.Default.ArrowForward, null,
                    tint = Color(0xFF1565C0),
                    modifier = Modifier.size(16.dp))
            }
        }

        // Hak kartlari
        rights.forEach { right ->
            val isExpanded = expandedId == right.id
            val bgColor = when (right.severity) {
                Severity.KESIN     -> colors.cardBg
                Severity.MUHTEMEL  -> colors.cardBg
                Severity.BILGI     -> colors.cardGray
            }
            val badgeColor = when (right.severity) {
                Severity.KESIN    -> Color(0xFFC62828)
                Severity.MUHTEMEL -> Color(0xFFE65100)
                Severity.BILGI    -> Color(0xFF1565C0)
            }
            val badgeText = when (right.severity) {
                Severity.KESIN    -> "KESN HAKLI FESH"
                Severity.MUHTEMEL -> "MUHTEMEL"
                Severity.BILGI    -> "BILGI"
            }

            Card(
                shape = RoundedCornerShape(12.dp),
                elevation = CardDefaults.cardElevation(2.dp),
                colors = CardDefaults.cardColors(containerColor = bgColor),
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable {
                        expandedId = if (isExpanded) null else right.id
                    }
            ) {
                Column(modifier = Modifier.padding(14.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    modifier = Modifier
                                        .background(badgeColor, RoundedCornerShape(4.dp))
                                        .padding(horizontal = 6.dp, vertical = 2.dp)
                                ) {
                                    Text(badgeText, fontSize = 9.sp,
                                        color = Color.White, fontWeight = FontWeight.Bold)
                                }
                                Spacer(Modifier.width(6.dp))
                                Text(right.lawRef, fontSize = 10.sp,
                                    color = colors.textSecondary)
                            }
                            Spacer(Modifier.height(4.dp))
                            Text(right.title,
                                fontWeight = FontWeight.Bold, fontSize = 14.sp,
                                color = colors.textPrimary)
                            Text(right.description,
                                fontSize = 12.sp, color = colors.textSecondary,
                                lineHeight = 16.sp)
                        }
                        Icon(
                            if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                            null, tint = colors.textSecondary,
                            modifier = Modifier.size(20.dp)
                        )
                    }

                    if (isExpanded) {
                        Spacer(Modifier.height(10.dp))
                        HorizontalDivider()
                        Spacer(Modifier.height(10.dp))

                        Text(right.detail,
                            fontSize = 13.sp, color = colors.textPrimary,
                            lineHeight = 19.sp)

                        Spacer(Modifier.height(10.dp))
                        Text("Ne yapmaliyim?",
                            fontWeight = FontWeight.Bold, fontSize = 13.sp,
                            color = colors.textPrimary)
                        Spacer(Modifier.height(6.dp))

                        right.actionSteps.forEachIndexed { i, step ->
                            Row(
                                modifier = Modifier.padding(vertical = 3.dp),
                                verticalAlignment = Alignment.Top
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(20.dp)
                                        .background(badgeColor, RoundedCornerShape(10.dp)),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text("${i+1}", fontSize = 10.sp,
                                        color = Color.White, fontWeight = FontWeight.Bold)
                                }
                                Spacer(Modifier.width(8.dp))
                                Text(step, fontSize = 12.sp,
                                    color = colors.textPrimary, lineHeight = 17.sp,
                                    modifier = Modifier.weight(1f))
                            }
                        }
                    }
                }
            }
        }

        // ── Dilekçe Şablonları ──────────────────────────────────
        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
        Spacer(Modifier.height(4.dp))

        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Description, null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(6.dp))
            Text("Dilekçe Şablonları",
                fontWeight = FontWeight.Bold, fontSize = 15.sp,
                color = colors.textPrimary)
        }
        Spacer(Modifier.height(4.dp))
        Text(
            "Şablonu indirin, mavi alanları doldurun. Notere göndermeden önce bir avukata danışmanız önerilir.",
            fontSize = 11.sp, color = colors.textSecondary, lineHeight = 15.sp
        )
        Spacer(Modifier.height(6.dp))

        com.bluechip.finance.ui.components.PdfDownloadButton(
            label = "📄 Haklı Fesih İhtarnamesi",
            assetFileName = "1_hakli_fesih_ihtarnamesi.pdf"
        )
        com.bluechip.finance.ui.components.PdfDownloadButton(
            label = "📄 SGK Şikayet Dilekçesi",
            assetFileName = "2_sgk_sikayet_dilekce.pdf"
        )
        com.bluechip.finance.ui.components.PdfDownloadButton(
            label = "📄 Fazla Mesai Talep Yazısı",
            assetFileName = "3_fazla_mesai_talep_yazisi.pdf"
        )

        Spacer(Modifier.height(8.dp))
    }
}
