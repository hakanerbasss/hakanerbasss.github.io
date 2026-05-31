package com.bluechip.finance.data

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

enum class SideIncomeCategory(val label: String, val emoji: String) {
    KIRA("Kira Geliri", "🏠"),
    FAIZ("Faiz Geliri", "🏦"),
    DIJITAL("Dijital Gelir", "💻"),
    FREELANCE("Freelance", "🎯"),
    DIGER("Diger", "📋")
}

data class SideIncomeRecord(
    val id: String = java.util.UUID.randomUUID().toString(),
    val amount: Double = 0.0,
    val dateMillis: Long = System.currentTimeMillis()
)

data class SideIncome(
    val id: String = java.util.UUID.randomUUID().toString(),
    val category: SideIncomeCategory = SideIncomeCategory.DIGER,
    val label: String = "",
    val amount: Double = 0.0,
    val isVariable: Boolean = false,
    val dayOfMonth: Int = 0,
    val records: List<SideIncomeRecord> = emptyList()
) {
    // Degisken degilse direkt amount, degiskense son 12 kayit ortalamasi
    fun effectiveAmount(): Double {
        if (!isVariable) return amount
        if (records.isEmpty()) return amount
        return records.takeLast(12).map { it.amount }.average()
    }
    // Bu ayin tutari: en son kayit varsa onu kullan, yoksa ortalama
    fun currentMonthAmount(): Double {
        if (!isVariable) return amount
        if (records.isEmpty()) return amount
        val cal = java.util.Calendar.getInstance()
        val thisMonth = cal.get(java.util.Calendar.MONTH)
        val thisYear  = cal.get(java.util.Calendar.YEAR)
        val thisMon = records.filter {
            val rc = java.util.Calendar.getInstance().apply { timeInMillis = it.dateMillis }
            rc.get(java.util.Calendar.MONTH) == thisMonth && rc.get(java.util.Calendar.YEAR) == thisYear
        }.maxByOrNull { it.dateMillis }
        return thisMon?.amount ?: effectiveAmount()
    }
}

data class UserProfile(
    val name: String = "",
    val grossSalary: Double = 0.0,
    val netSalary: Double = 0.0,
    val salaryDay: Int = 0,
    val startDateMillis: Long = 0L,
    val birthDateMillis: Long = 0L,
    val isUnderground: Boolean = false,
    val isLoggedIn: Boolean = false,
    val advanceDay: Int = 0,
    val advanceAmount: Double = 0.0,
    val isRetired: Boolean = false,
    val retirementSalary: Double = 0.0,
    val retirementDay: Int = 0,
    val sideIncomes: List<SideIncome> = emptyList(),
    val firstInsuranceDateMillis: Long = 0L
) {
    fun totalIncome(): Double {
        val side = sideIncomes.sumOf { it.effectiveAmount() }
        val retirement = if (isRetired) retirementSalary else 0.0
        return netSalary + retirement + side
    }

    fun isAdvanceTaken(): Boolean {
        if (advanceDay <= 0 || advanceAmount <= 0.0) return false
        val today = java.util.Calendar.getInstance().get(java.util.Calendar.DAY_OF_MONTH)
        return today >= advanceDay
    }
}

class ProfileManager(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("user_profile", Context.MODE_PRIVATE)

    fun save(profile: UserProfile) {
        val sideArr = JSONArray()
        profile.sideIncomes.forEach { s ->
            val recArr = JSONArray()
            s.records.forEach { r ->
                recArr.put(JSONObject().apply {
                    put("rid", r.id)
                    put("amount", r.amount)
                    put("date", r.dateMillis)
                })
            }
            sideArr.put(JSONObject().apply {
                put("id", s.id)
                put("category", s.category.name)
                put("label", s.label)
                put("amount", s.amount)
                put("isVariable", s.isVariable)
                put("dayOfMonth", s.dayOfMonth)
                put("records", recArr)
            })
        }
        prefs.edit()
            .putString("name", profile.name)
            .putFloat("gross_salary", profile.grossSalary.toFloat())
            .putFloat("net_salary", profile.netSalary.toFloat())
            .putInt("salary_day", profile.salaryDay)
            .putLong("start_date", profile.startDateMillis)
            .putLong("birth_date", profile.birthDateMillis)
            .putBoolean("underground", profile.isUnderground)
            .putBoolean("logged_in", true)
            .putInt("advance_day", profile.advanceDay)
            .putFloat("advance_amount", profile.advanceAmount.toFloat())
            .putBoolean("is_retired", profile.isRetired)
            .putFloat("retirement_salary", profile.retirementSalary.toFloat())
            .putInt("retirement_day", profile.retirementDay)
            .putString("side_incomes", sideArr.toString())
            .putLong("first_insurance_date", profile.firstInsuranceDateMillis)
            .apply()
    }

    fun load(): UserProfile {
        val sideJson = prefs.getString("side_incomes", "[]") ?: "[]"
        val sideArr = JSONArray(sideJson)
        val sides = mutableListOf<SideIncome>()
        for (i in 0 until sideArr.length()) {
            val o = sideArr.getJSONObject(i)
            val recArr = o.optJSONArray("records") ?: o.optJSONArray("history") ?: JSONArray()
            val recs = mutableListOf<SideIncomeRecord>()
            for (j in 0 until recArr.length()) {
                val r = recArr.optJSONObject(j)
                if (r != null) {
                    recs.add(SideIncomeRecord(
                        id = r.optString("rid", java.util.UUID.randomUUID().toString()),
                        amount = r.optDouble("amount", 0.0),
                        dateMillis = r.optLong("date", System.currentTimeMillis())
                    ))
                } else {
                    // Eski format: sadece double (history)
                    val amt = try { recArr.getDouble(j) } catch (_: Exception) { 0.0 }
                    if (amt > 0) recs.add(SideIncomeRecord(amount = amt))
                }
            }
            sides.add(SideIncome(
                id = o.optString("id", java.util.UUID.randomUUID().toString()),
                category = try { SideIncomeCategory.valueOf(o.getString("category")) } catch (_: Exception) { SideIncomeCategory.DIGER },
                label = o.optString("label", ""),
                amount = o.optDouble("amount", 0.0),
                isVariable = o.optBoolean("isVariable", false),
                dayOfMonth = o.optInt("dayOfMonth", 0),
                records = recs
            ))
        }
        return UserProfile(
            name = prefs.getString("name", "") ?: "",
            grossSalary = prefs.getFloat("gross_salary", 0f).toDouble(),
            netSalary = prefs.getFloat("net_salary", 0f).toDouble(),
            salaryDay = prefs.getInt("salary_day", 0),
            startDateMillis = prefs.getLong("start_date", 0L),
            birthDateMillis = prefs.getLong("birth_date", 0L),
            isUnderground = prefs.getBoolean("underground", false),
            isLoggedIn = prefs.getBoolean("logged_in", false),
            advanceDay = prefs.getInt("advance_day", 0),
            advanceAmount = prefs.getFloat("advance_amount", 0f).toDouble(),
            isRetired = prefs.getBoolean("is_retired", false),
            retirementSalary = prefs.getFloat("retirement_salary", 0f).toDouble(),
            retirementDay = prefs.getInt("retirement_day", 0),
            sideIncomes = sides,
            firstInsuranceDateMillis = prefs.getLong("first_insurance_date", 0L)
        )
    }

    fun isLoggedIn(): Boolean = prefs.getBoolean("logged_in", false)
    fun logout() { prefs.edit().clear().apply() }
}
