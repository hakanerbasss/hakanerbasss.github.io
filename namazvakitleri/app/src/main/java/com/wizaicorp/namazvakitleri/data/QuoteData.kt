package com.wizaicorp.namazvakitleri.data

data class Quote(
    val textTr: String,
    val textEn: String,
    val sourceTr: String,
    val sourceEn: String
) {
    val text: String get() = if (Lang.code == "tr") textTr else textEn
    val source: String get() = if (Lang.code == "tr") sourceTr else sourceEn
}

/** Gunun sozu - dogrulanabilir, yaygin bilinen ayet mealleri ve hadisler. */
object QuoteData {

    val list = listOf(
        Quote("Ameller niyetlere göredir.",
            "Actions are judged by intentions.",
            "Hadis-i Şerif (Buhârî)", "Hadith (Bukhari)"),
        Quote("Şüphesiz güçlükle beraber kolaylık vardır.",
            "Indeed, with hardship comes ease.",
            "İnşirâh Suresi, 6", "Quran, Ash-Sharh 94:6"),
        Quote("Kolaylaştırın, zorlaştırmayın; müjdeleyin, nefret ettirmeyin.",
            "Make things easy, not difficult; give glad tidings, do not repel people.",
            "Hadis-i Şerif (Buhârî)", "Hadith (Bukhari)"),
        Quote("Allah sabredenlerle beraberdir.",
            "Indeed, Allah is with those who are patient.",
            "Bakara Suresi, 153", "Quran, Al-Baqarah 2:153"),
        Quote("Hiçbiriniz kendisi için istediğini kardeşi için istemedikçe iman etmiş olmaz.",
            "None of you truly believes until he loves for his brother what he loves for himself.",
            "Hadis-i Şerif (Buhârî)", "Hadith (Bukhari)"),
        Quote("Kalpler ancak Allah'ı anmakla huzur bulur.",
            "Verily, in the remembrance of Allah do hearts find rest.",
            "Ra'd Suresi, 28", "Quran, Ar-Ra'd 13:28"),
        Quote("Temizlik imanın yarısıdır.",
            "Cleanliness is half of faith.",
            "Hadis-i Şerif (Müslim)", "Hadith (Muslim)"),
        Quote("Bana dua edin, size cevap vereyim.",
            "Call upon Me; I will respond to you.",
            "Mü'min Suresi, 60", "Quran, Ghafir 40:60"),
        Quote("Allah katında en sevimli amel, az da olsa devamlı olanıdır.",
            "The most beloved deeds to Allah are those done regularly, even if small.",
            "Hadis-i Şerif (Buhârî)", "Hadith (Bukhari)"),
        Quote("Allah'ın rahmetinden ümidinizi kesmeyin.",
            "Do not despair of the mercy of Allah.",
            "Zümer Suresi, 53", "Quran, Az-Zumar 39:53"),
        Quote("Müslüman, elinden ve dilinden insanların güvende olduğu kimsedir.",
            "A Muslim is the one from whose tongue and hand people are safe.",
            "Hadis-i Şerif (Buhârî)", "Hadith (Bukhari)"),
        Quote("Kim Allah'a ve ahiret gününe inanıyorsa ya hayır söylesin ya da sussun.",
            "Whoever believes in Allah and the Last Day should speak good or remain silent.",
            "Hadis-i Şerif (Buhârî)", "Hadith (Bukhari)"),
        Quote("Nerede olursanız olun, O sizinle beraberdir.",
            "He is with you wherever you are.",
            "Hadîd Suresi, 4", "Quran, Al-Hadid 57:4"),
        Quote("Güzel söz sadakadır.",
            "A good word is charity.",
            "Hadis-i Şerif (Buhârî)", "Hadith (Bukhari)"),
        Quote("Merhamet etmeyene merhamet edilmez.",
            "He who does not show mercy will not be shown mercy.",
            "Hadis-i Şerif (Buhârî)", "Hadith (Bukhari)"),
        Quote("Namaz, hayâsızlıktan ve kötülükten alıkoyar.",
            "Indeed, prayer prohibits immorality and wrongdoing.",
            "Ankebût Suresi, 45", "Quran, Al-Ankabut 29:45"),
        Quote("Cennet, annelerin ayakları altındadır.",
            "Paradise lies at the feet of mothers.",
            "Hadis-i Şerif (Nesâî)", "Hadith (An-Nasa'i)"),
        Quote("Şükrederseniz elbette size nimetimi artırırım.",
            "If you are grateful, I will surely increase you in favor.",
            "İbrahim Suresi, 7", "Quran, Ibrahim 14:7"),
        Quote("Bir kimse din kardeşinin yardımında olduğu sürece Allah da onun yardımındadır.",
            "Allah helps His servant as long as the servant helps his brother.",
            "Hadis-i Şerif (Müslim)", "Hadith (Muslim)"),
        Quote("Kim zerre kadar hayır işlerse onu görür.",
            "Whoever does an atom's weight of good will see it.",
            "Zilzâl Suresi, 7", "Quran, Az-Zalzalah 99:7"),
        Quote("Allah güzeldir, güzelliği sever.",
            "Allah is beautiful and loves beauty.",
            "Hadis-i Şerif (Müslim)", "Hadith (Muslim)"),
        Quote("Komşusu açken tok yatan bizden değildir.",
            "He is not one of us who sleeps full while his neighbor goes hungry.",
            "Hadis-i Şerif", "Hadith"),
        Quote("İlim öğrenmek her Müslümana farzdır.",
            "Seeking knowledge is an obligation upon every Muslim.",
            "Hadis-i Şerif (İbn Mâce)", "Hadith (Ibn Majah)"),
        Quote("Rabbinizden bağışlanma dileyin; çünkü O çok bağışlayıcıdır.",
            "Seek forgiveness of your Lord. Indeed, He is ever a Perpetual Forgiver.",
            "Nûh Suresi, 10", "Quran, Nuh 71:10")
    )

    fun ofToday(): Quote {
        val doy = java.time.LocalDate.now().dayOfYear
        return list[doy % list.size]
    }
}
