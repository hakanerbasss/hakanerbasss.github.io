package com.wizaicorp.namazvakitleri.data

import android.content.Context
import java.util.Locale

object Lang {

    private const val PREF = "namaz_prefs"
    private const val KEY  = "app_lang" // "system" | "tr" | "en"

    var code: String = "en"
        private set

    fun init(ctx: Context) {
        val pref = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(KEY, "system") ?: "system"
        code = resolve(pref)
    }

    fun getSetting(ctx: Context): String =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(KEY, "system") ?: "system"

    fun setSetting(ctx: Context, setting: String) {
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString(KEY, setting).apply()
        code = resolve(setting)
    }

    private fun resolve(setting: String): String = when (setting) {
        "tr", "en" -> setting
        else       -> if (Locale.getDefault().language == "tr") "tr" else "en"
    }

    fun get(key: String): String =
        (if (code == "tr") tr[key] else en[key]) ?: en[key] ?: key

    fun fmt(key: String, vararg args: Any): String =
        try { String.format(get(key), *args) } catch (e: Exception) { get(key) }

    private val en = mapOf(
        // Tabs
        "tab_times" to "Times",
        "tab_qibla" to "Qibla",
        "tab_calendar" to "Calendar",
        "tab_more" to "More",
        // Prayer names
        "p_imsak" to "Fajr",
        "p_gunes" to "Sunrise",
        "p_ogle" to "Dhuhr",
        "p_ikindi" to "Asr",
        "p_aksam" to "Maghrib",
        "p_yatsi" to "Isha",
        "p_sabah" to "Fajr",
        "p_vitir" to "Witr",
        // Main screen
        "next_prayer" to "Next Prayer",
        "left" to "left",
        "h_short" to "h",
        "m_short" to "min",
        "offline_cached" to "Offline - showing saved times",
        "err_load" to "Could not load times. Check your internet connection.",
        "retry" to "Retry",
        "today" to "Today",
        // Settings
        "settings_title" to "Notification Settings",
        "pre_reminder_q" to "Remind how many minutes before?",
        "on_time_chip" to "At prayer time",
        "min_before" to "min before",
        "which_prayers" to "Which prayers?",
        "saved" to "Saved",
        "lang_label" to "App Language",
        "lang_system" to "System",
        // City select
        "city_search" to "Search City",
        "city_label" to "City",
        "country_label" to "Country (in English)",
        "city_hint" to "E.g: Istanbul, London, Dubai, Mecca",
        "country_hint" to "E.g: Turkey, United Kingdom, Saudi Arabia",
        "search" to "Search",
        "searching" to "Searching...",
        "city_not_found" to "City not found. Check the city and country name.",
        "select_this_city" to "Select This City",
        "current_city" to "Current",
        "back" to "Back",
        // Calendar
        "month_1" to "January", "month_2" to "February", "month_3" to "March",
        "month_4" to "April", "month_5" to "May", "month_6" to "June",
        "month_7" to "July", "month_8" to "August", "month_9" to "September",
        "month_10" to "October", "month_11" to "November", "month_12" to "December",
        "err_calendar" to "Could not load calendar. Check your internet connection.",
        // More menu
        "zikir" to "Tasbih Counter",
        "kaza" to "Missed Prayers",
        "holy_days" to "Islamic Days",
        "esma" to "99 Names of Allah",
        "notif_settings" to "Notifications",
        "change_city" to "Change City",
        "share_app" to "Share",
        "rate_app" to "Rate App",
        "privacy" to "Privacy Policy",
        "share_today" to "Today's prayer times",
        // Zikir
        "target" to "Target",
        "unlimited" to "Free",
        "reset" to "Reset",
        "total" to "Total",
        "tap_hint" to "Tap anywhere to count",
        "target_done" to "Target completed!",
        "z_1" to "SubhanAllah",
        "z_2" to "Alhamdulillah",
        "z_3" to "Allahu Akbar",
        "z_4" to "La ilaha illallah",
        "z_5" to "Astaghfirullah",
        "z_6" to "Salawat",
        // Kaza
        "kaza_desc" to "Track your missed prayers. Decrease the count as you make them up.",
        "add_one_day" to "+1 Day (add to all)",
        // Holy days
        "holy_disclaimer" to "Dates are calculated from the astronomical hijri calendar and may differ by one day from official announcements.",
        "days_left" to "days left",
        "e_regaib" to "Laylat al-Raghaib",
        "e_mirac" to "Laylat al-Miraj",
        "e_berat" to "Laylat al-Baraah",
        "e_uc_aylar" to "Start of the Three Months",
        "e_ramazan" to "Start of Ramadan",
        "e_kadir" to "Laylat al-Qadr",
        "e_ramazan_bayram" to "Eid al-Fitr",
        "e_arefe" to "Day of Arafah",
        "e_kurban" to "Eid al-Adha",
        "e_hicri_yil" to "Islamic New Year",
        "e_asure" to "Day of Ashura",
        "e_mevlid" to "Mawlid al-Nabi",
        // Esma
        "esma_of_day" to "Name of the Day",
        // Hijri months
        "h_1" to "Muharram", "h_2" to "Safar", "h_3" to "Rabi al-Awwal",
        "h_4" to "Rabi al-Thani", "h_5" to "Jumada al-Awwal", "h_6" to "Jumada al-Thani",
        "h_7" to "Rajab", "h_8" to "Shaban", "h_9" to "Ramadan",
        "h_10" to "Shawwal", "h_11" to "Dhul-Qadah", "h_12" to "Dhul-Hijjah",
        // Notifications
        "notif_entered" to "It's time for %s.",
        "notif_pre" to "%2\$d minutes until %1\$s.",
        "notif_channel" to "Prayer Times",
        // Widget
        "w_next" to "Next",
        // Sound (zikir + esma)
        "sound_label" to "Sound",
        "sound_off" to "Off",
        "sound_tts" to "Voice",
        "sound_rec" to "My recording",
        "record_start" to "Record",
        "record_stop" to "Stop recording",
        "rec_missing" to "No recording yet - press Record and say the dhikr",
        "rec_saved" to "Recording saved",
        "mic_perm" to "Microphone permission required",
        "read_all" to "Read All",
        "stop" to "Stop",
        // Reminders
        "holy_notif_label" to "Islamic day alerts",
        "kaza_notif_label" to "Missed prayer reminder",
        "reminder_hour" to "Reminder time",
        "holy_today_notif" to "Today is %s",
        "holy_eve_notif" to "%s begins tonight",
        "kaza_left" to "Remaining",
        "channel_reminder" to "Reminders",
        // Library
        "library" to "Islamic Library",
        "lib_sure_tab" to "Surahs",
        "lib_dua_tab" to "Duas",
        "mode_reading" to "Transliteration",
        "mode_meaning" to "Meaning",
        // API keys
        "api_settings" to "API Keys",
        "key_hint" to "Paste your key here",
        "save" to "Save",
        "how_to_get" to "How do I get one?",
        "pexels_unlocks" to "Unlocks the daily photo on the home screen (free)",
        "deepseek_unlocks" to "Unlocks the AI Assistant (voice + text)",
        "pexels_guide" to "1) Go to pexels.com/api\n2) Create a free account with your e-mail\n3) Copy the key on the 'Your API Key' page\n4) Paste it here and tap Save\nFree plan: 200 requests/hour - this app uses about 1 per day.",
        "deepseek_guide" to "1) Go to platform.deepseek.com\n2) Create an account and sign in\n3) Open 'API Keys' and tap 'Create new API key'\n4) Copy the key, paste it here and tap Save\nNote: DeepSeek is pay-as-you-go; you may need to add a small balance. The key is stored only on your device.",
        "key_stored_note" to "Keys are stored only on this device and are never shared.",
        // News
        "news" to "Religious News",
        "news_err" to "Could not load news. Check your internet connection.",
        // Assistant
        "assistant" to "AI Assistant",
        "assistant_disclaimer" to "Answers are for information only and are NOT religious rulings (fatwa). Consult your local religious authority for important matters.",
        "ask_hint" to "Type your question...",
        "thinking" to "Thinking...",
        "assistant_err" to "No answer received. Check your API key and internet connection.",
        "tts_toggle" to "Read answers aloud",
        // Today card
        "quote_of_day" to "Quote of the Day",
        // Qibla
        "qibla_perm" to "Grant Location Permission",
        "qibla_aligned" to "You are facing the Qibla!",
        "qibla_hint" to "Point the arrow toward the Kaaba",
        "qibla_dist" to "%s km to the Kaaba",
        "qibla_label" to "Qibla",
        // Education
        "education" to "Prayer Guide",
        "edu_disclaimer" to "This guide follows the Hanafi school and Diyanet sources. Consult a scholar for details.",
        // Recitation + Ramadan
        "mode_audio" to "Recitation",
        "ramadan" to "Ramadan",
        "iftar_left" to "Until iftar",
        "sahur_left" to "Until imsak (suhoor ends)"
    )

