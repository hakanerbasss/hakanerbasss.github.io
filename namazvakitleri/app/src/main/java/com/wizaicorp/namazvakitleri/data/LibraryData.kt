package com.wizaicorp.namazvakitleri.data

data class Verse(
    val arabic: String,
    val reading: String,
    val meaningTr: String,
    val meaningEn: String
) {
    val meaning: String get() = if (Lang.code == "tr") meaningTr else meaningEn
}

data class LibraryItem(
    val id: String,
    val nameTr: String,
    val nameEn: String,
    val nameAr: String,
    val infoTr: String,
    val infoEn: String,
    val verses: List<Verse>
) {
    val name: String get() = if (Lang.code == "tr") nameTr else nameEn
    val info: String get() = if (Lang.code == "tr") infoTr else infoEn
}

/**
 * Namaz sureleri ve dualari - Arapca, Turkce okunus, TR/EN meal.
 * Metinler yaygin Diyanet okunus/meal gelenegine gore kisaltilarak yazilmistir.
 */
object LibraryData {

    private val besmele = Verse(
        "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
        "Bismillâhirrahmânirrahîm",
        "Rahmân ve Rahîm olan Allah'ın adıyla",
        "In the name of Allah, the Most Compassionate, the Most Merciful"
    )

    val sureler = listOf(
        LibraryItem(
            "fatiha", "Fâtiha Suresi", "Surah Al-Fatiha", "الفاتحة",
            "Kur'an'ın ilk suresi; her namazın her rekâtında okunur.",
            "The opening chapter, recited in every unit of prayer.",
            listOf(
                besmele,
                Verse("الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ",
                    "Elhamdü lillâhi rabbil âlemîn",
                    "Hamd, âlemlerin Rabbi Allah'a mahsustur.",
                    "All praise is for Allah, Lord of all worlds."),
                Verse("الرَّحْمَٰنِ الرَّحِيمِ",
                    "Errahmânirrahîm",
                    "O, Rahmân'dır, Rahîm'dir.",
                    "The Most Compassionate, the Most Merciful."),
                Verse("مَالِكِ يَوْمِ الدِّينِ",
                    "Mâliki yevmiddîn",
                    "Hesap gününün sahibidir.",
                    "Master of the Day of Judgment."),
                Verse("إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ",
                    "İyyâke na'büdü ve iyyâke neste'în",
                    "Yalnız sana kulluk eder, yalnız senden yardım dileriz.",
                    "You alone we worship, and You alone we ask for help."),
                Verse("اهْدِنَا الصِّرَاطَ الْمُسْتَقِيمَ",
                    "İhdinessırâtal müstakîm",
                    "Bizi dosdoğru yola ilet.",
                    "Guide us along the Straight Path."),
                Verse("صِرَاطَ الَّذِينَ أَنْعَمْتَ عَلَيْهِمْ غَيْرِ الْمَغْضُوبِ عَلَيْهِمْ وَلَا الضَّالِّينَ",
                    "Sırâtallezîne en'amte aleyhim gayril mağdûbi aleyhim veleddâllîn",
                    "Nimet verdiklerinin yoluna; gazaba uğrayanların ve sapanların yoluna değil.",
                    "The path of those You have blessed, not of those who earned Your anger or went astray.")
            )
        ),
        LibraryItem(
            "ayetel_kursi", "Âyetel Kürsî", "Ayat al-Kursi", "آية الكرسي",
            "Bakara Suresi 255. ayet; namazlardan sonra okunması faziletlidir.",
            "Verse 255 of Surah Al-Baqarah; virtuous to recite after prayers.",
            listOf(
                Verse("اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ",
                    "Allâhü lâ ilâhe illâ hüvel hayyül kayyûm",
                    "Allah, kendisinden başka ilah olmayandır; diridir, her şeyi ayakta tutandır.",
                    "Allah! There is no god but Him, the Ever-Living, the Sustainer of all."),
                Verse("لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ ۚ لَهُ مَا فِي السَّمَاوَاتِ وَمَا فِي الْأَرْضِ",
                    "Lâ te'huzühû sinetün velâ nevm, lehû mâ fissemâvâti ve mâ fil ard",
                    "O'nu ne uyuklama tutar ne de uyku. Göklerdekiler ve yerdekiler O'nundur.",
                    "Neither drowsiness nor sleep overtakes Him. To Him belongs all in the heavens and the earth."),
                Verse("مَنْ ذَا الَّذِي يَشْفَعُ عِنْدَهُ إِلَّا بِإِذْنِهِ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ",
                    "Men zellezî yeşfeu indehû illâ biiznih, ya'lemü mâ beyne eydîhim ve mâ halfehüm",
                    "İzni olmadan O'nun katında kim şefaat edebilir? Onların önlerindekini ve arkalarındakini bilir.",
                    "Who can intercede with Him except by His permission? He knows what is before them and behind them."),
                Verse("وَلَا يُحِيطُونَ بِشَيْءٍ مِنْ عِلْمِهِ إِلَّا بِمَا شَاءَ ۚ وَسِعَ كُرْسِيُّهُ السَّمَاوَاتِ وَالْأَرْضَ",
                    "Velâ yühîtûne bişey'in min ilmihî illâ bimâ şâe, vesia kürsiyyühüssemâvâti vel ard",
                    "Onlar O'nun ilminden, dilediği kadarından başkasını kavrayamazlar. Kürsüsü gökleri ve yeri kaplamıştır.",
                    "They encompass nothing of His knowledge except what He wills. His Seat extends over the heavens and the earth."),
                Verse("وَلَا يَئُودُهُ حِفْظُهُمَا ۚ وَهُوَ الْعَلِيُّ الْعَظِيمُ",
                    "Velâ yeûdühû hıfzuhümâ ve hüvel aliyyül azîm",
                    "Onları korumak O'na ağır gelmez. O, yücedir, büyüktür.",
                    "Preserving both does not tire Him. He is the Most High, the Most Great.")
            )
        ),
        LibraryItem(
            "fil", "Fîl Suresi", "Surah Al-Fil", "الفيل",
            "105. sure; fil ordusunun helâkını anlatır.",
            "Chapter 105; recounts the destruction of the army of the elephant.",
            listOf(
                besmele,
                Verse("أَلَمْ تَرَ كَيْفَ فَعَلَ رَبُّكَ بِأَصْحَابِ الْفِيلِ",
                    "Elem tera keyfe feale rabbüke biashâbil fîl",
                    "Rabbinin fil sahiplerine ne yaptığını görmedin mi?",
                    "Have you not seen how your Lord dealt with the army of the elephant?"),
                Verse("أَلَمْ يَجْعَلْ كَيْدَهُمْ فِي تَضْلِيلٍ",
                    "Elem yec'al keydehüm fî tadlîl",
                    "Onların tuzaklarını boşa çıkarmadı mı?",
                    "Did He not make their plan go astray?"),
                Verse("وَأَرْسَلَ عَلَيْهِمْ طَيْرًا أَبَابِيلَ",
                    "Ve ersele aleyhim tayran ebâbîl",
                    "Üzerlerine sürü sürü kuşlar gönderdi.",
                    "And He sent against them flocks of birds,"),
                Verse("تَرْمِيهِمْ بِحِجَارَةٍ مِنْ سِجِّيلٍ",
                    "Termîhim bihicâratin min siccîl",
                    "Onlara pişkin tuğladan taşlar atıyorlardı.",
                    "striking them with stones of baked clay,"),
                Verse("فَجَعَلَهُمْ كَعَصْفٍ مَأْكُولٍ",
                    "Fecealehüm keasfin me'kûl",
                    "Sonunda onları yenilmiş ekin yaprağı gibi yaptı.",
                    "so He made them like chewed-up straw.")
            )
        ),
        LibraryItem(
            "kureys", "Kureyş Suresi", "Surah Quraysh", "قريش",
            "106. sure; Kureyş'e verilen nimetleri hatırlatır.",
            "Chapter 106; reminds Quraysh of Allah's favors.",
            listOf(
                besmele,
                Verse("لِإِيلَافِ قُرَيْشٍ",
                    "Li îlâfi kurayş",
                    "Kureyş'i alıştırdığı için,",
                    "For the security of Quraysh,"),
                Verse("إِيلَافِهِمْ رِحْلَةَ الشِّتَاءِ وَالصَّيْفِ",
                    "Îlâfihim rıhleteşşitâi vessayf",
                    "onları kış ve yaz yolculuklarına alıştırdığı için,",
                    "their security in winter and summer journeys,"),
                Verse("فَلْيَعْبُدُوا رَبَّ هَٰذَا الْبَيْتِ",
                    "Felya'büdû rabbe hâzel beyt",
                    "bu evin (Kâbe'nin) Rabbine kulluk etsinler.",
                    "let them worship the Lord of this House,"),
                Verse("الَّذِي أَطْعَمَهُمْ مِنْ جُوعٍ وَآمَنَهُمْ مِنْ خَوْفٍ",
                    "Ellezî at'amehüm min cû'in ve âmenehüm min havf",
                    "O, onları açlıktan doyurdu ve korkudan emin kıldı.",
                    "who fed them against hunger and secured them from fear.")
            )
        ),
        LibraryItem(
            "maun", "Mâûn Suresi", "Surah Al-Ma'un", "الماعون",
            "107. sure; yardımlaşmayı ve namazda samimiyeti öğütler.",
            "Chapter 107; teaches sincerity in prayer and helping others.",
            listOf(
                besmele,
                Verse("أَرَأَيْتَ الَّذِي يُكَذِّبُ بِالدِّينِ",
                    "Eraeytellezî yükezzibü biddîn",
                    "Dini yalanlayanı gördün mü?",
                    "Have you seen the one who denies the Judgment?"),
                Verse("فَذَٰلِكَ الَّذِي يَدُعُّ الْيَتِيمَ",
                    "Fezâlikellezî yedu'ul yetîm",
                    "İşte o, yetimi itip kakar,",
                    "That is the one who repulses the orphan,"),
                Verse("وَلَا يَحُضُّ عَلَىٰ طَعَامِ الْمِسْكِينِ",
                    "Velâ yehuddu alâ taâmil miskîn",
                    "yoksulu doyurmaya teşvik etmez.",
                    "and does not encourage feeding the poor."),
                Verse("فَوَيْلٌ لِلْمُصَلِّينَ",
                    "Feveylün lil musallîn",
                    "Vay o namaz kılanların haline ki,",
                    "So woe to those who pray"),
                Verse("الَّذِينَ هُمْ عَنْ صَلَاتِهِمْ سَاهُونَ",
                    "Ellezîne hüm an salâtihim sâhûn",
                    "onlar namazlarından gafildirler,",
                    "but are heedless of their prayer,"),
                Verse("الَّذِينَ هُمْ يُرَاءُونَ",
                    "Ellezîne hüm yürâûn",
                    "onlar gösteriş yaparlar,",
                    "those who only show off,"),
                Verse("وَيَمْنَعُونَ الْمَاعُونَ",
                    "Ve yemneûnel mâûn",
                    "ve en küçük yardımı bile esirgerler.",
                    "and withhold simple assistance.")
            )
        ),
        LibraryItem(
            "kevser", "Kevser Suresi", "Surah Al-Kawthar", "الكوثر",
            "108. sure; Kur'an'ın en kısa suresidir.",
            "Chapter 108; the shortest chapter of the Quran.",
            listOf(
                besmele,
                Verse("إِنَّا أَعْطَيْنَاكَ الْكَوْثَرَ",
                    "İnnâ a'taynâkel kevser",
                    "Şüphesiz biz sana Kevser'i verdik.",
                    "Indeed, We have granted you Al-Kawthar."),
                Verse("فَصَلِّ لِرَبِّكَ وَانْحَرْ",
                    "Fesalli lirabbike venhar",
                    "O halde Rabbin için namaz kıl ve kurban kes.",
                    "So pray to your Lord and sacrifice."),
                Verse("إِنَّ شَانِئَكَ هُوَ الْأَبْتَرُ",
                    "İnne şânieke hüvel ebter",
                    "Asıl soyu kesik olan, sana buğzedendir.",
                    "Indeed, your enemy is the one cut off.")
            )
        ),
        LibraryItem(
            "kafirun", "Kâfirûn Suresi", "Surah Al-Kafirun", "الكافرون",
            "109. sure; inançta tavizsizliği bildirir.",
            "Chapter 109; declares firmness in faith.",
            listOf(
                besmele,
                Verse("قُلْ يَا أَيُّهَا الْكَافِرُونَ",
                    "Kul yâ eyyühel kâfirûn",
                    "De ki: Ey kâfirler!",
                    "Say: O disbelievers!"),
                Verse("لَا أَعْبُدُ مَا تَعْبُدُونَ",
                    "Lâ a'büdü mâ ta'büdûn",
                    "Ben sizin taptıklarınıza tapmam.",
                    "I do not worship what you worship,"),
                Verse("وَلَا أَنْتُمْ عَابِدُونَ مَا أَعْبُدُ",
                    "Velâ entüm âbidûne mâ a'büd",
                    "Siz de benim taptığıma tapmazsınız.",
                    "nor do you worship what I worship."),
                Verse("وَلَا أَنَا عَابِدٌ مَا عَبَدْتُمْ",
                    "Velâ ene âbidün mâ abedtüm",
                    "Ben sizin taptıklarınıza tapacak değilim.",
                    "I will never worship what you worship,"),
                Verse("وَلَا أَنْتُمْ عَابِدُونَ مَا أَعْبُدُ",
                    "Velâ entüm âbidûne mâ a'büd",
                    "Siz de benim taptığıma tapacak değilsiniz.",
                    "nor will you ever worship what I worship."),
                Verse("لَكُمْ دِينُكُمْ وَلِيَ دِينِ",
                    "Leküm dînüküm veliye dîn",
                    "Sizin dininiz size, benim dinim banadır.",
                    "You have your religion, and I have mine.")
            )
        ),
        LibraryItem(
            "nasr", "Nasr Suresi", "Surah An-Nasr", "النصر",
            "110. sure; yardım ve fetih müjdesini içerir.",
            "Chapter 110; the good news of help and victory.",
            listOf(
                besmele,
                Verse("إِذَا جَاءَ نَصْرُ اللَّهِ وَالْفَتْحُ",
                    "İzâ câe nasrullâhi velfeth",
                    "Allah'ın yardımı ve fetih geldiğinde,",
                    "When Allah's help and the victory come,"),
                Verse("وَرَأَيْتَ النَّاسَ يَدْخُلُونَ فِي دِينِ اللَّهِ أَفْوَاجًا",
                    "Veraeytennâse yedhulûne fî dînillâhi efvâcâ",
                    "ve insanların akın akın Allah'ın dinine girdiğini gördüğünde,",
                    "and you see people entering Allah's religion in crowds,"),
                Verse("فَسَبِّحْ بِحَمْدِ رَبِّكَ وَاسْتَغْفِرْهُ ۚ إِنَّهُ كَانَ تَوَّابًا",
                    "Fesebbih bihamdi rabbike vestağfirh, innehû kâne tevvâbâ",
                    "Rabbini hamd ile tesbih et ve O'ndan bağışlanma dile. Çünkü O, tövbeleri çok kabul edendir.",
                    "then glorify the praises of your Lord and seek His forgiveness. He is ever Accepting of repentance.")
            )
        ),
        LibraryItem(
            "tebbet", "Tebbet Suresi", "Surah Al-Masad", "المسد",
            "111. sure; Ebû Leheb'in akıbetini bildirir.",
            "Chapter 111; on the fate of Abu Lahab.",
            listOf(
                besmele,
                Verse("تَبَّتْ يَدَا أَبِي لَهَبٍ وَتَبَّ",
                    "Tebbet yedâ ebî lehebin ve tebb",
                    "Ebû Leheb'in iki eli kurusun, kurudu da.",
                    "May the hands of Abu Lahab perish, and he is ruined."),
                Verse("مَا أَغْنَىٰ عَنْهُ مَالُهُ وَمَا كَسَبَ",
                    "Mâ ağnâ anhü mâlühû ve mâ keseb",
                    "Malı ve kazandıkları ona fayda vermedi.",
                    "His wealth and gains will not benefit him."),
                Verse("سَيَصْلَىٰ نَارًا ذَاتَ لَهَبٍ",
                    "Seyaslâ nâran zâte leheb",
                    "O, alevli bir ateşe girecektir.",
                    "He will burn in a flaming Fire,"),
                Verse("وَامْرَأَتُهُ حَمَّالَةَ الْحَطَبِ",
                    "Vemraetühû hammâletel hatab",
                    "Odun taşıyıcısı olarak karısı da.",
                    "and so will his wife, the carrier of firewood,"),
                Verse("فِي جِيدِهَا حَبْلٌ مِنْ مَسَدٍ",
                    "Fî cîdihâ hablün min mesed",
                    "Boynunda hurma lifinden bir ip olduğu halde.",
                    "around her neck a rope of palm fiber.")
            )
        ),
        LibraryItem(
            "ihlas", "İhlâs Suresi", "Surah Al-Ikhlas", "الإخلاص",
            "112. sure; tevhidin özüdür.",
            "Chapter 112; the essence of monotheism.",
            listOf(
                besmele,
                Verse("قُلْ هُوَ اللَّهُ أَحَدٌ",
                    "Kul hüvellâhü ehad",
                    "De ki: O, Allah'tır, tektir.",
                    "Say: He is Allah, the One."),
                Verse("اللَّهُ الصَّمَدُ",
                    "Allâhüssamed",
                    "Allah Samed'dir (hiçbir şeye muhtaç değildir).",
                    "Allah, the Eternal, the Absolute."),
                Verse("لَمْ يَلِدْ وَلَمْ يُولَدْ",
                    "Lem yelid velem yûled",
                    "Doğurmamıştır ve doğmamıştır.",
                    "He begets not, nor was He begotten."),
                Verse("وَلَمْ يَكُنْ لَهُ كُفُوًا أَحَدٌ",
                    "Velem yekün lehû küfüven ehad",
                    "Hiçbir şey O'na denk değildir.",
                    "And there is none comparable to Him.")
            )
        ),
        LibraryItem(
            "felak", "Felak Suresi", "Surah Al-Falaq", "الفلق",
            "113. sure; şerlerden Allah'a sığınmayı öğretir.",
            "Chapter 113; seeking refuge in Allah from evil.",
            listOf(
                besmele,
                Verse("قُلْ أَعُوذُ بِرَبِّ الْفَلَقِ",
                    "Kul eûzü birabbil felak",
                    "De ki: Sabahın Rabbine sığınırım,",
                    "Say: I seek refuge in the Lord of daybreak,"),
                Verse("مِنْ شَرِّ مَا خَلَقَ",
                    "Min şerri mâ halak",
                    "yarattığı şeylerin şerrinden,",
                    "from the evil of what He has created,"),
                Verse("وَمِنْ شَرِّ غَاسِقٍ إِذَا وَقَبَ",
                    "Ve min şerri gâsikın izâ vekab",
                    "karanlığı çöktüğünde gecenin şerrinden,",
                    "from the evil of darkness when it settles,"),
                Verse("وَمِنْ شَرِّ النَّفَّاثَاتِ فِي الْعُقَدِ",
                    "Ve min şerrinneffâsâti fil ukad",
                    "düğümlere üfleyenlerin şerrinden,",
                    "from the evil of those who blow on knots,"),
                Verse("وَمِنْ شَرِّ حَاسِدٍ إِذَا حَسَدَ",
                    "Ve min şerri hâsidin izâ hased",
                    "ve haset ettiğinde hasetçinin şerrinden.",
                    "and from the evil of the envier when he envies.")
            )
        ),
        LibraryItem(
            "nas", "Nâs Suresi", "Surah An-Nas", "الناس",
            "114. ve son sure; vesveseden Allah'a sığınmayı öğretir.",
            "Chapter 114, the last chapter; refuge from whispering evil.",
            listOf(
                besmele,
                Verse("قُلْ أَعُوذُ بِرَبِّ النَّاسِ",
                    "Kul eûzü birabbinnâs",
                    "De ki: İnsanların Rabbine sığınırım,",
                    "Say: I seek refuge in the Lord of mankind,"),
                Verse("مَلِكِ النَّاسِ",
                    "Melikinnâs",
                    "insanların Melik'ine (hükümdarına),",
                    "the King of mankind,"),
                Verse("إِلَٰهِ النَّاسِ",
                    "İlâhinnâs",
                    "insanların İlâh'ına,",
                    "the God of mankind,"),
                Verse("مِنْ شَرِّ الْوَسْوَاسِ الْخَنَّاسِ",
                    "Min şerril vesvâsil hannâs",
                    "sinsi vesvesecinin şerrinden,",
                    "from the evil of the retreating whisperer,"),
                Verse("الَّذِي يُوَسْوِسُ فِي صُدُورِ النَّاسِ",
                    "Ellezî yüvesvisü fî sudûrinnâs",
                    "o ki insanların göğüslerine vesvese verir,",
                    "who whispers into the hearts of mankind,"),
                Verse("مِنَ الْجِنَّةِ وَالنَّاسِ",
                    "Minel cinneti vennâs",
                    "cinlerden ve insanlardan.",
                    "from among jinn and mankind.")
            )
        )
    )

