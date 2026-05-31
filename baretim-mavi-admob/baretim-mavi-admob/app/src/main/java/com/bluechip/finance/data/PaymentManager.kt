package com.bluechip.finance.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.Calendar
import java.util.UUID

// Ödeme kategorileri
enum class PaymentCategory(val label: String, val emoji: String) {
    FATURA("Fatura", "⚡"),
    KIRA("Kira", "🏠"),
    KREDI("Kredi", "🏦"),
    ABONELIK("Abonelik", "📱"),
    SIGORTA("Sigorta", "🛡️"),
    DIGER("Diğer", "📋")
}

data class Payment(
    val id: String = UUID.randomUUID().toString(),
    val name: String = "",
    val amount: Double = 0.0,
    val category: PaymentCategory = PaymentCategory.DIGER,
    val dueDayOfMonth: Int = 1,
    val isRecurring: Boolean = true,
    val isVariable: Boolean = false,
    val isActive: Boolean = true,
    val createdAt: Long = System.currentTimeMillis()
)

data class PaymentRecord(
    val id: String = UUID.randomUUID().toString(),
    val paymentId: String = "",        // Hangi Payment'a ait
    val paymentName: String = "",
    val amount: Double = 0.0,
    val category: PaymentCategory = PaymentCategory.DIGER,
    val paidAt: Long = System.currentTimeMillis(),
    val dueMonth: Int = 0,            // Hangi ay için ödendi (Calendar.MONTH)
    val dueYear: Int = 0
)

object PaymentManager {

    private const val PREFS = "payment_prefs"
    private const val KEY_PAYMENTS = "payments"
    private const val KEY_RECORDS = "payment_records"

    // ── Payments (tanımlar) ───────────────────────────────────────

