package com.bluechip.finance.util

import java.util.Locale

data class BordroScanResult(
    val grossSalary: String = "",
    val netSalary: String = "",
    val overtimeAmount: String = "",
    val mealAllowance: String = "",
    val transportAllowance: String = "",
    val clothingAllowance: String = "",
    val month: Int = -1
)

object BordroOcrParser {

    // Matches Turkish numbers: 1.500,00 or 1500 or 15000,00
    private val NUMBER = Regex("""(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{4,}(?:[.,]\d{1,2})?)""")

    private val GROSS = listOf(
        "brüt ücret", "brüt maaş", "toplam brüt", "ücret brüt", "esas ücret",
        "temel ücret", "ücret (brüt)", "brüt kazanç", "brüt"
    )
    private val NET = listOf(
        "net ödeme", "net ücret", "ele geçen", "ödenecek net", "net maaş",
        "ödenecek ücret", "net ödenecek", "ödenecek tutar", "net"
    )
    private val MEAL = listOf(
        "yemek yardımı", "yemek ücreti", "yemek bedeli", "yemek yrd", "yemek"
    )
    private val TRANSPORT = listOf(
        "ulaşım yardımı", "yol yardımı", "servis ücreti", "yol ücreti",
        "ulaşım bedeli", "yol yrd", "ulaşım"
    )
    private val CLOTHING = listOf(
        "giyim yardımı", "kıyafet yardımı", "giyim bedeli", "giyim"
    )
    private val OVERTIME = listOf(
        "fazla mesai ücreti", "fazla çalışma ücreti", "fazla mesai", "overtime"
    )

    // Longer keys matched first (more specific)
    private val ALL_KEYS = listOf(GROSS, NET, MEAL, TRANSPORT, CLOTHING, OVERTIME)
        .flatten()
        .sortedByDescending { it.length }

    private val MONTHS = linkedMapOf(
        "ocak" to 0, "şubat" to 1, "mart" to 2, "nisan" to 3,
        "mayıs" to 4, "haziran" to 5, "temmuz" to 6, "ağustos" to 7,
        "eylül" to 8, "ekim" to 9, "kasım" to 10, "aralık" to 11
    )

    fun parse(rawText: String): BordroScanResult {
        val text = rawText.lowercase(Locale.forLanguageTag("tr"))
        val lines = text.lines()

        fun firstBigNumber(line: String): String {
            val nums = NUMBER.findAll(line).map { it.value }
                .filter { toDouble(it) >= 500.0 }  // salaries > 500 TL
                .toList()
            return nums.maxByOrNull { toDouble(it) } ?: ""
        }

        fun findAmount(keys: List<String>): String {
            for (key in keys.sortedByDescending { it.length }) {
                for ((i, line) in lines.withIndex()) {
                    if (line.contains(key)) {
                        val onLine = firstBigNumber(line)
                        if (onLine.isNotEmpty()) return onLine
                        // Amount may be on the next line
                        if (i + 1 < lines.size) {
                            val next = firstBigNumber(lines[i + 1])
                            if (next.isNotEmpty()) return next
                        }
                    }
                }
            }
            return ""
        }

        var month = -1
        for ((name, idx) in MONTHS) {
            if (text.contains(name)) { month = idx; break }
        }

        return BordroScanResult(
            grossSalary        = findAmount(GROSS),
            netSalary          = findAmount(NET),
            overtimeAmount     = findAmount(OVERTIME),
            mealAllowance      = findAmount(MEAL),
            transportAllowance = findAmount(TRANSPORT),
            clothingAllowance  = findAmount(CLOTHING),
            month              = month
        )
    }

    fun toDouble(s: String): Double {
        if (s.isBlank()) return 0.0
        return when {
            // Turkish: 1.500,00
            s.contains(',') -> s.replace(".", "").replace(",", ".").toDoubleOrNull() ?: 0.0
            // International: 1,500.00
            else -> s.replace(",", "").toDoubleOrNull() ?: 0.0
        }
    }

    // Returns clean integer string for salary input fields (e.g. "45000")
    fun toSalaryString(raw: String): String {
        val d = toDouble(raw)
        return if (d > 0) d.toInt().toString() else ""
    }
}
