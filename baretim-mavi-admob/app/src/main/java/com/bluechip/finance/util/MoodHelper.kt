package com.bluechip.finance.util

import android.content.Context
import com.bluechip.finance.data.PaymentManager
import com.bluechip.finance.data.ProfileManager
import java.util.Calendar

fun getMoodInfo(
    daysToSalary: Int?,
    daysToAdvance: Int?,
    daysToPayment: Int?,
    dayOfYear: Int
): Pair<String, String> {
    if (daysToAdvance != null && daysToAdvance <= 1) {
        val emojis = listOf("\uD83D\uDE0E", "\uD83E\uDD73", "\uD83C\uDF89", "\uD83D\uDCB8")
        return Pair(emojis[dayOfYear % emojis.size], if (daysToAdvance == 0) "Avans gunu!" else "Yarin avans!")
    }
    if (daysToSalary == 0) return Pair("\uD83E\uDD11", "Maas gunu!")
    if (daysToSalary == 1) return Pair("\uD83D\uDE01", "Yarin maas!")
    if (daysToSalary != null && daysToSalary <= 3) {
        val emojis = listOf("\uD83D\uDE0A", "\uD83D\uDE04", "\uD83D\uDE4C", "\uD83E\uDD29")
        return Pair(emojis[dayOfYear % emojis.size], "Az kaldi!")
    }
    if (daysToAdvance != null && daysToAdvance <= 5) {
        val emojis = listOf("\uD83D\uDE42", "\uD83D\uDE0C", "\uD83D\uDE0F", "\uD83D\uDE0B")
        return Pair(emojis[dayOfYear % emojis.size], "Avans yaklisiyor")
    }
    if (daysToPayment != null && daysToPayment <= 3 && (daysToSalary == null || daysToSalary > 5)) {
        val emojis = listOf("\uD83D\uDE24", "\uD83D\uDE20", "\uD83E\uDD2C", "\uD83D\uDE21")
        return Pair(emojis[dayOfYear % emojis.size], "Odeme kapida!")
    }
    if (daysToPayment != null && daysToPayment <= 7 && (daysToSalary == null || daysToSalary > 10)) {
        val emojis = listOf("\uD83D\uDE11", "\uD83D\uDE12", "\uD83E\uDEE0", "\uD83D\uDE36")
        return Pair(emojis[dayOfYear % emojis.size], "Odeme geliyor...")
    }
    if (daysToSalary != null && daysToSalary <= 7) {
        val emojis = listOf("\uD83D\uDE42", "\uD83D\uDE0C", "\uD83E\uDEE1", "\uD83D\uDE0F")
        return Pair(emojis[dayOfYear % emojis.size], "Yaklisiyor!")
    }
    if (daysToSalary != null && daysToSalary <= 14) {
        val emojis = listOf("\uD83D\uDE10", "\uD83E\uDD14", "\uD83D\uDE36", "\uD83D\uDE44")
        return Pair(emojis[dayOfYear % emojis.size], "Biraz daha sabret")
    }
    if (daysToSalary != null && daysToSalary <= 20) {
        val emojis = listOf("\uD83D\uDE1F", "\uD83D\uDE14", "\uD83D\uDE29", "\uD83D\uDE2B")
        return Pair(emojis[dayOfYear % emojis.size], "Uzak biraz...")
    }
    if (daysToSalary != null && daysToSalary <= 25) {
        val emojis = listOf("\uD83D\uDE22", "\uD83D\uDE1E", "\uD83D\uDE13", "\uD83D\uDE25")
        return Pair(emojis[dayOfYear % emojis.size], "Cuzdan agliyor")
    }
    if (daysToSalary != null) {
        val emojis = listOf("\uD83D\uDE2D", "\uD83D\uDC80", "\uD83E\uDD7A", "\uD83D\uDE30")
        return Pair(emojis[dayOfYear % emojis.size], "Cok uzak...")
    }
    return Pair("\uD83D\uDE0A", "Iyi gunler!")
}

fun calcMoodEmoji(context: Context): String {
    val profile = ProfileManager(context).load()
    val cal = Calendar.getInstance()
    val today = cal.get(Calendar.DAY_OF_MONTH)
    val dayOfYear = cal.get(Calendar.DAY_OF_YEAR)
    val salaryDay = profile.salaryDay
    val daysToSalary: Int? = if (salaryDay > 0) {
        val maxDay = cal.getActualMaximum(Calendar.DAY_OF_MONTH)
        if (salaryDay >= today) salaryDay - today
        else (maxDay - today) + minOf(salaryDay, maxDay)
    } else null
    val advanceDay = profile.advanceDay
    val daysToAdvance: Int? = if (advanceDay > 0) {
        val maxDay = cal.getActualMaximum(Calendar.DAY_OF_MONTH)
        if (advanceDay >= today) advanceDay - today
        else (maxDay - today) + minOf(advanceDay, maxDay)
    } else null
    val daysToPayment: Int? = try {
        PaymentManager.getUpcomingThisMonth(context)
            .firstOrNull()?.dueDayOfMonth
            ?.let { day -> day - today }
            ?.takeIf { it >= 0 }
    } catch (_: Exception) { null }
    return getMoodInfo(daysToSalary, daysToAdvance, daysToPayment, dayOfYear).first
}
