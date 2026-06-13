package com.bluechip.finance.util

import android.content.Context
import com.bluechip.finance.data.BackupManager
import com.bluechip.finance.data.KnownCoins
import com.bluechip.finance.data.SpecialDay
import com.bluechip.finance.data.SpecialDayManager
import com.bluechip.finance.data.KnownCurrencies
import com.bluechip.finance.data.KnownMetals
import com.bluechip.finance.data.OvertimeManager
import com.bluechip.finance.data.OvertimeRecord
import com.bluechip.finance.data.OvertimeTrackType
import com.bluechip.finance.data.Payment
import com.bluechip.finance.data.PaymentCategory
import com.bluechip.finance.data.PaymentManager
import com.bluechip.finance.data.ProfileManager
import com.bluechip.finance.data.SavingsCategory
import com.bluechip.finance.data.SavingsManager
import com.bluechip.finance.data.SavingsRecord
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Locale

data class ChatMessage(val role: String, val content: String)

object DeepSeekClient {

    private const val API_URL = "https://api.deepseek.com/chat/completions"
    private const val MODEL   = "deepseek-chat"

    // ── Sistem promptu: yapılandırılmış + otomatik ham veri ─────────────
    fun buildSystemPrompt(context: Context): String {
        val profile       = ProfileManager(context).load()
        val payments      = PaymentManager.getPayments(context).filter { it.isActive }
        val totalPayments = payments.sumOf { it.amount }
        val overtimeAll   = OvertimeManager.loadAll(context)
        val overtimeMonth = OvertimeManager.thisMonthRecords(context)
        val sm            = SavingsManager(context)
        val savings       = sm.loadAll()
        val priceCache    = sm.loadPriceCache()

        val specialDays  = SpecialDayManager.getAll(context)
        val upcoming     = SpecialDayManager.getUpcoming(context, withinDays = 60)

        return buildString {
            appendLine("Sen 'Baretim' adli Turkce konusan bir finansal asistan ve islem yardimcisin.")
            appendLine("Kullanicinin tum uygulama verisine tam erisimin var.")
            appendLine("Kullanici bir islem yapmani isterse direkt araci cagir, onay isteme.")
            appendLine("Her zaman Turkce yaz, kisa ve net cevaplar ver.")
            appendLine()

            // ── UYGULAMA EKRANLARI VE OZELLIKLER ──────────────────────
            appendLine("=== UYGULAMANIN TUM OZELLIKLERI VE EKRANLARI ===")
            appendLine("Kullanici bir islem yapmak istediginde asagidaki ekran/ozellik rehberini kullan.")
            appendLine("AI yapabilecekleri: dogrudan arac cagir. Kullanicinin elle gitmesi gerekenler: yonlendir.")
            appendLine()
            appendLine("[ Ana Ekran ]")
            appendLine("  Profil ozeti, maaş bilgisi, maşa kac gun kaldi, yaklaşan odemeler, yan gelirler, mutluluk skoru.")
            appendLine("  AI yapabilir: profil guncelleme (update_profile)")
            appendLine()
            appendLine("[ Mesai Hesaplama — Alt nav: Mesai ]")
            appendLine("  Tek seferlik mesai ucreti hesapla: brut maas gir, saat gir, tur sec (%%50/%%100 vb).")
            appendLine("  AI yapabilir: hesaplamayı anlat, mesai kaydını ekle (add_overtime)")
            appendLine()
            appendLine("[ Mesai Takip — Araçlar menusunden ]")
            appendLine("  Yapılan mesaileri tarih/saat/tur ile kaydet, grafik goster, aylik toplam.")
            appendLine("  AI yapabilir: add_overtime, delete_overtime (son kaydi sil vb.)")
            appendLine()
            appendLine("[ Kidem & Ihbar Tazminati — Araçlar: Kıdem & İhbar ]")
            appendLine("  Calişma süresi, maas, işten ayrılma nednei girerek tazminat hesapla.")
            appendLine("  Kullanici gitmeli: tazminat hesaplamak icin manuel giriş gerekli.")
            appendLine()
            appendLine("[ Vergi & Bordro — Araçlar: Vergi & Bordro ]")
            appendLine("  Brut maaştan net hesapla, SGK, gelir vergisi dilimleri.")
            appendLine("  AI yapabilir: hesaplama mantığını anlat.")
            appendLine()
            appendLine("[ Yıllık İzin — Araçlar: Yıllık İzin ]")
            appendLine("  Işe başlama tarihine göre kazanılan yıllık izin günü hesapla.")
            appendLine("  AI yapabilir: izin hakkını hesapla ve anlat.")
            appendLine()
            appendLine("[ Bordro Simülasyon — Araçlar: Bordro ]")
            appendLine("  Tam bordro simülasyonu: tüm kesintiler, yan haklar, net hesap.")
            appendLine("  Bordro fotoğrafı ile OCR tarama özelliği var (Bordronu Tara butonu).")
            appendLine("  AI yapabilir: bordro kalemlerini açıkla.")
            appendLine()
            appendLine("[ İşsizlik Maaşı — Araçlar: İşsizlik Maaşı ]")
            appendLine("  İşten çıkma durumunda alınacak işsizlik ödeneği hesapla.")
            appendLine()
            appendLine("[ Emeklilik — Araçlar: Emeklilik ]")
            appendLine("  Sigorta giriş tarihi, yaş ve prim gününe göre emeklilik tarihi hesapla.")
            appendLine()
            appendLine("[ Enflasyon — Araçlar: Enflasyon ]")
            appendLine("  Belirli bir tutarın enflasyona göre gerçek değerini hesapla.")
            appendLine()
            appendLine("[ Maaş Karşılaştır — Araçlar: Maaş Karşılaştır ]")
            appendLine("  İki iş teklifini net değer, yan haklar ve maliyet açısından karşılaştır.")
            appendLine()
            appendLine("[ Haklarım — Araçlar: Hakkımı Arıyorum ]")
            appendLine("  Tazminatlı ayrılıp ayrılamayacağını hesapla (mobbing, kötü niyet vb.).")
            appendLine()
            appendLine("[ Ödeme Takip — Araçlar: Ödeme Takip ]")
            appendLine("  Fatura, kira, kredi, abonelik ödemelerini kaydet ve takip et.")
            appendLine("  AI yapabilir: add_payment, update_payment, delete_payment")
            appendLine()
            appendLine("[ Özel Günler — Araçlar: Özel Günler ]")
            appendLine("  Doğum günü, yıldönümü, özel tarihler ekle, bildirim al.")
            appendLine("  AI yapabilir: add_special_day, delete_special_day")
            appendLine()
            appendLine("[ Birikimlerim — Araçlar: Birikimlerim ]")
            appendLine("  Kripto, altın, döviz varlıklarını kaydet, anlık fiyat & kar/zarar gör.")
            appendLine("  AI yapabilir: add_savings, delete_savings")
            appendLine()
            appendLine("[ Anlık Kazanç — Araçlar: Anlık Kazanç ]")
            appendLine("  Saniye saniye çalışma saatlerinde ne kadar kazandığını gösterir.")
            appendLine()
            appendLine("[ Maaş Koçu — Araçlar: Maaş Koçu ]")
            appendLine("  Sektör, şehir ve deneyime göre maaşını piyasayla karşılaştır.")
            appendLine("  AI yapabilir: karşılaştırmayı anlat ve müzakere stratejisi öner.")
            appendLine()
            appendLine("[ Bütçe & Acil Fon — Araçlar: Bütçe & Acil Fon ]")
            appendLine("  50/30/20 kuralı ile bütçe planla, 6 aylık acil fon hedefi, finansal skor.")
            appendLine("  Ödeme takibinden otomatik veri çeker.")
            appendLine()
            appendLine("[ Haklarım Chatbot — Araçlar: Haklarım Chatbot ]")
            appendLine("  Kıdem, ihbar, fazla mesai, SGK, işten çıkarma gibi 12 konu hakkında hızlı bilgi.")
            appendLine("  ALO 170 / 182 / 150 iş hattı bağlantıları var.")
            appendLine()
            appendLine("[ Bildirim Ayarları — Ana ekran çan ikonu ]")
            appendLine("  Hangi olaylar için bildirim geleceğini ayarla (maaş, ödeme, özel gün, yedekleme).")
            appendLine("  AI yapabilir: neyi açıp kapatacağını anlat, kullanıcıyı yönlendir.")
            appendLine()
            appendLine("[ Profil — Ana ekran profil bölümü ]")
            appendLine("  Ad, brüt/net maaş, maaş günü, işe başlama tarihi, avans bilgileri.")
            appendLine("  AI yapabilir: update_profile")
            appendLine()

            // PROFIL
            appendLine("=== PROFIL ===")
            if (profile.name.isNotEmpty()) appendLine("Ad: ${profile.name}")
            if (profile.grossSalary > 0)   appendLine("Brut Maas: ${profile.grossSalary.toLong()} TL")
            if (profile.netSalary > 0)     appendLine("Net Maas: ${profile.netSalary.toLong()} TL")
            if (profile.salaryDay > 0)     appendLine("Maas Gunu: Ayin ${profile.salaryDay}.")
            if (profile.advanceAmount > 0) appendLine("Avans: ${profile.advanceAmount.toLong()} TL (Ayin ${profile.advanceDay}.)")
            val totalIncome = profile.totalIncome()
            if (totalIncome > profile.netSalary && totalIncome > 0)
                appendLine("Toplam Gelir (yan gelirler dahil): ${totalIncome.toLong()} TL")
            if (profile.sideIncomes.isNotEmpty()) {
                appendLine("Yan Gelirler:")
                profile.sideIncomes.forEach { si ->
                    appendLine("  - ${si.label} (${si.category.label}): ~${si.effectiveAmount().toLong()} TL/ay")
                }
            }

            // ODEME TAKİBİ
            if (payments.isNotEmpty()) {
                appendLine()
                appendLine("=== AYLIK SABIT ODEMELER ===")
                payments.forEach { p ->
                    appendLine("- [${p.id.take(8)}] ${p.name} (${p.category.label}): ${p.amount.toLong()} TL, ayin ${p.dueDayOfMonth}.")
                }
                appendLine("Toplam: ${totalPayments.toLong()} TL/ay")
                if (profile.netSalary > 0)
                    appendLine("Sabit odemeler sonrasi kalan: ${(profile.netSalary - totalPayments).toLong()} TL")
            }

            // FAZLA MESAİ
            if (overtimeAll.isNotEmpty()) {
                appendLine()
                appendLine("=== FAZLA MESAI ===")
                appendLine("Toplam ${overtimeAll.size} kayit — tum zamanlar net: ${overtimeAll.sumOf { it.netAmount }.toLong()} TL")
                if (overtimeMonth.isNotEmpty()) {
                    appendLine("Bu ay (${overtimeMonth.size} kayit, ${overtimeMonth.sumOf { it.netAmount }.toLong()} TL net):")
                    overtimeMonth.forEach { r ->
                        val d = SimpleDateFormat("dd.MM", Locale.getDefault()).format(java.util.Date(r.dateMillis))
                        appendLine("  - [${r.id.take(8)}] $d ${r.hours}s ${r.type.label}: net ${r.netAmount.toLong()} TL")
                    }
                }
            }

            // BİRİKİMLER
            if (savings.isNotEmpty()) {
                appendLine()
                appendLine("=== BIRIKIMLER ===")
                var totalCost = 0.0; var totalCurrent = 0.0
                savings.groupBy { it.category }.forEach { (cat, records) ->
                    appendLine("${cat.emoji} ${cat.label}:")
                    records.forEach { s ->
                        val cost = s.totalCostTry()
                        val curPrice = priceCache.priceOf(s.assetId)
                        val curVal = if (curPrice > 0) s.quantity * curPrice else 0.0
                        totalCost += cost; totalCurrent += curVal
                        val pnlStr = if (curVal > 0) {
                            val pnl = curVal - cost
                            val pct = if (cost > 0) pnl / cost * 100 else 0.0
                            " | K/Z: ${if (pnl >= 0) "+" else ""}${pnl.toLong()} TL (${"%.1f".format(pct)}%)"
                        } else ""
                        appendLine("  - [${s.id.take(8)}] ${s.assetName}: ${s.quantity} adet, alis: ${cost.toLong()} TL$pnlStr")
                    }
                }
                appendLine("Toplam alis: ${totalCost.toLong()} TL" +
                    if (totalCurrent > 0) ", guncel: ${totalCurrent.toLong()} TL, K/Z: ${if (totalCurrent - totalCost >= 0) "+" else ""}${(totalCurrent - totalCost).toLong()} TL" else "")
                if (priceCache.isStale()) appendLine("(Fiyat verisi eski — Birikimler ekranini acp guncelle)")
            }

            // ÖZEL GÜNLER
            if (specialDays.isNotEmpty()) {
                appendLine()
                appendLine("=== OZEL GUNLER ===")
                specialDays.forEach { d ->
                    val daysLeft = SpecialDayManager.daysUntil(d.day, d.month)
                    appendLine("- [${d.id.take(8)}] ${d.title}${if (d.subtitle.isNotEmpty()) " (${d.subtitle})" else ""}: ${d.day}.${d.month} — $daysLeft gun kaldi")
                }
                if (upcoming.isNotEmpty()) {
                    appendLine("Yaklasan (60 gun icinde): ${upcoming.joinToString(", ") { "${it.first.title} (${it.second} gun)" }}")
                }
            }

            // HAM VERİ (BackupManager ile otomatik — yeni özellikler buraya dahil olur)
            appendLine()
            appendLine("=== TUM UYGULAMA VERILERI (ham) ===")
            appendLine("Asagida uygulamadaki tum kaydedilmis veri JSON formatinda. Yukarida ozetlenmeyenler buradadir.")
            try {
                val bos = ByteArrayOutputStream()
                BackupManager.export(context, bos)
                val root  = JSONObject(bos.toString("UTF-8"))
                val prefs = root.optJSONObject("prefs") ?: JSONObject()
                prefs.keys().forEach { prefName ->
                    val obj = prefs.optJSONObject(prefName) ?: return@forEach
                    if (obj.length() == 0) return@forEach
                    appendLine("[$prefName]")
                    obj.keys().forEach { key ->
                        val entry = obj.optJSONObject(key)
                        val value = entry?.optString("v") ?: return@forEach
                        if (value.isNotBlank() && value != "[]" && value != "{}" && value != "0" && value != "false")
                            appendLine("  $key = $value")
                    }
                }
            } catch (_: Exception) { appendLine("(Veri okunamadi)") }

            appendLine()
            appendLine("Islem araclari: add_overtime, delete_overtime, update_payment, add_payment, delete_payment,")
            appendLine("add_savings, delete_savings, update_profile, get_summary")
            appendLine("Turkiye calisma mevzuatini biliyorsun: kidem, ihbar, izin, mesai, SGK vs.")
        }
    }

