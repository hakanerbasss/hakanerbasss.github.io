package com.wizaicorp.namazvakitleri.data

data class PrayerTimes(
    val imsak: String,
    val gunes: String,
    val ogle: String,
    val ikindi: String,
    val aksam: String,
    val yatsi: String,
    val city: String,
    val date: String
) {
    fun asList(): List<Pair<String, String>> = listOf(
        Lang.get("p_imsak")  to imsak,
        Lang.get("p_gunes")  to gunes,
        Lang.get("p_ogle")   to ogle,
        Lang.get("p_ikindi") to ikindi,
        Lang.get("p_aksam")  to aksam,
        Lang.get("p_yatsi")  to yatsi
    )
}

data class City(val name: String, val apiName: String, val country: String = "Turkey")