    private val tr = mapOf(
        // Tabs
        "tab_times" to "Vakitler",
        "tab_qibla" to "Kıble",
        "tab_calendar" to "Takvim",
        "tab_more" to "Daha Fazla",
        // Prayer names
        "p_imsak" to "İmsak",
        "p_gunes" to "Güneş",
        "p_ogle" to "Öğle",
        "p_ikindi" to "İkindi",
        "p_aksam" to "Akşam",
        "p_yatsi" to "Yatsı",
        "p_sabah" to "Sabah",
        "p_vitir" to "Vitir",
        // Main screen
        "next_prayer" to "Sıradaki Vakit",
        "left" to "kaldı",
        "h_short" to "sa",
        "m_short" to "dk",
        "offline_cached" to "Çevrimdışı - kayıtlı vakitler gösteriliyor",
        "err_load" to "Vakitler yüklenemedi. İnternet bağlantınızı kontrol edin.",
        "retry" to "Tekrar Dene",
        "today" to "Bugün",
        // Settings
        "settings_title" to "Bildirim Ayarları",
        "pre_reminder_q" to "Vakitten kaç dakika önce hatırlatılsın?",
        "on_time_chip" to "Tam vakitte",
        "min_before" to "dk önce",
        "which_prayers" to "Hangi vakitler?",
        "saved" to "Kaydedildi",
        "lang_label" to "Uygulama Dili",
        "lang_system" to "Sistem",
        // City select
        "city_search" to "Şehir Ara",
        "city_label" to "Şehir",
        "country_label" to "Ülke (İngilizce)",
        "city_hint" to "Örn: Istanbul, London, Dubai, Mecca",
        "country_hint" to "Örn: Turkey, United Kingdom, Saudi Arabia",
        "search" to "Ara",
        "searching" to "Aranıyor...",
        "city_not_found" to "Şehir bulunamadı. Şehir ve ülke adını kontrol edin.",
        "select_this_city" to "Bu Şehri Seç",
        "current_city" to "Mevcut",
        "back" to "Geri",
        // Calendar
        "month_1" to "Ocak", "month_2" to "Şubat", "month_3" to "Mart",
        "month_4" to "Nisan", "month_5" to "Mayıs", "month_6" to "Haziran",
        "month_7" to "Temmuz", "month_8" to "Ağustos", "month_9" to "Eylül",
        "month_10" to "Ekim", "month_11" to "Kasım", "month_12" to "Aralık",
        "err_calendar" to "Takvim yüklenemedi. İnternet bağlantınızı kontrol edin.",
        // More menu
        "zikir" to "Zikirmatik",
        "kaza" to "Kaza Takibi",
        "holy_days" to "Dini Günler",
        "esma" to "Esmaül Hüsna",
        "notif_settings" to "Bildirim Ayarları",
        "change_city" to "Şehir Değiştir",
        "share_app" to "Paylaş",
        "rate_app" to "Değerlendir",
        "privacy" to "Gizlilik Politikası",
        "share_today" to "Bugünün namaz vakitleri",
        // Zikir
        "target" to "Hedef",
        "unlimited" to "Serbest",
        "reset" to "Sıfırla",
        "total" to "Toplam",
        "tap_hint" to "Saymak için ekrana dokun",
        "target_done" to "Hedef tamamlandı!",
        "z_1" to "Sübhanallah",
        "z_2" to "Elhamdülillah",
        "z_3" to "Allahu Ekber",
        "z_4" to "La ilahe illallah",
        "z_5" to "Estağfirullah",
        "z_6" to "Salavat",
        // Kaza
        "kaza_desc" to "Kılamadığın namazları kaydet, kıldıkça düş.",
        "add_one_day" to "+1 Gün (tümüne ekle)",
        // Holy days
        "holy_disclaimer" to "Tarihler astronomik hicri takvime göre hesaplanır; resmi takvimle 1 gün fark edebilir.",
        "days_left" to "gün kaldı",
        "e_regaib" to "Regaib Kandili",
        "e_mirac" to "Miraç Kandili",
        "e_berat" to "Berat Kandili",
        "e_uc_aylar" to "Üç Ayların Başlangıcı",
        "e_ramazan" to "Ramazan Başlangıcı",
        "e_kadir" to "Kadir Gecesi",
        "e_ramazan_bayram" to "Ramazan Bayramı",
        "e_arefe" to "Arefe Günü",
        "e_kurban" to "Kurban Bayramı",
        "e_hicri_yil" to "Hicri Yılbaşı",
        "e_asure" to "Aşure Günü",
        "e_mevlid" to "Mevlid Kandili",
        // Esma
        "esma_of_day" to "Günün Esması",
        // Hijri months
        "h_1" to "Muharrem", "h_2" to "Safer", "h_3" to "Rebiülevvel",
        "h_4" to "Rebiülahir", "h_5" to "Cemaziyelevvel", "h_6" to "Cemaziyelahir",
        "h_7" to "Recep", "h_8" to "Şaban", "h_9" to "Ramazan",
        "h_10" to "Şevval", "h_11" to "Zilkade", "h_12" to "Zilhicce",
        // Notifications
        "notif_entered" to "%s vakti girdi.",
        "notif_pre" to "%1\$s vaktine %2\$d dakika kaldı.",
        "notif_channel" to "Namaz Vakitleri",
        // Widget
        "w_next" to "Sıradaki",
        // Sound (zikir + esma)
        "sound_label" to "Ses",
        "sound_off" to "Kapalı",
        "sound_tts" to "Seslendir",
        "sound_rec" to "Kaydım",
        "record_start" to "Kayıt Al",
        "record_stop" to "Kaydı Bitir",
        "rec_missing" to "Henüz kayıt yok - Kayıt Al'a basıp zikri söyle",
        "rec_saved" to "Kayıt kaydedildi",
        "mic_perm" to "Mikrofon izni gerekli",
        "read_all" to "Sırayla Oku",
        "stop" to "Durdur",
        // Reminders
        "holy_notif_label" to "Dini gün bildirimleri",
        "kaza_notif_label" to "Kaza hatırlatması",
        "reminder_hour" to "Hatırlatma saati",
        "holy_today_notif" to "Bugün %s",
        "holy_eve_notif" to "Bu akşam %s başlıyor",
        "kaza_left" to "Kalan kaza",
        "channel_reminder" to "Hatırlatmalar",
        // Library
        "library" to "Dini Kütüphane",
        "lib_sure_tab" to "Sureler",
        "lib_dua_tab" to "Dualar",
        "mode_reading" to "Okunuş",
        "mode_meaning" to "Meal",
        // API keys
        "api_settings" to "API Anahtarları",
        "key_hint" to "Anahtarı buraya yapıştır",
        "save" to "Kaydet",
        "how_to_get" to "Nasıl alınır?",
        "pexels_unlocks" to "Ana ekrandaki günün görselini açar (ücretsiz)",
        "deepseek_unlocks" to "AI Asistan özelliğini açar (sesli + yazılı)",
        "pexels_guide" to "1) pexels.com/api adresine gir\n2) E-posta ile ücretsiz hesap aç\n3) 'Your API Key' sayfasındaki anahtarı kopyala\n4) Buraya yapıştır ve Kaydet'e bas\nÜcretsiz plan: saatte 200 istek - bu uygulama günde yaklaşık 1 istek kullanır.",
        "deepseek_guide" to "1) platform.deepseek.com adresine gir\n2) Hesap aç ve giriş yap\n3) 'API Keys' bölümünden 'Create new API key' ile anahtar oluştur\n4) Anahtarı kopyala, buraya yapıştır ve Kaydet'e bas\nNot: DeepSeek kullandıkça öde çalışır; hesabına küçük bir bakiye yüklemen gerekebilir. Anahtar yalnızca cihazında saklanır.",
        "key_stored_note" to "Anahtarlar yalnızca bu cihazda saklanır, hiçbir yere gönderilmez.",
        // News
        "news" to "Dini Haberler",
        "news_err" to "Haberler yüklenemedi. İnternet bağlantınızı kontrol edin.",
        // Assistant
        "assistant" to "AI Asistan",
        "assistant_disclaimer" to "Cevaplar bilgilendirme amaçlıdır, fetva DEĞİLDİR. Önemli konularda müftülüğe / Diyanet'e danışın.",
        "ask_hint" to "Sorunuzu yazın...",
        "thinking" to "Yanıtlıyor...",
        "assistant_err" to "Cevap alınamadı. API anahtarını ve internet bağlantınızı kontrol edin.",
        "tts_toggle" to "Cevabı sesli oku",
        // Today card
        "quote_of_day" to "Günün Sözü",
        // Qibla
        "qibla_perm" to "Konum İzni Ver",
        "qibla_aligned" to "Kıbleye Dönüksünüz!",
        "qibla_hint" to "Oku Kabe'ye doğrultun",
        "qibla_dist" to "Kabe'ye %s km",
        "qibla_label" to "Kıble",
        // Education
        "education" to "Namaz Eğitimi",
        "edu_disclaimer" to "Anlatım Hanefî mezhebine ve Diyanet kaynaklarına göredir. Ayrıntılar için ilmihale veya müftülüğe başvurunuz.",
        // Recitation + Ramadan
        "mode_audio" to "Kıraat",
        "ramadan" to "Ramazan",
        "iftar_left" to "İftara kalan",
        "sahur_left" to "İmsaka kalan"
    )
}
