package com.wizaicorp.namazvakitleri.data

import java.time.DayOfWeek
import java.time.LocalDate
import java.time.chrono.HijrahDate
import java.time.temporal.ChronoField
import java.time.temporal.ChronoUnit

data class HolyDay(val nameKey: String, val date: LocalDate) {
    val daysLeft: Long get() = ChronoUnit.DAYS.between(LocalDate.now(), date)
}

/**
 * Dini gunleri hicri takvimden (Umm al-Qura) hesaplar.
 * minSdk 26 oldugu icin java.time.chrono.HijrahDate dogrudan kullanilabilir.
 */
object HolyDays {

    // (hicri ay, hicri gun, isim anahtari)
    private val fixed = listOf(
        Triple(1, 1, "e_hicri_yil"),
        Triple(1, 10, "e_asure"),
        Triple(3, 12, "e_mevlid"),
        Triple(7, 1, "e_uc_aylar"),
        Triple(7, 27, "e_mirac"),
        Triple(8, 15, "e_berat"),
        Triple(9, 1, "e_ramazan"),
        Triple(9, 27, "e_kadir"),
        Triple(10, 1, "e_ramazan_bayram"),
        Triple(12, 9, "e_arefe"),
        Triple(12, 10, "e_kurban")
    )

    /** Bugunden itibaren onumuzdeki ~14 ayin dini gunleri, tarihe gore sirali. */
    fun upcoming(): List<HolyDay> {
        val today = LocalDate.now()
        val hijriYearNow = HijrahDate.from(today).get(ChronoField.YEAR)
        val result = mutableListOf<HolyDay>()

        for (hy in (hijriYearNow - 1)..(hijriYearNow + 1)) {
            for ((month, day, key) in fixed) {
                val date = toGregorian(hy, month, day) ?: continue
                result.add(HolyDay(key, date))
            }
            // Regaib: Recep ayinin ilk cuma gecesi (persembeyi cumaya baglayan gece)
            regaib(hy)?.let { result.add(HolyDay("e_regaib", it)) }
        }

        return result
            .filter { !it.date.isBefore(today) }
            .sortedBy { it.date }
            .take(15)
    }

    private fun toGregorian(hijriYear: Int, month: Int, day: Int): LocalDate? = try {
        LocalDate.from(HijrahDate.of(hijriYear, month, day))
    } catch (e: Exception) { null }

    private fun regaib(hijriYear: Int): LocalDate? {
        val start = toGregorian(hijriYear, 7, 1) ?: return null
        // Recep'in ilk cumasini bul, kandil gecesi bir onceki gun (persembe) aksami
        var d = start
        repeat(7) {
            if (d.dayOfWeek == DayOfWeek.FRIDAY) return d.minusDays(1)
            d = d.plusDays(1)
        }
        return null
    }

    /** Bugunun hicri tarihi, secili dilde: "15 Şaban 1447" */
    fun hijriToday(): String {
        val h = HijrahDate.from(LocalDate.now())
        val day = h.get(ChronoField.DAY_OF_MONTH)
        val month = h.get(ChronoField.MONTH_OF_YEAR)
        val year = h.get(ChronoField.YEAR)
        return "$day ${Lang.get("h_$month")} $year"
    }
}
