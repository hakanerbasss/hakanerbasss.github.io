package com.hakanerbasss.notificationreader

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.widget.SwitchCompat
import androidx.recyclerview.widget.RecyclerView

class AppListAdapter(
    private val items: List<AppInfo>,
    private val onToggle: (packageName: String, enabled: Boolean) -> Unit
) : RecyclerView.Adapter<AppListAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val icon: ImageView = view.findViewById(R.id.app_icon)
        val name: TextView = view.findViewById(R.id.app_name)
        val pkg: TextView = view.findViewById(R.id.app_package)
        val toggle: SwitchCompat = view.findViewById(R.id.app_toggle)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_app, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = items[position]
        holder.icon.setImageDrawable(item.icon)
        holder.name.text = item.label
        holder.pkg.text = item.packageName
        holder.toggle.setOnCheckedChangeListener(null)
        holder.toggle.isChecked = item.enabled
        holder.toggle.setOnCheckedChangeListener { _, checked ->
            item.enabled = checked
            onToggle(item.packageName, checked)
        }
        holder.itemView.setOnClickListener {
            holder.toggle.toggle()
        }
    }

    override fun getItemCount() = items.size
}
