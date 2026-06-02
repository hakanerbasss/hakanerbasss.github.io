package com.bluechip.finance.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.ui.theme.*

@Composable
fun SectionHeader(title: String, icon: ImageVector? = null, onInfoClick: (() -> Unit)? = null, onRefreshClick: (() -> Unit)? = null) {
    val colors = LocalAppColors.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (icon != null) {
            Icon(icon, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(24.dp))
            Spacer(modifier = Modifier.width(8.dp))
        }
        Text(title, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = colors.textPrimary, modifier = Modifier.weight(1f))
        if (onRefreshClick != null) {
            IconButton(onClick = onRefreshClick) {
                Icon(Icons.Default.Refresh, "Güncelle", tint = MaterialTheme.colorScheme.primary)
            }
        }
        if (onInfoClick != null) {
            IconButton(onClick = onInfoClick) {
                Icon(Icons.Default.Info, "Bilgi", tint = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

@Composable
fun CurrencyField(value: String, onValueChange: (String) -> Unit, label: String, modifier: Modifier = Modifier) {
    OutlinedTextField(
        value = value,
        onValueChange = { new -> if (new.isEmpty() || new.matches(Regex("^\\d*\\.?\\d{0,2}$"))) onValueChange(new) },
        label = { Text(label) },
        leadingIcon = { Text("₺", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = MaterialTheme.colorScheme.primary) },
        modifier = modifier.fillMaxWidth(),
        singleLine = true,
        shape = RoundedCornerShape(12.dp)
    )
}

@Composable
fun NumberField(value: String, onValueChange: (String) -> Unit, label: String, modifier: Modifier = Modifier) {
    OutlinedTextField(
        value = value,
        onValueChange = { new -> if (new.isEmpty() || new.matches(Regex("^\\d*\\.?\\d*$"))) onValueChange(new) },
        label = { Text(label) },
        modifier = modifier.fillMaxWidth(),
        singleLine = true,
        shape = RoundedCornerShape(12.dp)
    )
}

@Composable
fun ActionButtons(onCalculate: () -> Unit, onReset: () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Button(
            onClick = onCalculate,
            modifier = Modifier.weight(1f).height(52.dp),
            shape = RoundedCornerShape(12.dp)
        ) {
            Icon(Icons.Default.Calculate, null, modifier = Modifier.size(20.dp))
            Spacer(modifier = Modifier.width(8.dp))
            Text("HESAPLA", fontWeight = FontWeight.Bold)
        }
        OutlinedButton(
            onClick = onReset,
            modifier = Modifier.weight(1f).height(52.dp),
            shape = RoundedCornerShape(12.dp)
        ) { Text("TEMİZLE") }
    }
}

@Composable
fun ResultCard(visible: Boolean, content: @Composable ColumnScope.() -> Unit) {
    val colors = LocalAppColors.current
    AnimatedVisibility(visible = visible, enter = fadeIn() + expandVertically()) {
        Card(
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
            shape = RoundedCornerShape(16.dp),
            elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
            colors = CardDefaults.cardColors(containerColor = colors.cardGray)
        ) {
            Column(modifier = Modifier.padding(20.dp), content = content)
        }
    }
}

@Composable
fun ResultLine(label: String, value: String, color: Color = LocalAppColors.current.textPrimary, bold: Boolean = false) {
    Text(
        text = "$label $value",
        fontSize = if (bold) 16.sp else 14.sp,
        fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal,
        color = color,
        modifier = Modifier.padding(vertical = 2.dp)
    )
}

@Composable
fun BigResult(label: String, value: String, color: Color = LocalAppColors.current.success) {
    Column(
        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(label, fontSize = 13.sp, color = color)
        Text(value, fontSize = 24.sp, fontWeight = FontWeight.Bold, color = color)
    }
}

@Composable
fun ShareButton(onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp)
    ) { Text("PAYLAŞ 📤") }
}

@Composable
fun DatePickerButton(text: String, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp)
    ) {
        Icon(Icons.Default.DateRange, null, modifier = Modifier.size(20.dp))
        Spacer(modifier = Modifier.width(8.dp))
        Text(text)
    }
}

@Composable
fun SelectorButton(text: String, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp)
    ) { Text(text) }
}

@Composable
fun UpdateStatusBar(lastUpdate: String, onRefresh: () -> Unit) {
    val colors = LocalAppColors.current
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text("📅 Son güncelleme: $lastUpdate", fontSize = 12.sp, color = colors.success, modifier = Modifier.weight(1f))
        IconButton(onClick = onRefresh, modifier = Modifier.size(32.dp)) {
            Icon(Icons.Default.Refresh, "Güncelle", tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
        }
    }
}

fun formatMoney(amount: Double): String {
    return String.format("%,.2f", amount).replace(',', 'X').replace('.', ',').replace('X', '.')
}

fun formatNumber(amount: Double): String {
    return String.format("%,.0f", amount).replace(',', '.')
}
