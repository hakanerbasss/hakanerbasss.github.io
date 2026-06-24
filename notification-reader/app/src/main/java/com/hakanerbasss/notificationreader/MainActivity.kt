package com.hakanerbasss.notificationreader

import android.content.ComponentName
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.recyclerview.widget.DividerItemDecoration
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: AppPreferences
    private lateinit var recyclerView: RecyclerView
    private lateinit var progressBar: ProgressBar
    private lateinit var statusText: TextView
    private lateinit var emptyText: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = AppPreferences(this)
        recyclerView = findViewById(R.id.recycler_view)
        progressBar = findViewById(R.id.progress_bar)
        statusText = findViewById(R.id.status_text)
        emptyText = findViewById(R.id.empty_text)

        val lm = LinearLayoutManager(this)
        recyclerView.layoutManager = lm
        recyclerView.addItemDecoration(DividerItemDecoration(this, lm.orientation))

        setupSettings()
        loadApps()
    }

    override fun onResume() {
        super.onResume()
        updatePermissionStatus()
    }

    private fun setupSettings() {
        bindSetting(
            rowId = R.id.row_announce_app,
            title = "Uygulama adını söyle",
            desc = "Örn: \"WhatsApp: Merhaba\"",
            get = { prefs.isAnnounceApp() },
            set = { prefs.setAnnounceApp(it) }
        )
        bindSetting(
            rowId = R.id.row_announce_sender,
            title = "Gönderen adını söyle",
            desc = "Örn: \"WhatsApp, Ahmet: Merhaba\"",
            get = { prefs.isAnnounceSender() },
            set = { prefs.setAnnounceSender(it) }
        )
        bindSetting(
            rowId = R.id.row_announce_number,
            title = "Ad yoksa numara söyle",
            desc = "Kişi kayıtlı değilse telefon numarasını oku",
            get = { prefs.isAnnounceNumber() },
            set = { prefs.setAnnounceNumber(it) }
        )
        bindSetting(
            rowId = R.id.row_read_all,
            title = "Tüm birikmiş mesajları oku",
            desc = "Kapalıysa sadece en son mesaj okunur",
            get = { prefs.isReadAllMessages() },
            set = { prefs.setReadAllMessages(it) }
        )
    }

    private fun bindSetting(
        rowId: Int,
        title: String,
        desc: String,
        get: () -> Boolean,
        set: (Boolean) -> Unit
    ) {
        val row = findViewById<View>(rowId)
        row.findViewById<TextView>(R.id.setting_title).text = title
        val descView = row.findViewById<TextView>(R.id.setting_desc)
        descView.text = desc
        descView.visibility = View.VISIBLE
        val sw = row.findViewById<SwitchCompat>(R.id.setting_switch)
        sw.isChecked = get()
        sw.setOnCheckedChangeListener { _, checked -> set(checked) }
        row.setOnClickListener { sw.toggle() }
    }

    private fun updatePermissionStatus() {
        if (isNotificationAccessGranted()) {
            statusText.text = getString(R.string.status_active)
            statusText.setTextColor(getColor(R.color.status_active))
        } else {
            statusText.text = getString(R.string.status_inactive)
            statusText.setTextColor(getColor(R.color.status_inactive))
            showPermissionDialog()
        }
    }

    private fun isNotificationAccessGranted(): Boolean {
        val flat = Settings.Secure.getString(
            contentResolver, "enabled_notification_listeners"
        ) ?: return false
        val cn = ComponentName(this, NotificationReaderService::class.java)
        return flat.split(":").any {
            try { ComponentName.unflattenFromString(it) == cn } catch (_: Exception) { false }
        }
    }

    private fun showPermissionDialog() {
        AlertDialog.Builder(this)
            .setTitle(R.string.permission_title)
            .setMessage(R.string.permission_message)
            .setPositiveButton(R.string.permission_grant) { _, _ ->
                startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
            }
            .setNegativeButton(R.string.permission_cancel, null)
            .setCancelable(false)
            .show()
    }

    private fun loadApps() {
        progressBar.visibility = View.VISIBLE
        recyclerView.visibility = View.GONE
        emptyText.visibility = View.GONE

        CoroutineScope(Dispatchers.IO).launch {
            val pm = packageManager
            val launchIntent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            val apps = pm.queryIntentActivities(launchIntent, 0)
                .map { it.activityInfo.applicationInfo }
                .distinctBy { it.packageName }
                .filter { it.packageName != packageName }
                .sortedBy { pm.getApplicationLabel(it).toString().lowercase() }
                .map { info ->
                    AppInfo(
                        packageName = info.packageName,
                        label = pm.getApplicationLabel(info).toString(),
                        icon = pm.getApplicationIcon(info.packageName),
                        enabled = prefs.isAppEnabled(info.packageName)
                    )
                }

            withContext(Dispatchers.Main) {
                progressBar.visibility = View.GONE
                if (apps.isEmpty()) {
                    emptyText.visibility = View.VISIBLE
                } else {
                    recyclerView.visibility = View.VISIBLE
                    recyclerView.adapter = AppListAdapter(apps) { pkg, enabled ->
                        prefs.setAppEnabled(pkg, enabled)
                    }
                }
            }
        }
    }
}
