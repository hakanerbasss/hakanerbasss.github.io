package com.wizaicorp.namazvakitleri.data

data class EduStep(
    val emoji: String,
    val titleTr: String,
    val titleEn: String,
    val bodyTr: String,
    val bodyEn: String
) {
    val title: String get() = if (Lang.code == "tr") titleTr else titleEn
    val body: String get() = if (Lang.code == "tr") bodyTr else bodyEn
}

data class EduTopic(
    val id: String,
    val emoji: String,
    val nameTr: String,
    val nameEn: String,
    val introTr: String,
    val introEn: String,
    val steps: List<EduStep>
) {
    val name: String get() = if (Lang.code == "tr") nameTr else nameEn
    val intro: String get() = if (Lang.code == "tr") introTr else introEn
}

/**
 * Namaz egitimi icerigi - Hanefi mezhebi ve Diyanet kaynaklarindaki
 * yaygin anlatima gore hazirlanmistir.
 */
object EducationData {

    val topics = listOf(

        EduTopic(
            "abdest", "💧", "Abdest Nasıl Alınır?", "How to Perform Wudu",
            "Abdestin farzı dörttür: yüzü yıkamak, kolları dirseklerle birlikte yıkamak, başın dörtte birini mesh etmek, ayakları topuklarla birlikte yıkamak.",
            "Wudu has four obligatory acts: washing the face, washing the arms including the elbows, wiping a quarter of the head, and washing the feet including the ankles.",
            listOf(
                EduStep("🤲", "Niyet ve Besmele", "Intention and Basmala",
                    "\"Niyet ettim Allah rızası için abdest almaya\" diye niyet edilir ve Besmele çekilir.",
                    "Make the intention: \"I intend to perform wudu for the sake of Allah\" and say Bismillah."),
                EduStep("👐", "Elleri Yıkama", "Washing the Hands",
                    "Eller bileklere kadar üç kez yıkanır; parmak araları ovulur, varsa yüzük oynatılır.",
                    "Wash the hands up to the wrists three times; rub between the fingers and move any rings."),
                EduStep("💦", "Ağza Su Verme", "Rinsing the Mouth",
                    "Sağ el ile ağza üç kez su verilir. Dişleri fırçalamak veya misvak kullanmak sünnettir.",
                    "Rinse the mouth three times with the right hand. Using a miswak or brushing is sunnah."),
                EduStep("👃", "Buruna Su Verme", "Rinsing the Nose",
                    "Sağ el ile buruna üç kez su çekilir, sol el ile sümkürülür.",
                    "Sniff water into the nose three times with the right hand and blow it out with the left."),
                EduStep("🧼", "Yüzü Yıkama", "Washing the Face",
                    "Alın saç bitiminden çene altına, iki kulak yumuşağı arasına kadar yüz üç kez yıkanır.",
                    "Wash the face three times, from the hairline to below the chin and from ear to ear."),
                EduStep("💪", "Kolları Yıkama", "Washing the Arms",
                    "Önce sağ, sonra sol kol dirsekler dahil üç kez yıkanır.",
                    "Wash the right arm, then the left, including the elbows, three times each."),
                EduStep("✋", "Başı Mesh Etme", "Wiping the Head",
                    "Eller ıslatılır, sağ elin içi ile başın üstü bir kez mesh edilir.",
                    "Wet the hands and wipe over the top of the head once with the wet right palm."),
                EduStep("👂", "Kulak ve Boyun Meshi", "Wiping Ears and Neck",
                    "Şahadet parmaklarıyla kulakların içi, baş parmaklarla arkası; ellerin dışıyla boyun mesh edilir.",
                    "Wipe inside the ears with index fingers, behind with thumbs, and the neck with the back of the hands."),
                EduStep("🦶", "Ayakları Yıkama", "Washing the Feet",
                    "Önce sağ, sonra sol ayak topuklar dahil üç kez yıkanır; parmak araları ovulur. Abdest tamamdır.",
                    "Wash the right foot, then the left, including the ankles, three times; rub between the toes. Wudu is complete."),
                EduStep("⚠️", "Abdesti Bozan Şeyler", "What Invalidates Wudu",
                    "Tuvalet ihtiyacını gidermek, yellenmek, vücuttan kan-irin akması, ağız dolusu kusmak, uyumak, bayılmak ve namazda sesli gülmek abdesti bozar.",
                    "Using the toilet, passing wind, flowing blood or pus, vomiting a mouthful, sleeping, fainting, and laughing aloud in prayer invalidate wudu.")
            )
        ),

        EduTopic(
            "gusul", "🚿", "Gusül (Boy Abdesti)", "Ghusl (Full Ablution)",
            "Guslün farzı üçtür: ağza su vermek, buruna su vermek, bütün vücudu kuru yer kalmayacak şekilde yıkamak.",
            "Ghusl has three obligatory acts: rinsing the mouth, rinsing the nose, and washing the entire body leaving no dry spot.",
            listOf(
                EduStep("🤲", "Niyet ve Hazırlık", "Intention and Preparation",
                    "Besmele çekilir ve gusle niyet edilir. Önce eller, sonra beden temizlenir.",
                    "Say Bismillah and intend to perform ghusl. Wash the hands first, then clean the body."),
                EduStep("💦", "Ağza Bolca Su", "Rinse the Mouth Thoroughly",
                    "Ağza üç kez, boğaza kadar ulaşacak şekilde bolca su verilir.",
                    "Rinse the mouth three times thoroughly, letting the water reach the throat."),
                EduStep("👃", "Buruna Su", "Rinse the Nose",
                    "Buruna üç kez su çekilir; genzin yumuşağına kadar ulaşmalıdır.",
                    "Sniff water into the nose three times so it reaches deep inside."),
                EduStep("🧼", "Namaz Abdesti", "Perform Wudu",
                    "Namaz abdesti gibi abdest alınır.",
                    "Perform wudu as done for prayer."),
                EduStep("🚿", "Bütün Vücudu Yıkama", "Wash the Whole Body",
                    "Önce başa, sonra sağ omuza, sonra sol omuza üçer kez su dökülür; her seferinde vücut ovulur.",
                    "Pour water over the head, then the right shoulder, then the left, three times each, rubbing the body."),
                EduStep("✅", "Kuru Yer Kalmamalı", "No Dry Spot Left",
                    "Göbek çukuru, kulak arkası, saç dipleri dahil iğne ucu kadar kuru yer kalmamalıdır. Gusül tamamdır.",
                    "No spot may remain dry - navel, behind the ears, hair roots. Ghusl is then complete.")
            )
        ),

        EduTopic(
            "teyemmum", "🏜️", "Teyemmüm", "Tayammum",
            "Su bulunmadığında veya kullanılamadığında temiz toprak cinsi bir şeyle alınan abdesttir.",
            "Dry ablution performed with clean earth when water is unavailable or cannot be used.",
            listOf(
                EduStep("🤲", "Niyet", "Intention",
                    "Neye niyet edildiği belirtilir: \"Niyet ettim Allah rızası için teyemmüm almaya.\"",
                    "Make the intention: \"I intend tayammum for the sake of Allah.\""),
                EduStep("🖐️", "Yüz Meshi", "Wiping the Face",
                    "Eller temiz toprağa veya toprak cinsi bir yüzeye vurulur, silkelenir ve yüz mesh edilir.",
                    "Strike clean earth with both palms, shake off the dust and wipe the face."),
                EduStep("💪", "Kolların Meshi", "Wiping the Arms",
                    "Eller ikinci kez toprağa vurulur; önce sağ kol, sonra sol kol dirseklerle birlikte mesh edilir.",
                    "Strike the earth again; wipe the right arm including the elbow, then the left.")
            )
        ),

        EduTopic(
            "namaz_erkek", "🧎", "Namaz Kılınışı (Erkek)", "How Men Pray",
            "İki rekâtlık bir namaz örneği üzerinden adım adım anlatım (Hanefî mezhebine göre).",
            "Step-by-step example of a two-rakah prayer (according to the Hanafi school).",
            listOf(
                EduStep("🕌", "Hazırlık", "Preparation",
                    "Abdestli olarak kıbleye dönülür. Kılınacak namaza kalben niyet edilir: \"Niyet ettim Allah rızası için bugünkü sabah namazının sünnetini kılmaya.\"",
                    "Face the qibla with wudu. Make the intention in your heart for the specific prayer."),
                EduStep("🙌", "İftitah Tekbiri", "Opening Takbir",
                    "Eller, baş parmaklar kulak yumuşağına değecek şekilde kaldırılır ve \"Allahu Ekber\" denir.",
                    "Raise the hands so the thumbs touch the earlobes and say \"Allahu Akbar\"."),
                EduStep("🧍", "Kıyam ve El Bağlama", "Standing (Qiyam)",
                    "Eller göbek altında bağlanır; sağ el sol elin üzerine konur, sağ elin serçe ve baş parmağı sol bileği kavrar. Sübhâneke okunur.",
                    "Fold the hands below the navel, right hand over the left wrist. Recite Subhanaka."),
                EduStep("📖", "Kıraat", "Recitation",
                    "Eûzü-Besmele çekilir, Fâtiha ve ardından bir sure (örneğin İhlâs) okunur.",
                    "Recite Audhu-Bismillah, Al-Fatiha and then a short surah (e.g. Al-Ikhlas)."),
                EduStep("🙇", "Rükû", "Bowing (Ruku)",
                    "\"Allahu Ekber\" diyerek eğilinir; eller parmaklar açık dizleri kavrar, sırt düz olur. Üç kez \"Sübhâne Rabbiyel-azîm\" denir. Doğrulurken \"Semiallâhü limen hamideh\", ardından \"Rabbenâ lekel-hamd\" denir.",
                    "Say \"Allahu Akbar\" and bow; grasp the knees with fingers spread, back straight. Say \"Subhana Rabbiyal-Azim\" three times. Rise saying \"Sami Allahu liman hamidah, Rabbana lakal-hamd\"."),
                EduStep("🧎", "Secde", "Prostration (Sujud)",
                    "\"Allahu Ekber\" ile secdeye gidilir: alın, burun, eller, dizler ve ayak parmakları yere değer; dirsekler yerden ve gövdeden uzak tutulur. Üç kez \"Sübhâne Rabbiyel-a'lâ\" denir. Oturulur, tekrar secde edilir.",
                    "Say \"Allahu Akbar\" and prostrate: forehead, nose, hands, knees and toes touch the ground; elbows kept off the ground and away from the body. Say \"Subhana Rabbiyal-A'la\" three times. Sit briefly, prostrate again."),
                EduStep("🔁", "İkinci Rekât", "Second Rakah",
                    "\"Allahu Ekber\" diyerek ayağa kalkılır. Besmele, Fâtiha ve bir sure okunur; rükû ve iki secde aynı şekilde yapılır.",
                    "Rise saying \"Allahu Akbar\". Recite Bismillah, Al-Fatiha and a surah; perform ruku and two prostrations as before."),
                EduStep("🪑", "Son Oturuş", "Final Sitting",
                    "İkinci secdeden sonra oturulur: sol ayak yere yatırılıp üzerine oturulur, sağ ayak dik tutulur. Ettehiyyâtü, Allâhümme Salli, Allâhümme Bârik ve Rabbenâ duaları okunur.",
                    "Sit after the second prostration: sit on the left foot laid flat, right foot upright. Recite At-Tahiyyat, Allahumma Salli, Allahumma Barik and the Rabbana duas."),
                EduStep("🕊️", "Selam", "Salutation (Salam)",
                    "Önce sağa, sonra sola dönerek \"Esselâmü aleyküm ve rahmetullâh\" denir. Namaz tamamdır.",
                    "Turn the head right then left saying \"As-salamu alaykum wa rahmatullah\". The prayer is complete.")
            )
        ),

        EduTopic(
            "namaz_kadin", "🧕", "Namaz Kılınışı (Kadın)", "How Women Pray",
            "İki rekâtlık bir namaz örneği; kadınların duruşundaki farklar belirtilmiştir (Hanefî mezhebine göre).",
            "Step-by-step two-rakah example noting the differences in women's posture (Hanafi school).",
            listOf(
                EduStep("🕌", "Hazırlık", "Preparation",
                    "Abdestli olarak kıbleye dönülür; el ve yüz dışında beden (saç dahil) örtülü olmalıdır. Kılınacak namaza niyet edilir.",
                    "Face the qibla with wudu; the body including hair must be covered except face and hands. Make the intention."),
                EduStep("🙌", "İftitah Tekbiri", "Opening Takbir",
                    "Eller omuz hizasına kadar kaldırılır ve \"Allahu Ekber\" denir.",
                    "Raise the hands to shoulder level and say \"Allahu Akbar\"."),
                EduStep("🧍", "Kıyam ve El Bağlama", "Standing (Qiyam)",
                    "Eller göğüs üzerinde bağlanır; sağ el sol elin üzerine konur (bilek kavranmaz). Sübhâneke okunur.",
                    "Place the hands on the chest, right over left without grasping the wrist. Recite Subhanaka."),
                EduStep("📖", "Kıraat", "Recitation",
                    "Eûzü-Besmele çekilir, Fâtiha ve bir sure okunur.",
                    "Recite Audhu-Bismillah, Al-Fatiha and a short surah."),
                EduStep("🙇", "Rükû", "Bowing (Ruku)",
                    "\"Allahu Ekber\" ile eğilinir; dizler hafif bükük, eller parmaklar bitişik dizlerin üzerine konur, sırt erkeklere göre daha az eğilir. Üç kez \"Sübhâne Rabbiyel-azîm\" denir.",
                    "Bow saying \"Allahu Akbar\"; knees slightly bent, hands on knees with fingers together, back less inclined than men. Say \"Subhana Rabbiyal-Azim\" three times."),
                EduStep("🧎", "Secde", "Prostration (Sujud)",
                    "Secdede kollar yere yakın tutulur, karın uyluklara bitişik olur; beden derli toplu durur. Üç kez \"Sübhâne Rabbiyel-a'lâ\" denir. Oturulur, tekrar secde edilir.",
                    "In prostration the arms stay close to the ground and the abdomen rests on the thighs; the body kept compact. Say \"Subhana Rabbiyal-A'la\" three times. Sit, then prostrate again."),
                EduStep("🔁", "İkinci Rekât", "Second Rakah",
                    "Ayağa kalkılır; Besmele, Fâtiha ve bir sure okunur, rükû ve iki secde aynı şekilde yapılır.",
                    "Rise; recite Bismillah, Al-Fatiha and a surah, then ruku and two prostrations as before."),
                EduStep("🪑", "Son Oturuş", "Final Sitting",
                    "Kalça sola verilerek oturulur, ayaklar sağ taraftan çıkarılır. Ettehiyyâtü, Salli-Bârik ve Rabbenâ duaları okunur.",
                    "Sit shifting onto the left hip with both feet to the right side. Recite At-Tahiyyat, Salli-Barik and the Rabbana duas."),
                EduStep("🕊️", "Selam", "Salutation (Salam)",
                    "Önce sağa, sonra sola \"Esselâmü aleyküm ve rahmetullâh\" denir. Namaz tamamdır.",
                    "Turn right then left saying \"As-salamu alaykum wa rahmatullah\". The prayer is complete.")
            )
        ),

        EduTopic(
            "rekatlar", "🔢", "Rekât Tablosu", "Rakah Table",
            "Beş vakit namazın ve cuma namazının rekât sayıları.",
            "Number of rakahs for the five daily prayers and Friday prayer.",
            listOf(
                EduStep("🌅", "Sabah (2+2)", "Fajr (2+2)",
                    "2 rekât sünnet + 2 rekât farz. Toplam 4 rekât.",
                    "2 sunnah + 2 fard. Total 4 rakahs."),
                EduStep("☀️", "Öğle (4+4+2)", "Dhuhr (4+4+2)",
                    "4 rekât ilk sünnet + 4 rekât farz + 2 rekât son sünnet. Toplam 10 rekât.",
                    "4 first sunnah + 4 fard + 2 last sunnah. Total 10 rakahs."),
                EduStep("🌤️", "İkindi (4+4)", "Asr (4+4)",
                    "4 rekât sünnet (gayr-i müekkede) + 4 rekât farz. Toplam 8 rekât.",
                    "4 sunnah (non-emphasized) + 4 fard. Total 8 rakahs."),
                EduStep("🌇", "Akşam (3+2)", "Maghrib (3+2)",
                    "3 rekât farz + 2 rekât sünnet. Toplam 5 rekât.",
                    "3 fard + 2 sunnah. Total 5 rakahs."),
                EduStep("🌙", "Yatsı (4+4+2+3)", "Isha (4+4+2+3)",
                    "4 rekât ilk sünnet + 4 rekât farz + 2 rekât son sünnet + 3 rekât vitir. Toplam 13 rekât.",
                    "4 first sunnah + 4 fard + 2 last sunnah + 3 witr. Total 13 rakahs."),
                EduStep("🕌", "Cuma", "Jumu'ah (Friday)",
                    "4 rekât ilk sünnet + 2 rekât farz (cemaatle) + 4 rekât son sünnet. Öğle namazının yerine kılınır.",
                    "4 first sunnah + 2 fard (in congregation) + 4 last sunnah. It replaces Dhuhr prayer.")
            )
        ),

        EduTopic(
            "sartlar", "📋", "Namazın Şartları ve Rükünleri", "Conditions and Pillars of Prayer",
            "Namazın dışındaki altı şart ve içindeki altı rükün.",
            "The six external conditions and six internal pillars of prayer.",
            listOf(
                EduStep("1️⃣", "Hadesten Taharet", "Purity from Impurity",
                    "Abdestsizlik veya gusül gerektiren durumdan temizlenmek.",
                    "Being purified through wudu or ghusl."),
                EduStep("2️⃣", "Necasetten Taharet", "Cleanliness",
                    "Beden, elbise ve namaz kılınacak yerin temiz olması.",
                    "Body, clothes and prayer place must be clean."),
                EduStep("3️⃣", "Setr-i Avret", "Covering the Body",
                    "Örtülmesi gereken yerlerin örtülmesi.",
                    "Covering the parts of the body that must be covered."),
                EduStep("4️⃣", "İstikbâl-i Kıble", "Facing the Qibla",
                    "Kâbe yönüne dönmek.",
                    "Facing the direction of the Kaaba."),
                EduStep("5️⃣", "Vakit", "Time",
                    "Namazı kendi vakti içinde kılmak.",
                    "Praying within the prescribed time."),
                EduStep("6️⃣", "Niyet", "Intention",
                    "Hangi namazın kılındığını kalben bilmek.",
                    "Knowing in the heart which prayer is being performed."),
                EduStep("🕋", "Rükünler", "The Pillars",
                    "Namazın içindeki rükünler: iftitah tekbiri, kıyam, kıraat, rükû, secde ve son oturuş (ka'de-i ahîre).",
                    "The pillars within prayer: opening takbir, standing, recitation, bowing, prostration and the final sitting.")
            )
        ),

        EduTopic(
            "bozanlar", "🚫", "Namazı Bozan Şeyler", "What Invalidates Prayer",
            "Namaz sırasında yapıldığında namazı geçersiz kılan durumlar.",
            "Actions that invalidate the prayer when done during it.",
            listOf(
                EduStep("🗣️", "Konuşmak", "Speaking",
                    "Namazda bilerek veya yanılarak konuşmak namazı bozar.",
                    "Speaking during prayer, deliberately or by mistake, invalidates it."),
                EduStep("😄", "Gülmek", "Laughing",
                    "Sesli gülmek namazı bozar; yakındakinin duyacağı kadar gülmek abdesti de bozar.",
                    "Laughing aloud invalidates prayer; audible laughter also invalidates wudu."),
                EduStep("🍽️", "Yemek-İçmek", "Eating or Drinking",
                    "Namazda bir şey yemek veya içmek namazı bozar.",
                    "Eating or drinking anything during prayer invalidates it."),
                EduStep("🧭", "Kıbleden Dönmek", "Turning from the Qibla",
                    "Göğsü kıble yönünden çevirmek namazı bozar.",
                    "Turning the chest away from the qibla invalidates prayer."),
                EduStep("🏃", "Amel-i Kesîr", "Excessive Movement",
                    "Namazla ilgisi olmayan, dışarıdan bakanın 'namazda değil' diyeceği kadar çok hareket namazı bozar.",
                    "Excessive movement unrelated to prayer, enough that an onlooker would think one is not praying."),
                EduStep("💧", "Abdestin Bozulması", "Losing Wudu",
                    "Namaz içinde abdestin bozulması namazı da bozar.",
                    "Losing wudu during prayer invalidates the prayer."),
                EduStep("📿", "Not", "Note",
                    "Bu anlatım Hanefî mezhebine ve Diyanet kaynaklarına göredir; ayrıntılar için ilmihale veya müftülüğe başvurunuz.",
                    "This guide follows the Hanafi school and Diyanet sources; consult a scholar for details.")
            )
        )
    )
}