    // ── Araç tanımları ───────────────────────────────────────────────────
    private fun toolDefinitions(): JSONArray {
        fun param(type: String, desc: String, enumVals: List<String>? = null) = JSONObject().apply {
            put("type", type); put("description", desc)
            if (enumVals != null) put("enum", JSONArray(enumVals))
        }
        fun tool(name: String, desc: String, props: JSONObject, required: List<String>) =
            JSONObject().apply {
                put("type", "function")
                put("function", JSONObject().apply {
                    put("name", name); put("description", desc)
                    put("parameters", JSONObject().apply {
                        put("type", "object"); put("properties", props)
                        put("required", JSONArray(required))
                    })
                })
            }

        return JSONArray().apply {
            // Mesai
            put(tool("add_overtime",
                "Fazla mesai kaydı ekle.",
                JSONObject().apply {
                    put("hours", param("number", "Saat"))
                    put("type",  param("string", "Tur", listOf("PCT25","PCT50","PCT75","PCT100","PCT125","PCT200")))
                    put("date",  param("string", "YYYY-MM-DD veya today"))
                    put("note",  param("string", "Not"))
                }, listOf("hours","type")))

            put(tool("delete_overtime",
                "Fazla mesai kaydını sil. id veya 'last' (son kayit) ile.",
                JSONObject().apply {
                    put("id", param("string", "Kayit id'sinin ilk 8 hanesi veya 'last'"))
                }, listOf("id")))

            // Ödemeler
            put(tool("update_payment",
                "Mevcut ödemenin tutarını güncelle.",
                JSONObject().apply {
                    put("payment_name", param("string", "Odeme adinin bir kismi"))
                    put("new_amount",   param("number", "Yeni tutar TL"))
                }, listOf("payment_name","new_amount")))

            put(tool("add_payment",
                "Yeni sabit ödeme/fatura ekle.",
                JSONObject().apply {
                    put("name",     param("string", "Ad"))
                    put("amount",   param("number", "Tutar TL"))
                    put("category", param("string", "Kategori", listOf("KIRA","FATURA","KREDI","ABONELIK","SIGORTA","DIGER")))
                    put("due_day",  param("integer", "Ayin kacinda (1-31)"))
                }, listOf("name","amount","category")))

            put(tool("delete_payment",
                "Ödemeyi sil.",
                JSONObject().apply {
                    put("payment_name", param("string", "Odeme adinin bir kismi"))
                }, listOf("payment_name")))

            // Birikimler
            put(tool("add_savings",
                "Birikime varlık ekle (kripto/altın/döviz).",
                JSONObject().apply {
                    put("asset_symbol", param("string", "BTC ETH TIA SOL ALTIN USD EUR vb."))
                    put("quantity",     param("number", "Miktar"))
                    put("buy_price",    param("number", "Alis fiyati TL/birim"))
                    put("note",         param("string", "Not"))
                }, listOf("asset_symbol","quantity","buy_price")))

            put(tool("delete_savings",
                "Birikim kaydını sil.",
                JSONObject().apply {
                    put("asset_symbol", param("string", "Sembol veya id ilk 8 hanesi"))
                }, listOf("asset_symbol")))

            // Profil
            put(tool("update_profile",
                "Kullanıcı profilini güncelle (maaş, isim, maaş günü vb.).",
                JSONObject().apply {
                    put("name",         param("string", "Ad (degismiyorsa bos birak)"))
                    put("gross_salary", param("number", "Brut maas TL (0 = degistirme)"))
                    put("net_salary",   param("number", "Net maas TL (0 = degistirme)"))
                    put("salary_day",   param("integer", "Maas gunu (0 = degistirme)"))
                }, listOf()))

            // Özel Günler
            put(tool("add_special_day",
                "Özel gün / doğum günü / yıldönümü ekle.",
                JSONObject().apply {
                    put("title",    param("string", "Tur: Dogum Gunu / Evlilik Yildonumu / Anma vb."))
                    put("subtitle", param("string", "Kisi adi veya aciklama (opsiyonel)"))
                    put("day",      param("integer", "Gun (1-31)"))
                    put("month",    param("integer", "Ay (1-12)"))
                }, listOf("title","day","month")))

            put(tool("delete_special_day",
                "Özel günü sil.",
                JSONObject().apply {
                    put("title_or_id", param("string", "Baslik kismi veya id ilk 8 hanesi"))
                }, listOf("title_or_id")))

            // Özet
            put(tool("get_summary",
                "Bu ayın mali özetini hesapla.",
                JSONObject().apply {}, listOf()))
        }
    }

