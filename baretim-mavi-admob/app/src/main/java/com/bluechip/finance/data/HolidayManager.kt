package com.bluechip.finance.data

import android.content.Context

data class Holiday(val month: Int, val day: Int, val name: String)

object HolidayManager {

    // Türkiye resmi tatil listesi (sabit)
    private val fixedHolidays = listOf(
        Holiday(1,  1,  "Yılbaşı"),
        Holiday(4,  23, "Ulusal Egemenlik ve Çocuk Bayramı"),
        Holiday(5,  1,  "Emek ve Dayanışma Günü"),
        Holiday(5,  19, "Atatürk'ü Anma, Gençlik ve Spor Bayramı"),
        Holiday(7,  15, "Demokrasi ve Milli Birlik Günü"),
        Holiday(8,  30, "Zafer Bayramı"),
        Holiday(10, 29, "Cumhuriyet Bayramı")
    )

    // Ramazan / Kurban Bayramı tarihleri (2025-2030, yaklaşık)
    private val islamicHolidays = mapOf(
        2025 to listOf(
            Holiday(3, 30, "Ramazan Bayramı 1. Gün"),
            Holiday(3, 31, "Ramazan Bayramı 2. Gün"),
            Holiday(4,  1, "Ramazan Bayramı 3. Gün"),
            Holiday(6,  6, "Kurban Bayramı 1. Gün"),
            Holiday(6,  7, "Kurban Bayramı 2. Gün"),
            Holiday(6,  8, "Kurban Bayramı 3. Gün"),
            Holiday(6,  9, "Kurban Bayramı 4. Gün")
        ),
        2026 to listOf(
            Holiday(3, 20, "Ramazan Bayramı 1. Gün"),
            Holiday(3, 21, "Ramazan Bayramı 2. Gün"),
            Holiday(3, 22, "Ramazan Bayramı 3. Gün"),
            Holiday(5, 27, "Kurban Bayramı 1. Gün"),
            Holiday(5, 28, "Kurban Bayramı 2. Gün"),
            Holiday(5, 29, "Kurban Bayramı 3. Gün"),
            Holiday(5, 30, "Kurban Bayramı 4. Gün")
        ),
        2027 to listOf(
            Holiday(3,  9, "Ramazan Bayramı 1. Gün"),
            Holiday(3, 10, "Ramazan Bayramı 2. Gün"),
            Holiday(3, 11, "Ramazan Bayramı 3. Gün"),
            Holiday(5, 17, "Kurban Bayramı 1. Gün"),
            Holiday(5, 18, "Kurban Bayramı 2. Gün"),
            Holiday(5, 19, "Kurban Bayramı 3. Gün"),
            Holiday(5, 20, "Kurban Bayramı 4. Gün")
        )
    )

    fun getHolidays(year: Int): List<Holiday> {
        val list = fixedHolidays.toMutableList()
        islamicHolidays[year]?.let { list.addAll(it) }
        return list.sortedWith(compareBy({ it.month }, { it.day }))
    }

    fun isHoliday(year: Int, month: Int, day: Int): Boolean {
        return getHolidays(year).any { it.month == month && it.day == day }
    }

    /** Belirtilen tarihten itibaren kaç iş günü var (tatil+hafta sonu hariç). */
    fun workDaysUntil(year: Int, month: Int, fromDay: Int, toDay: Int): Int {
        var count = 0
        val cal = java.util.Calendar.getInstance()
        for (d in fromDay..toDay) {
            cal.set(year, month - 1, d)
            val dow = cal.get(java.util.Calendar.DAY_OF_WEEK)
            if (dow == java.util.Calendar.SATURDAY || dow == java.util.Calendar.SUNDAY) continue
            if (isHoliday(year, month, d)) continue
            count++
        }
        return count
    }
}
