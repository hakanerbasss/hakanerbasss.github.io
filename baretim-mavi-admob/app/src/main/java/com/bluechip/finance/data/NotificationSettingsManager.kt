package com.bluechip.finance.data

import android.content.Context

data class NotificationSettings(
    val hour: Int = 9,
    val minute: Int = 0,
    val salaryEnabled: Boolean = true,
    val salaryDaysBefore: Int = 1,
    val advanceEnabled: Boolean = true,
    val advanceDaysBefore: Int = 1,
    val retirementEnabled: Boolean = true,
    val retirementDaysBefore: Int = 1,
    val sideIncomeEnabled: Boolean = true,
    val sideDaysBefore: Int = 1,
    val paymentEnabled: Boolean = true,
    val paymentDaysBefore: Int = 2,
    val specialDayEnabled: Boolean = true,
    val specialDaysBefore: Int = 1,
    val backupReminderEnabled: Boolean = true
)

object NotificationSettingsManager {
    private const val PREFS = "notif_settings"
    const val KEY_LAST_BACKUP_DATE = "last_backup_date"

    fun get(context: Context): NotificationSettings {
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return NotificationSettings(
            hour                   = p.getInt("hour", 9),
            minute                 = p.getInt("minute", 0),
            salaryEnabled          = p.getBoolean("salary_enabled", true),
            salaryDaysBefore       = p.getInt("salary_days_before", 1),
            advanceEnabled         = p.getBoolean("advance_enabled", true),
            advanceDaysBefore      = p.getInt("advance_days_before", 1),
            retirementEnabled      = p.getBoolean("retirement_enabled", true),
            retirementDaysBefore   = p.getInt("retirement_days_before", 1),
            sideIncomeEnabled      = p.getBoolean("side_income_enabled", true),
            sideDaysBefore         = p.getInt("side_days_before", 1),
            paymentEnabled         = p.getBoolean("payment_enabled", true),
            paymentDaysBefore      = p.getInt("payment_days_before", 2),
            specialDayEnabled      = p.getBoolean("special_day_enabled", true),
            specialDaysBefore      = p.getInt("special_days_before", 1),
            backupReminderEnabled  = p.getBoolean("backup_reminder_enabled", true)
        )
    }

    fun save(context: Context, s: NotificationSettings) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().apply {
            putInt("hour", s.hour)
            putInt("minute", s.minute)
            putBoolean("salary_enabled", s.salaryEnabled)
            putInt("salary_days_before", s.salaryDaysBefore)
            putBoolean("advance_enabled", s.advanceEnabled)
            putInt("advance_days_before", s.advanceDaysBefore)
            putBoolean("retirement_enabled", s.retirementEnabled)
            putInt("retirement_days_before", s.retirementDaysBefore)
            putBoolean("side_income_enabled", s.sideIncomeEnabled)
            putInt("side_days_before", s.sideDaysBefore)
            putBoolean("payment_enabled", s.paymentEnabled)
            putInt("payment_days_before", s.paymentDaysBefore)
            putBoolean("special_day_enabled", s.specialDayEnabled)
            putInt("special_days_before", s.specialDaysBefore)
            putBoolean("backup_reminder_enabled", s.backupReminderEnabled)
            apply()
        }
    }
}