    // ── Araç çalıştırıcı ────────────────────────────────────────────────
    private fun executeTool(context: Context, name: String, args: JSONObject): String {
        return try {
            when (name) {
                "add_overtime" -> {
                    val profile = ProfileManager(context).load()
                    val hours   = args.getDouble("hours")
                    val type    = try { OvertimeTrackType.valueOf(args.optString("type","PCT50")) } catch (_: Exception) { OvertimeTrackType.PCT50 }
                    val dateMs  = args.optString("date","today").let { d ->
                        if (d == "today" || d.isBlank()) System.currentTimeMillis()
                        else try { SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).parse(d)?.time ?: System.currentTimeMillis() } catch (_: Exception) { System.currentTimeMillis() }
                    }
                    val brut = OvertimeManager.calcBrutAmount(profile.grossSalary, hours, type)
                    val net  = OvertimeManager.calcNetAmount(brut)
                    OvertimeManager.add(context, OvertimeRecord(dateMillis = dateMs, hours = hours, type = type,
                        brutAmount = brut, netAmount = net, note = args.optString("note","")))
                    "BASARILI: ${hours}s ${type.label} mesai eklendi — net ${net.toLong()} TL, brut ${brut.toLong()} TL"
                }

                "delete_overtime" -> {
                    val idPrefix = args.getString("id")
                    val all = OvertimeManager.loadAll(context)
                    val target = if (idPrefix == "last") all.maxByOrNull { it.dateMillis }
                                 else all.firstOrNull { it.id.startsWith(idPrefix) }
                    if (target != null) {
                        OvertimeManager.delete(context, target.id)
                        val d = SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()).format(java.util.Date(target.dateMillis))
                        "BASARILI: $d tarihli ${target.hours}s mesai kaydi silindi."
                    } else "HATA: Kayit bulunamadi."
                }

                "update_payment" -> {
                    val kw = args.getString("payment_name").lowercase()
                    val amt = args.getDouble("new_amount")
                    val match = PaymentManager.getPayments(context).firstOrNull { it.name.lowercase().contains(kw) }
                    if (match != null) { PaymentManager.savePayment(context, match.copy(amount = amt))
                        "BASARILI: '${match.name}' -> ${amt.toLong()} TL olarak guncellendi."
                    } else "HATA: '$kw' odeme bulunamadi."
                }

                "add_payment" -> {
                    val cat = try { PaymentCategory.valueOf(args.optString("category","DIGER")) } catch (_: Exception) { PaymentCategory.DIGER }
                    val p   = Payment(name = args.getString("name"), amount = args.getDouble("amount"),
                        category = cat, dueDayOfMonth = args.optInt("due_day",1))
                    PaymentManager.savePayment(context, p)
                    "BASARILI: '${p.name}' odeme eklendi — ${p.amount.toLong()} TL/ay"
                }

                "delete_payment" -> {
                    val kw = args.getString("payment_name").lowercase()
                    val match = PaymentManager.getPayments(context).firstOrNull { it.name.lowercase().contains(kw) }
                    if (match != null) { PaymentManager.deletePayment(context, match.id)
                        "BASARILI: '${match.name}' odeme silindi."
                    } else "HATA: '$kw' odeme bulunamadi."
                }

                "add_savings" -> {
                    val sym   = args.getString("asset_symbol").uppercase().trim()
                    val qty   = args.getDouble("quantity")
                    val price = args.getDouble("buy_price")
                    val coinId  = KnownCoins.idOf(sym)
                    val metalId = KnownMetals.list.firstOrNull { it.second.contains(sym, ignoreCase = true) }?.first
                    val currId  = KnownCurrencies.list.firstOrNull { it.first.equals(sym, ignoreCase = true) }?.first
                    val (cat, assetId, assetName) = when {
                        coinId  != null -> Triple(SavingsCategory.CRYPTO, coinId, sym)
                        metalId != null -> Triple(SavingsCategory.METAL, metalId, sym)
                        currId  != null -> Triple(SavingsCategory.DOVIZ, currId, KnownCurrencies.list.first { it.first == currId }.second)
                        sym.contains("ALTIN", ignoreCase = true) -> Triple(SavingsCategory.METAL, "tether-gold", "Altin (gram)")
                        else -> Triple(SavingsCategory.CRYPTO, sym.lowercase(), sym)
                    }
                    SavingsManager(context).add(SavingsRecord(category = cat, assetId = assetId,
                        assetName = assetName, quantity = qty, buyPriceTry = price,
                        note = args.optString("note","")))
                    "BASARILI: $qty adet $assetName eklendi — alis maliyeti: ${(qty * price).toLong()} TL"
                }

                "delete_savings" -> {
                    val sym = args.getString("asset_symbol").uppercase().trim()
                    val all = SavingsManager(context).loadAll()
                    val match = all.firstOrNull { it.assetName.uppercase().contains(sym) || it.id.startsWith(sym.lowercase()) }
                    if (match != null) { SavingsManager(context).delete(match.id)
                        "BASARILI: ${match.assetName} (${match.quantity} adet) silindi."
                    } else "HATA: '$sym' birikim bulunamadi. Mevcut: ${all.map { it.assetName }}"
                }

                "add_special_day" -> {
                    val sd = SpecialDay(
                        title    = args.getString("title"),
                        subtitle = args.optString("subtitle", ""),
                        day      = args.getInt("day"),
                        month    = args.getInt("month")
                    )
                    SpecialDayManager.save(context, sd)
                    val daysLeft = SpecialDayManager.daysUntil(sd.day, sd.month)
                    "BASARILI: '${sd.title}${if (sd.subtitle.isNotEmpty()) " (${sd.subtitle})" else ""}' ${sd.day}.${sd.month} tarihinde eklendi — $daysLeft gun kaldi."
                }

                "delete_special_day" -> {
                    val query = args.getString("title_or_id").lowercase()
                    val all   = SpecialDayManager.getAll(context)
                    val match = all.firstOrNull { it.title.lowercase().contains(query) || it.subtitle.lowercase().contains(query) || it.id.startsWith(query) }
                    if (match != null) {
                        SpecialDayManager.delete(context, match.id)
                        "BASARILI: '${match.title}${if (match.subtitle.isNotEmpty()) " (${match.subtitle})" else ""}' silindi."
                    } else "HATA: '$query' bulunamadi. Mevcut: ${all.map { it.title }}"
                }

                "update_profile" -> {
                    val pm = ProfileManager(context)
                    val p  = pm.load()
                    val updated = p.copy(
                        name         = args.optString("name","").ifBlank { p.name },
                        grossSalary  = args.optDouble("gross_salary", 0.0).let { if (it > 0) it else p.grossSalary },
                        netSalary    = args.optDouble("net_salary",   0.0).let { if (it > 0) it else p.netSalary },
                        salaryDay    = args.optInt("salary_day",      0  ).let { if (it > 0) it else p.salaryDay }
                    )
                    pm.save(updated)
                    "BASARILI: Profil guncellendi. Net: ${updated.netSalary.toLong()} TL, Brut: ${updated.grossSalary.toLong()} TL"
                }

                "get_summary" -> {
                    val p     = ProfileManager(context).load()
                    val pays  = PaymentManager.getPayments(context).filter { it.isActive }
                    val otM   = OvertimeManager.thisMonthRecords(context)
                    val today = java.util.Calendar.getInstance().get(java.util.Calendar.DAY_OF_MONTH)
                    val daysLeft = if (p.salaryDay > 0) { val d = p.salaryDay - today; if (d < 0) d + 30 else d } else -1
                    buildString {
                        if (p.netSalary > 0) appendLine("Net maas: ${p.netSalary.toLong()} TL")
                        appendLine("Sabit odemeler: ${pays.sumOf { it.amount }.toLong()} TL")
                        if (p.netSalary > 0) appendLine("Kalan: ${(p.netSalary - pays.sumOf { it.amount }).toLong()} TL")
                        if (otM.isNotEmpty()) appendLine("Bu ay mesai: ${otM.sumOf { it.netAmount }.toLong()} TL (${otM.size} kayit)")
                        val side = p.sideIncomes.sumOf { it.currentMonthAmount() }
                        if (side > 0) appendLine("Yan gelirler: ${side.toLong()} TL")
                        if (daysLeft >= 0) appendLine("Masaya $daysLeft gun kaldi.")
                    }
                }

                else -> "Bilinmeyen arac: $name"
            }
        } catch (e: Exception) { "Arac hatasi: ${e.message}" }
    }

    // ── API çağrısı ──────────────────────────────────────────────────────
    private fun callApi(apiKey: String, body: JSONObject): JSONObject {
        val conn = (URL(API_URL).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Authorization", "Bearer $apiKey")
            doOutput = true; connectTimeout = 30_000; readTimeout = 60_000
        }
        conn.outputStream.use { it.write(body.toString().toByteArray()) }
        val code = conn.responseCode
        val raw  = if (code == 200) conn.inputStream.bufferedReader().readText()
                   else conn.errorStream?.bufferedReader()?.readText() ?: "HTTP $code"
        if (code != 200) error("API hatasi $code: $raw")
        return JSONObject(raw)
    }

    // ── Ana mesaj gönderici (tool call döngüsü dahil) ────────────────────
    suspend fun sendMessage(
        context: Context,
        history: List<ChatMessage>,
        userMessage: String
    ): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            val apiKey = DeepSeekKeyManager.getKey(context)
            if (apiKey.isBlank()) error("API_KEY_MISSING")

            val messages = JSONArray()
            messages.put(JSONObject().apply { put("role","system"); put("content", buildSystemPrompt(context)) })
            history.takeLast(10).forEach { msg ->
                messages.put(JSONObject().apply { put("role", msg.role); put("content", msg.content) })
            }
            messages.put(JSONObject().apply { put("role","user"); put("content", userMessage) })

            var body = JSONObject().apply {
                put("model", MODEL); put("messages", messages)
                put("max_tokens", 1024); put("temperature", 0.7)
                put("tools", toolDefinitions()); put("tool_choice", "auto")
            }

            var response = callApi(apiKey, body)
            var choice   = response.getJSONArray("choices").getJSONObject(0)

            repeat(5) {
                if (choice.optString("finish_reason") != "tool_calls") return@repeat
                val assistantMsg = choice.getJSONObject("message")
                messages.put(assistantMsg)
                val toolCalls = assistantMsg.getJSONArray("tool_calls")
                for (i in 0 until toolCalls.length()) {
                    val tc = toolCalls.getJSONObject(i)
                    val result = executeTool(context,
                        tc.getJSONObject("function").getString("name"),
                        JSONObject(tc.getJSONObject("function").getString("arguments")))
                    messages.put(JSONObject().apply {
                        put("role","tool"); put("tool_call_id", tc.getString("id")); put("content", result)
                    })
                }
                body = JSONObject().apply {
                    put("model", MODEL); put("messages", messages)
                    put("max_tokens", 1024); put("temperature", 0.7)
                }
                response = callApi(apiKey, body)
                choice   = response.getJSONArray("choices").getJSONObject(0)
            }

            choice.getJSONObject("message").getString("content")
        }
    }
}
