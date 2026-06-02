package com.bluechip.finance.data

import android.content.Context

object NotificationSettingsManager {

    private const val PREFS = "notif_settings"

    // Toggle keys
    private const val KEY_SALARY      = "notif_salary"
    private const val KEY_ADVANCE     = "notif_advance"
    private const val KEY_PAYMENT     = "notif_payment"
    private const val KEY_RETIREMENT  = "notif_retirement"
    private const val KEY_SIDE_INCOME = "notif_side_income"

    // Days before keys
    private const val KEY_SALARY_DAYS     = "notif_salary_days"
    private const val KEY_ADVANCE_DAYS    = "notif_advance_days"
    private const val KEY_PAYMENT_DAYS    = "notif_payment_days"
    private const val KEY_RETIREMENT_DAYS = "notif_retirement_days"
    private const val KEY_SIDE_DAYS       = "notif_side_days"
    private const val KEY_SPECIAL_DAY     = "notif_special_day"
    private const val KEY_SPECIAL_DAYS    = "notif_special_days" 

    // Time key
    private const val KEY_HOUR   = "notif_hour"
    private const val KEY_MINUTE = "notif_minute"

    data class NotifSettings(
        val salaryEnabled: Boolean = true,
        val advanceEnabled: Boolean = true,
        val paymentEnabled: Boolean = true,
        val retirementEnabled: Boolean = true,
        val sideIncomeEnabled: Boolean = true,
        val salaryDaysBefore: Int = 3,
        val advanceDaysBefore: Int = 1,
        val paymentDaysBefore: Int = 3,
        val retirementDaysBefore: Int = 3,
        val sideDaysBefore: Int = 1,
        val specialDayEnabled: Boolean = true,
        val specialDaysBefore: Int = 3,
        val hour: Int = 9,
        val minute: Int = 0
    )

    fun get(context: Context): NotifSettings {
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return NotifSettings(
            salaryEnabled     = p.getBoolean(KEY_SALARY, true),
            advanceEnabled    = p.getBoolean(KEY_ADVANCE, true),
            paymentEnabled    = p.getBoolean(KEY_PAYMENT, true),
            retirementEnabled = p.getBoolean(KEY_RETIREMENT, true),
            sideIncomeEnabled = p.getBoolean(KEY_SIDE_INCOME, true),
            salaryDaysBefore     = p.getInt(KEY_SALARY_DAYS, 3),
            advanceDaysBefore    = p.getInt(KEY_ADVANCE_DAYS, 1),
            paymentDaysBefore    = p.getInt(KEY_PAYMENT_DAYS, 3),
            retirementDaysBefore = p.getInt(KEY_RETIREMENT_DAYS, 3),
            sideDaysBefore       = p.getInt(KEY_SIDE_DAYS, 1),
            specialDayEnabled  = p.getBoolean(KEY_SPECIAL_DAY, true),
            specialDaysBefore = p.getInt(KEY_SPECIAL_DAYS, 3),
            hour   = p.getInt(KEY_HOUR, 9),
            minute = p.getInt(KEY_MINUTE, 0)
        )
    }

    fun save(context: Context, s: NotifSettings) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putBoolean(KEY_SALARY, s.salaryEnabled)
            .putBoolean(KEY_ADVANCE, s.advanceEnabled)
            .putBoolean(KEY_PAYMENT, s.paymentEnabled)
            .putBoolean(KEY_RETIREMENT, s.retirementEnabled)
            .putBoolean(KEY_SIDE_INCOME, s.sideIncomeEnabled)
            .putInt(KEY_SALARY_DAYS, s.salaryDaysBefore)
            .putInt(KEY_ADVANCE_DAYS, s.advanceDaysBefore)
            .putInt(KEY_PAYMENT_DAYS, s.paymentDaysBefore)
            .putInt(KEY_RETIREMENT_DAYS, s.retirementDaysBefore)
            .putInt(KEY_SIDE_DAYS, s.sideDaysBefore)
            .putBoolean(KEY_SPECIAL_DAY, s.specialDayEnabled)
            .putInt(KEY_SPECIAL_DAYS, s.specialDaysBefore)
            .putInt(KEY_HOUR, s.hour)
            .putInt(KEY_MINUTE, s.minute)
            .apply()
    }
}
