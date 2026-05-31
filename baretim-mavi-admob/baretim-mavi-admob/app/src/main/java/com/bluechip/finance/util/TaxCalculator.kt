package com.bluechip.finance.util

/**
 * Doğru kademeli (progressive) vergi hesaplama motoru.
 *
 * HATA (eski kod):
 *   incomeTax = taxable * bRate
 *   → Kümülatif matrah dilim sınırını geçtiği ayda tüm aylık maaşa
 *     yüksek dilim oranı uygulanıyordu. Örnek: Nisan ayında (4. ay)
 *     40.000₺ taxable için eski kod 10.000₺, doğru sonuç 8.000₺.
 *
 * DÜZELTME:
 *   incomeTax = kümülatif_vergi(N. ay) − kümülatif_vergi(N-1. ay)
 *   → Her ay için yalnızca o aya düşen kısım vergilenir.
 *
 * Hem TaxScreen hem BordroScreen List<Pair<Double,Double>> ile çalışır.
 */
object TaxCalculator {

    /**
     * Verilen kümülatif matrah üzerinden toplam kademeli vergiyi hesaplar.
     *
     * @param cumulativeMatrah  Yılın başından bu aya kadar toplam vergiye tabi matrah
     * @param brackets          List<Pair<limit, rate>> — artan sırada
     */
    fun cumulativeTax(
        cumulativeMatrah: Double,
        brackets: List<Pair<Double, Double>>
    ): Double {
        var tax = 0.0
        var prevLimit = 0.0
        for ((limit, rate) in brackets) {
            if (cumulativeMatrah <= prevLimit) break
            val inBracket = minOf(cumulativeMatrah, limit) - prevLimit
            if (inBracket > 0.0) tax += inBracket * rate
            prevLimit = limit
            if (cumulativeMatrah <= limit) break
        }
        return tax
    }

    /**
     * Belirtilen aydaki gelir vergisini hesaplar.
     *
     * @param taxableThisMonth  Bu aya ait vergiye tabi matrah (AGİ düşüldükten sonra)
     * @param monthIndex        Yılın kaçıncı ayı (1–12)
     * @param brackets          List<Pair<limit, rate>>
     */
    fun monthlyIncomeTax(
        taxableThisMonth: Double,
        monthIndex: Int,
        brackets: List<Pair<Double, Double>>
    ): Double {
        if (taxableThisMonth <= 0.0 || monthIndex <= 0) return 0.0
        val cumulN   = taxableThisMonth * monthIndex
        val cumulNm1 = taxableThisMonth * (monthIndex - 1)
        return cumulativeTax(cumulN, brackets) - cumulativeTax(cumulNm1, brackets)
    }
}
