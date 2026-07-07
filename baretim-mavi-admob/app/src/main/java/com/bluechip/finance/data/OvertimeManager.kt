package com.bluechip.finance.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.Calendar
import java.util.UUID

enum class OvertimeTrackType(val label: String, val pct: String, val mult: Double) {
    PCT25 ("Gece",           "%25",  1.25),
    PCT50 ("Fazla Calisma",  "%50",  1.50),
    PCT75 ("Gece+Fazla",     "%75",  1.75),
    PCT100("Bayram/Tatil",   "%100", 2.00),
    PCT125("Gece+Tatil",     "%125", 2.25),
    PCT200("Resmi Tatil",    "%200", 3.00)
}

data class OvertimeRecord(
    val id:         String            = UUID.randomUUID().toString(),
    val dateMillis: Long              = System.currentTimeMillis(),
    val hours:      Double            = 0.0,
    val type:       OvertimeTrackType = OvertimeTrackType.PCT50,
    val brutAmount: Double            = 0.0,
    val netAmount:  Double            = 0.0,
    val note:       String            = ""
)

object OvertimeManager {

    private const val PREFS   = "overtime_track_prefs"
    private const val KEY     = "overtime_records"
    const val NET_RATE        = 0.715  // ~%71.5 net kaliyor (SGK+vergi+issizlik)

    fun calcBrutAmount(grossSalary: Double, hours: Double, type: OvertimeTrackType): Double {
        if (grossSalary <= 0 || hours <= 0) return 0.0
        return (grossSalary / 225.0) * type.mult * hours
    }

    fun calcNetAmount(brutAmount: Double): Double = brutAmount * NET_RATE

    fun unitHourlyNet(grossSalary: Double, type: OvertimeTrackType): Double {
        if (grossSalary <= 0) return 0.0
        return (grossSalary / 225.0) * type.mult * NET_RATE
    }

    fun loadAll(context: Context): List<OvertimeRecord> {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val json  = prefs.getString(KEY, "[]") ?: "[]"
        return try {
            val arr = JSONArray(json)
            (0 until arr.length()).map { parse(arr.getJSONObject(it)) }
        } catch (_: Exception) { emptyList() }
    }

    fun save(context: Context, records: List<OvertimeRecord>) {
        val arr = JSONArray()
        records.forEach { arr.put(toJson(it)) }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY, arr.toString()).apply()
    }

    fun add(context: Context, record: OvertimeRecord)    = save(context, loadAll(context) + record)
    fun update(context: Context, record: OvertimeRecord) = save(context, loadAll(context).map { if (it.id == record.id) record else it })
    fun delete(context: Context, id: String)             = save(context, loadAll(context).filter { it.id != id })
    fun deleteAll(context: Context)                      = save(context, emptyList())

    fun thisMonthRecords(context: Context): List<OvertimeRecord> {
        val now   = Calendar.getInstance()
        val month = now.get(Calendar.MONTH)
        val year  = now.get(Calendar.YEAR)
        return loadAll(context).filter {
            val cal = Calendar.getInstance().apply { timeInMillis = it.dateMillis }
            cal.get(Calendar.MONTH) == month && cal.get(Calendar.YEAR) == year
        }
    }

    fun thisMonthTotalBrut(context: Context): Double = thisMonthRecords(context).sumOf { it.brutAmount }
    fun thisMonthTotalNet(context: Context):  Double = thisMonthRecords(context).sumOf { it.netAmount }
    fun thisMonthTotal(context: Context):     Double = thisMonthTotalNet(context)

    fun currentPeriodStart(salaryDay: Int): Calendar {
        val today = Calendar.getInstance()
        return if (salaryDay <= 0) {
            Calendar.getInstance().apply {
                set(Calendar.DAY_OF_MONTH, 1)
                set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0)
                set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
            }
        } else {
            val todayDay = today.get(Calendar.DAY_OF_MONTH)
            Calendar.getInstance().apply {
                time = today.time
                if (todayDay < salaryDay) add(Calendar.MONTH, -1)
                val maxDay = getActualMaximum(Calendar.DAY_OF_MONTH)
                set(Calendar.DAY_OF_MONTH, minOf(salaryDay, maxDay))
                set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0)
                set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
            }
        }
    }

    fun currentPeriodLabel(salaryDay: Int): String {
        if (salaryDay <= 0) return java.text.SimpleDateFormat("MMMM yyyy", java.util.Locale("tr"))
            .format(java.util.Date()).replaceFirstChar { it.uppercase() }
        val start = currentPeriodStart(salaryDay)
        val end = Calendar.getInstance().apply {
            time = start.time
            add(Calendar.MONTH, 1)
            add(Calendar.DAY_OF_MONTH, -1)
        }
        val fmt  = java.text.SimpleDateFormat("d MMM", java.util.Locale("tr"))
        val fmtY = java.text.SimpleDateFormat("d MMM yyyy", java.util.Locale("tr"))
        return if (start.get(Calendar.YEAR) == end.get(Calendar.YEAR))
            "${fmt.format(start.time)} - ${fmtY.format(end.time)} Donemi"
        else
            "${fmtY.format(start.time)} - ${fmtY.format(end.time)} Donemi"
    }

    fun currentPeriodRecords(context: Context, salaryDay: Int): List<OvertimeRecord> {
        if (salaryDay <= 0) return thisMonthRecords(context)
        val startMillis = currentPeriodStart(salaryDay).timeInMillis
        return loadAll(context).filter { it.dateMillis >= startMillis }
    }

    fun currentPeriodTotalNet(context: Context, salaryDay: Int): Double =
        currentPeriodRecords(context, salaryDay).sumOf { it.netAmount }

    fun groupedByMonth(context: Context): Map<String, List<OvertimeRecord>> {
        val all = loadAll(context).sortedByDescending { it.dateMillis }
        val fmt = java.text.SimpleDateFormat("MMMM yyyy", java.util.Locale("tr"))
        return all.groupBy { fmt.format(java.util.Date(it.dateMillis)) }
    }

    private fun toJson(r: OvertimeRecord) = JSONObject().apply {
        put("id",    r.id);   put("date",  r.dateMillis); put("hours", r.hours)
        put("type",  r.type.name); put("brut", r.brutAmount); put("net", r.netAmount)
        put("note",  r.note)
    }

    private fun parse(o: JSONObject) = OvertimeRecord(
        id         = o.optString("id", UUID.randomUUID().toString()),
        dateMillis = o.optLong("date",  System.currentTimeMillis()),
        hours      = o.optDouble("hours", 0.0),
        type       = try { OvertimeTrackType.valueOf(o.getString("type")) } catch (_: Exception) { OvertimeTrackType.PCT50 },
        brutAmount = o.optDouble("brut", 0.0),
        netAmount  = o.optDouble("net",  0.0).let { if (it == 0.0) o.optDouble("brut", 0.0) * NET_RATE else it },
        note       = o.optString("note", "")
    )
}