    fun getPayments(context: Context): List<Payment> {
        val json = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_PAYMENTS, "[]") ?: "[]"
        return parsePayments(JSONArray(json))
    }

    fun savePayment(context: Context, payment: Payment) {
        val list = getPayments(context).toMutableList()
        val idx = list.indexOfFirst { it.id == payment.id }
        if (idx >= 0) list[idx] = payment else list.add(payment)
        savePayments(context, list)
    }

    fun deletePayment(context: Context, paymentId: String) {
        val list = getPayments(context).map {
            if (it.id == paymentId) it.copy(isActive = false) else it
        }
        savePayments(context, list)
    }

    fun getActivePayments(context: Context): List<Payment> =
        getPayments(context).filter { it.isActive }

    // Bu ay içinde ödenecek aktif ödemeler (son ödeme günü bu ay içinde)
    fun getUpcomingThisMonth(context: Context): List<Payment> {
        val cal = Calendar.getInstance()
        val today = cal.get(Calendar.DAY_OF_MONTH)
        val maxDay = cal.getActualMaximum(Calendar.DAY_OF_MONTH)
        return getActivePayments(context)
            .filter { it.dueDayOfMonth >= today && it.dueDayOfMonth <= maxDay }
            .sortedBy { it.dueDayOfMonth }
    }

    // Sonraki 30 gün içinde yaklaşan ödemeler
    fun getUpcoming30Days(context: Context): List<Payment> {
        val cal = Calendar.getInstance()
        val today = cal.get(Calendar.DAY_OF_MONTH)
        val month = cal.get(Calendar.MONTH)
        val maxDay = cal.getActualMaximum(Calendar.DAY_OF_MONTH)
        return getActivePayments(context)
            .filter { p ->
                // Bu ay kalan günler veya gelecek ay başı
                (p.dueDayOfMonth >= today && month == cal.get(Calendar.MONTH)) ||
                (p.dueDayOfMonth < today)  // Gelecek ay
            }
            .sortedBy { it.dueDayOfMonth }
    }

    fun getThisMonthTotal(context: Context): Double =
        getUpcomingThisMonth(context).sumOf { it.amount }

    // ── Records (geçmiş ödemeler) ──────────────────────────────────

    fun getRecords(context: Context): List<PaymentRecord> {
        val json = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_RECORDS, "[]") ?: "[]"
        return parseRecords(JSONArray(json))
    }

    fun markAsPaid(context: Context, payment: Payment) {
        val cal = Calendar.getInstance()
        val actualAmount = if (payment.isVariable && payment.isRecurring) {
            val avg = getAverageAmount(context, payment.id)
            if (avg > 0) avg else payment.amount
        } else payment.amount
        val record = PaymentRecord(
            paymentId   = payment.id,
            paymentName = payment.name,
            amount      = actualAmount,
            category    = payment.category,
            paidAt      = System.currentTimeMillis(),
            dueMonth    = cal.get(Calendar.MONTH),
            dueYear     = cal.get(Calendar.YEAR)
        )
        val list = getRecords(context).toMutableList()
        list.add(0, record)
        saveRecords(context, list)
    }

    fun getTotalPaid(context: Context): Double =
        getRecords(context).sumOf { it.amount }

    // Aylık özet: son 6 ay
    fun getMonthlyTotals(context: Context): List<Pair<String, Double>> {
        val records = getRecords(context)
        val result = mutableListOf<Pair<String, Double>>()
        val cal = Calendar.getInstance()
        val monthNames = listOf("Oca","Şub","Mar","Nis","May","Haz","Tem","Ağu","Eyl","Eki","Kas","Ara")
        repeat(6) { i ->
            val m = cal.get(Calendar.MONTH)
            val y = cal.get(Calendar.YEAR)
            val label = "${monthNames[m]} ${y.toString().takeLast(2)}"
            val total = records.filter { it.dueMonth == m && it.dueYear == y }.sumOf { it.amount }
            result.add(0, label to total)
            cal.add(Calendar.MONTH, -1)
        }
        return result
    }

    // Bu ay bu ödeme zaten işaretlendi mi?
    fun isPaidThisMonth(context: Context, paymentId: String): Boolean {
        val cal = Calendar.getInstance()
        val m = cal.get(Calendar.MONTH)
        val y = cal.get(Calendar.YEAR)
        return getRecords(context).any { it.paymentId == paymentId && it.dueMonth == m && it.dueYear == y }
    }

    fun clearRecords(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY_RECORDS, "[]").apply()
    }

    fun deleteRecord(context: Context, recordId: String) {
        val list = getRecords(context).filter { it.id != recordId }
        saveRecords(context, list)
    }

    fun autoMarkDuePayments(context: Context) {
        val cal = Calendar.getInstance()
        val today = cal.get(Calendar.DAY_OF_MONTH)
        val month = cal.get(Calendar.MONTH)
        val year  = cal.get(Calendar.YEAR)
        getActivePayments(context).forEach { p ->
            if (p.dueDayOfMonth <= today && !isPaidThisMonth(context, p.id)) {
                val actualAmount = if (p.isVariable && p.isRecurring) {
                    val avg = getAverageAmount(context, p.id)
                    if (avg > 0) avg else p.amount
                } else p.amount
                val record = PaymentRecord(
                    paymentId   = p.id,
                    paymentName = p.name,
                    amount      = actualAmount,
                    category    = p.category,
                    paidAt      = System.currentTimeMillis(),
                    dueMonth    = month,
                    dueYear     = year
                )
                val list = getRecords(context).toMutableList()
                list.add(0, record)
                saveRecords(context, list)
            }
        }
    }

    fun getAverageAmount(context: Context, paymentId: String): Double {
        val records = getRecords(context).filter { it.paymentId == paymentId }
        return if (records.isEmpty()) 0.0 else records.sumOf { it.amount } / records.size
    }

    // En yuksek odeme ayi
    fun getHighestMonth(context: Context): Pair<String, Double>? =
        getMonthlyTotals(context).maxByOrNull { it.second }?.takeIf { it.second > 0 }

    // ── Serialization ──────────────────────────────────────────────

    private fun savePayments(context: Context, list: List<Payment>) {
        val arr = JSONArray()
        list.forEach { p ->
            arr.put(JSONObject().apply {
                put("id", p.id)
                put("name", p.name)
                put("amount", p.amount)
                put("category", p.category.name)
                put("dueDayOfMonth", p.dueDayOfMonth)
                put("isRecurring", p.isRecurring)
                put("isVariable", p.isVariable)
                put("isActive", p.isActive)
                put("createdAt", p.createdAt)
            })
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY_PAYMENTS, arr.toString()).apply()
    }

    private fun parsePayments(arr: JSONArray): List<Payment> {
        val list = mutableListOf<Payment>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            list.add(Payment(
                id = o.getString("id"),
                name = o.getString("name"),
                amount = o.getDouble("amount"),
                category = try { PaymentCategory.valueOf(o.getString("category")) } catch (_: Exception) { PaymentCategory.DIGER },
                dueDayOfMonth = o.getInt("dueDayOfMonth"),
                isRecurring = o.optBoolean("isRecurring", true),
                isVariable  = o.optBoolean("isVariable", false),
                isActive    = o.optBoolean("isActive", true),
                createdAt = o.optLong("createdAt", 0L)
            ))
        }
        return list
    }

    private fun saveRecords(context: Context, list: List<PaymentRecord>) {
        val arr = JSONArray()
        list.forEach { r ->
            arr.put(JSONObject().apply {
                put("id", r.id)
                put("paymentId", r.paymentId)
                put("paymentName", r.paymentName)
                put("amount", r.amount)
                put("category", r.category.name)
                put("paidAt", r.paidAt)
                put("dueMonth", r.dueMonth)
                put("dueYear", r.dueYear)
            })
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY_RECORDS, arr.toString()).apply()
    }

    private fun parseRecords(arr: JSONArray): List<PaymentRecord> {
        val list = mutableListOf<PaymentRecord>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            list.add(PaymentRecord(
                id = o.getString("id"),
                paymentId = o.getString("paymentId"),
                paymentName = o.getString("paymentName"),
                amount = o.getDouble("amount"),
                category = try { PaymentCategory.valueOf(o.getString("category")) } catch (_: Exception) { PaymentCategory.DIGER },
                paidAt = o.getLong("paidAt"),
                dueMonth = o.getInt("dueMonth"),
                dueYear = o.getInt("dueYear")
            ))
        }
        return list
    }
}