    val dualar = listOf(
        LibraryItem(
            "subhaneke", "Sübhâneke", "Subhanaka", "سبحانك",
            "Namaza başlarken okunur.",
            "Recited at the beginning of prayer.",
            listOf(
                Verse("سُبْحَانَكَ اللَّهُمَّ وَبِحَمْدِكَ",
                    "Sübhânekellâhümme ve bihamdik",
                    "Allah'ım! Sen eksik sıfatlardan uzaksın, seni hamdinle tesbih ederim.",
                    "Glory be to You, O Allah, and all praise is Yours."),
                Verse("وَتَبَارَكَ اسْمُكَ وَتَعَالَى جَدُّكَ",
                    "Ve tebârakesmük ve teâlâ ceddük",
                    "Senin adın mübarektir, şanın yücedir.",
                    "Blessed is Your name and exalted is Your majesty."),
                Verse("وَلَا إِلَهَ غَيْرُكَ",
                    "Ve lâ ilâhe gayrük",
                    "Senden başka ilah yoktur.",
                    "There is no god but You.")
            )
        ),
        LibraryItem(
            "ettehiyyatu", "Ettehiyyâtü", "At-Tahiyyat", "التحيات",
            "Namazların oturuşlarında okunur.",
            "Recited while sitting in prayer.",
            listOf(
                Verse("التَّحِيَّاتُ لِلَّهِ وَالصَّلَوَاتُ وَالطَّيِّبَاتُ",
                    "Ettehiyyâtü lillâhi vessalevâtü vettayyibât",
                    "Bütün övgüler, dualar ve güzellikler Allah'adır.",
                    "All greetings, prayers and good things belong to Allah."),
                Verse("السَّلَامُ عَلَيْكَ أَيُّهَا النَّبِيُّ وَرَحْمَةُ اللَّهِ وَبَرَكَاتُهُ",
                    "Esselâmü aleyke eyyühennebiyyü ve rahmetullâhi ve berakâtüh",
                    "Ey Peygamber! Selam, Allah'ın rahmeti ve bereketi senin üzerine olsun.",
                    "Peace be upon you, O Prophet, and Allah's mercy and blessings."),
                Verse("السَّلَامُ عَلَيْنَا وَعَلَى عِبَادِ اللَّهِ الصَّالِحِينَ",
                    "Esselâmü aleynâ ve alâ ibâdillâhissâlihîn",
                    "Selam bizim ve Allah'ın salih kullarının üzerine olsun.",
                    "Peace be upon us and upon Allah's righteous servants."),
                Verse("أَشْهَدُ أَنْ لَا إِلَهَ إِلَّا اللَّهُ وَأَشْهَدُ أَنَّ مُحَمَّدًا عَبْدُهُ وَرَسُولُهُ",
                    "Eşhedü en lâ ilâhe illallâh ve eşhedü enne Muhammeden abdühû ve rasûlüh",
                    "Şahitlik ederim ki Allah'tan başka ilah yoktur; yine şahitlik ederim ki Muhammed O'nun kulu ve elçisidir.",
                    "I bear witness that there is no god but Allah, and that Muhammad is His servant and messenger.")
            )
        ),
        LibraryItem(
            "salli", "Allâhümme Salli", "Allahumma Salli", "اللهم صل",
            "Son oturuşta Ettehiyyâtü'den sonra okunur.",
            "Recited after At-Tahiyyat in the final sitting.",
            listOf(
                Verse("اللَّهُمَّ صَلِّ عَلَى مُحَمَّدٍ وَعَلَى آلِ مُحَمَّدٍ",
                    "Allâhümme salli alâ Muhammedin ve alâ âli Muhammed",
                    "Allah'ım! Muhammed'e ve Muhammed'in ailesine rahmet et.",
                    "O Allah, send blessings upon Muhammad and his family,"),
                Verse("كَمَا صَلَّيْتَ عَلَى إِبْرَاهِيمَ وَعَلَى آلِ إِبْرَاهِيمَ",
                    "Kemâ salleyte alâ İbrâhîme ve alâ âli İbrâhîm",
                    "İbrahim'e ve ailesine rahmet ettiğin gibi.",
                    "as You blessed Ibrahim and his family."),
                Verse("إِنَّكَ حَمِيدٌ مَجِيدٌ",
                    "İnneke hamîdün mecîd",
                    "Şüphesiz sen övülmeye layıksın, şanı yüce olansın.",
                    "Indeed, You are Praiseworthy, Most Glorious.")
            )
        ),
        LibraryItem(
            "barik", "Allâhümme Bârik", "Allahumma Barik", "اللهم بارك",
            "Allâhümme Salli'den sonra okunur.",
            "Recited after Allahumma Salli.",
            listOf(
                Verse("اللَّهُمَّ بَارِكْ عَلَى مُحَمَّدٍ وَعَلَى آلِ مُحَمَّدٍ",
                    "Allâhümme bârik alâ Muhammedin ve alâ âli Muhammed",
                    "Allah'ım! Muhammed'e ve Muhammed'in ailesine bereket ver.",
                    "O Allah, bless Muhammad and the family of Muhammad,"),
                Verse("كَمَا بَارَكْتَ عَلَى إِبْرَاهِيمَ وَعَلَى آلِ إِبْرَاهِيمَ",
                    "Kemâ bârekte alâ İbrâhîme ve alâ âli İbrâhîm",
                    "İbrahim'e ve ailesine bereket verdiğin gibi.",
                    "as You blessed Ibrahim and his family."),
                Verse("إِنَّكَ حَمِيدٌ مَجِيدٌ",
                    "İnneke hamîdün mecîd",
                    "Şüphesiz sen övülmeye layıksın, şanı yüce olansın.",
                    "Indeed, You are Praiseworthy, Most Glorious.")
            )
        ),
        LibraryItem(
            "rabbena_atina", "Rabbenâ Âtinâ", "Rabbana Atina", "ربنا آتنا",
            "Son oturuşta okunur (Bakara 201).",
            "Recited in the final sitting (Al-Baqarah 201).",
            listOf(
                Verse("رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ",
                    "Rabbenâ âtinâ fiddünyâ haseneten ve fil âhirati haseneten ve kınâ azâbennâr",
                    "Rabbimiz! Bize dünyada da iyilik ver, ahirette de iyilik ver; bizi ateşin azabından koru.",
                    "Our Lord! Grant us good in this world and good in the Hereafter, and protect us from the punishment of the Fire.")
            )
        ),
        LibraryItem(
            "rabbenagfirli", "Rabbenâğfirlî", "Rabbanaghfirli", "ربنا اغفر لي",
            "Rabbenâ Âtinâ'dan sonra okunur (İbrahim 41).",
            "Recited after Rabbana Atina (Ibrahim 41).",
            listOf(
                Verse("رَبَّنَا اغْفِرْ لِي وَلِوَالِدَيَّ وَلِلْمُؤْمِنِينَ يَوْمَ يَقُومُ الْحِسَابُ",
                    "Rabbenâğfirlî ve livâlideyye ve lil mü'minîne yevme yekûmül hisâb",
                    "Rabbimiz! Hesabın görüleceği gün beni, anne babamı ve müminleri bağışla.",
                    "Our Lord! Forgive me, my parents and the believers on the Day the reckoning takes place.")
            )
        ),
        LibraryItem(
            "kunut1", "Kunut Duası 1", "Qunut Dua 1", "دعاء القنوت ١",
            "Vitir namazının üçüncü rekâtında okunur.",
            "Recited in the third unit of Witr prayer.",
            listOf(
                Verse("اللَّهُمَّ إِنَّا نَسْتَعِينُكَ وَنَسْتَغْفِرُكَ وَنَسْتَهْدِيكَ",
                    "Allâhümme innâ nesteînüke ve nestağfirüke ve nestehdîk",
                    "Allah'ım! Senden yardım isteriz, bağışlanma dileriz, hidayet isteriz.",
                    "O Allah, we seek Your help, Your forgiveness and Your guidance."),
                Verse("وَنُؤْمِنُ بِكَ وَنَتُوبُ إِلَيْكَ وَنَتَوَكَّلُ عَلَيْكَ",
                    "Ve nü'minü bike ve netûbü ileyk ve netevekkelü aleyk",
                    "Sana inanırız, sana tövbe ederiz, sana güveniriz.",
                    "We believe in You, repent to You and rely on You."),
                Verse("وَنُثْنِي عَلَيْكَ الْخَيْرَ كُلَّهُ نَشْكُرُكَ وَلَا نَكْفُرُكَ",
                    "Ve nüsnî aleykel hayra küllehû neşkürüke velâ nekfürük",
                    "Bütün hayırlarla seni överiz, sana şükrederiz, nankörlük etmeyiz.",
                    "We praise You for all good; we thank You and are not ungrateful."),
                Verse("وَنَخْلَعُ وَنَتْرُكُ مَنْ يَفْجُرُكَ",
                    "Ve nahleu ve netrükü men yefcürük",
                    "Sana isyan edeni bırakır, ondan uzaklaşırız.",
                    "And we abandon and forsake those who disobey You.")
            )
        ),
        LibraryItem(
            "kunut2", "Kunut Duası 2", "Qunut Dua 2", "دعاء القنوت ٢",
            "Kunut 1'den sonra okunur.",
            "Recited after Qunut Dua 1.",
            listOf(
                Verse("اللَّهُمَّ إِيَّاكَ نَعْبُدُ وَلَكَ نُصَلِّي وَنَسْجُدُ",
                    "Allâhümme iyyâke na'büdü ve leke nüsallî ve nescüd",
                    "Allah'ım! Yalnız sana kulluk ederiz, senin için namaz kılar ve secde ederiz.",
                    "O Allah, You alone we worship; for You we pray and prostrate."),
                Verse("وَإِلَيْكَ نَسْعَى وَنَحْفِدُ",
                    "Ve ileyke nes'â ve nahfid",
                    "Sana koşar, sana yaklaştıracak şeylere gayret ederiz.",
                    "To You we hasten and strive to serve."),
                Verse("نَرْجُو رَحْمَتَكَ وَنَخْشَى عَذَابَكَ",
                    "Nercû rahmeteke ve nahşâ azâbek",
                    "Rahmetini umar, azabından korkarız.",
                    "We hope for Your mercy and fear Your punishment."),
                Verse("إِنَّ عَذَابَكَ بِالْكُفَّارِ مُلْحِقٌ",
                    "İnne azâbeke bil küffâri mülhık",
                    "Şüphesiz senin azabın kâfirlere ulaşır.",
                    "Indeed, Your punishment will reach the disbelievers.")
            )
        ),
        LibraryItem(
            "amentu", "Âmentü", "Amantu", "آمنت",
            "İman esaslarını özetleyen metindir.",
            "The summary of the articles of faith.",
            listOf(
                Verse("آمَنْتُ بِاللَّهِ وَمَلَائِكَتِهِ وَكُتُبِهِ وَرُسُلِهِ وَالْيَوْمِ الْآخِرِ",
                    "Âmentü billâhi ve melâiketihî ve kütübihî ve rusülihî vel yevmil âhir",
                    "Allah'a, meleklerine, kitaplarına, peygamberlerine ve ahiret gününe inandım.",
                    "I believe in Allah, His angels, His books, His messengers and the Last Day,"),
                Verse("وَبِالْقَدَرِ خَيْرِهِ وَشَرِّهِ مِنَ اللَّهِ تَعَالَى",
                    "Ve bil kaderi hayrihî ve şerrihî minallâhi teâlâ",
                    "Kadere; hayrın ve şerrin Allah'tan olduğuna inandım.",
                    "and in destiny — that its good and its evil are from Allah Most High,"),
                Verse("وَالْبَعْثُ بَعْدَ الْمَوْتِ حَقٌّ",
                    "Vel ba'sü ba'del mevti hakkun",
                    "Öldükten sonra dirilmek haktır.",
                    "and that resurrection after death is true."),
                Verse("أَشْهَدُ أَنْ لَا إِلَهَ إِلَّا اللَّهُ وَأَشْهَدُ أَنَّ مُحَمَّدًا عَبْدُهُ وَرَسُولُهُ",
                    "Eşhedü en lâ ilâhe illallâh ve eşhedü enne Muhammeden abdühû ve rasûlüh",
                    "Şahitlik ederim ki Allah'tan başka ilah yoktur; Muhammed O'nun kulu ve elçisidir.",
                    "I bear witness that there is no god but Allah, and that Muhammad is His servant and messenger.")
            )
        )
    )
}
