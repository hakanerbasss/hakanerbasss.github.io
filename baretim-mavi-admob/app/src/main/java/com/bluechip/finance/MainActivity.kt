package com.bluechip.finance

import android.os.Bundle
import com.google.android.play.core.review.ReviewManagerFactory
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Alignment
import androidx.compose.ui.unit.dp
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.bluechip.finance.ui.screens.*
import com.bluechip.finance.util.calcMoodEmoji
import com.bluechip.finance.ui.theme.BlueChipTheme
import com.bluechip.finance.ui.theme.LocalAppColors

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)

        // Unity Ads init
        UnityAdsManager.init(this)
        NotificationWorker.createChannels(this)
        NotificationWorker.schedule(this)
        // Android 13+ bildirim izni iste
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            if (androidx.core.content.ContextCompat.checkSelfPermission(this,
                    android.Manifest.permission.POST_NOTIFICATIONS) !=
                    android.content.pm.PackageManager.PERMISSION_GRANTED) {
                androidx.core.app.ActivityCompat.requestPermissions(this,
                    arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 101)
            }
        }
        // Tam alarm izni iste (Android 12+)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            val am = getSystemService(android.app.AlarmManager::class.java)
            if (!am.canScheduleExactAlarms()) {
                val intent = android.content.Intent(
                    android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                    android.net.Uri.parse("package:$packageName")
                )
                startActivity(intent)
            }
        }
        // In-App Review: 5. acilista native Play yorum popup'i goster
        val reviewPrefs = getSharedPreferences("review_prefs", MODE_PRIVATE)
        val launchCount = reviewPrefs.getInt("launch_count", 0) + 1
        reviewPrefs.edit().putInt("launch_count", launchCount).apply()
        if (launchCount == 5 || launchCount == 15 || launchCount == 30) {
            val reviewManager = ReviewManagerFactory.create(this)
            val request = reviewManager.requestReviewFlow()
            request.addOnCompleteListener { task ->
                if (task.isSuccessful) {
                    val reviewInfo = task.result
                    reviewManager.launchReviewFlow(this, reviewInfo)
                }
            }
        }

        setContent { BlueChipTheme { BlueChipApp() } }
    }

    override fun onResume() {
        super.onResume()
    }

    override fun onPause() {
        super.onPause()
    }
}

data class NavItem(val route: String, val label: String, val icon: ImageVector?)

// Araçlar alt sayfaları
val toolsSubRoutes = setOf("leave", "bordro", "unemployment", "retirement", "inflation", "comparison", "profile", "rights", "payments", "savings", "overtime_track")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BlueChipApp() {
    val navController = rememberNavController()
    val colors = LocalAppColors.current
    val context = androidx.compose.ui.platform.LocalContext.current
    val activity = context as? android.app.Activity
    var showRewardedDialog by remember { mutableStateOf(false) }
    var showSupportDialog by remember { mutableStateOf(false) }
    var adFreeActive   by remember { mutableStateOf(com.bluechip.finance.data.AdFreeManager.isAdFree(context)) }
    var remainingDays  by remember { mutableStateOf(if (com.bluechip.finance.data.AdFreeManager.isAdFree(context)) com.bluechip.finance.data.AdFreeManager.remainingDays(context) else 0) }
    // Dinamik mood emoji (maaş gününe göre)
    val moodEmoji = remember { calcMoodEmoji(context) }
    val items = listOf(
        NavItem("overtime",  "Mesai",    Icons.Default.AccessTime),
        NavItem("severance", "Tazminat", Icons.Default.AccountBalance),
        NavItem("home",      "",         null),   // merkez — emoji
        NavItem("tax",       "Vergi",    Icons.Default.Receipt),
        NavItem("tools",     "Araçlar",  Icons.Default.Apps)
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Baretim Mavi", fontWeight = FontWeight.Bold, fontSize = 20.sp, color = colors.textPrimary) },
                actions = {
                    if (adFreeActive) {
                        androidx.compose.foundation.layout.Box(
                            modifier = androidx.compose.ui.Modifier
                                .background(
                                    colors.success.copy(alpha = 0.15f),
                                    androidx.compose.foundation.shape.RoundedCornerShape(20.dp)
                                )
                                .clickable { showRewardedDialog = true }
                                .padding(horizontal = 10.dp, vertical = 5.dp)
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("✨", fontSize = 13.sp)
                                Spacer(androidx.compose.ui.Modifier.width(4.dp))
                                Text("${remainingDays}g Reklamsız", fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold, color = colors.success)
                            }
                        }
                    } else {
                        androidx.compose.foundation.layout.Box(
                            modifier = androidx.compose.ui.Modifier
                                .background(
                                    androidx.compose.ui.graphics.Color(0xFFFFB300).copy(alpha = 0.15f),
                                    androidx.compose.foundation.shape.RoundedCornerShape(20.dp)
                                )
                                .clickable { showRewardedDialog = true }
                                .padding(horizontal = 10.dp, vertical = 5.dp)
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("⭐", fontSize = 13.sp)
                                Spacer(androidx.compose.ui.Modifier.width(4.dp))
                                Text("Reklamsız", fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = androidx.compose.ui.graphics.Color(0xFFFFB300))
                            }
                        }
                    }
                    Spacer(androidx.compose.ui.Modifier.width(4.dp))
                    androidx.compose.foundation.layout.Box(
                        modifier = androidx.compose.ui.Modifier
                            .background(
                                androidx.compose.ui.graphics.Color(0xFF9C27B0).copy(alpha = 0.15f),
                                androidx.compose.foundation.shape.RoundedCornerShape(20.dp)
                            )
                            .clickable { showSupportDialog = true }
                            .padding(horizontal = 10.dp, vertical = 5.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("❤️", fontSize = 13.sp)
                            Spacer(androidx.compose.ui.Modifier.width(4.dp))
                            Text("Destek", fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = androidx.compose.ui.graphics.Color(0xFF9C27B0))
                        }
                    }
                    Spacer(androidx.compose.ui.Modifier.width(4.dp))
                    IconButton(onClick = { navController.navigate("notif_settings") }) {
                        Icon(androidx.compose.material.icons.Icons.Filled.NotificationsNone, contentDescription = null)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface)
            )
        },
        bottomBar = {
            Column {
            com.bluechip.finance.ui.components.BannerAd(modifier = Modifier.fillMaxWidth())
            NavigationBar(
                containerColor = MaterialTheme.colorScheme.surface,
                tonalElevation = 0.dp,
                modifier = androidx.compose.ui.Modifier
                    .fillMaxWidth()
            ) {
                val navBackStack by navController.currentBackStackEntryAsState()
                val currentRoute = navBackStack?.destination?.route

                items.forEach { item ->
                    val isSelected = if (item.route == "tools") {
                        currentRoute == "tools" || currentRoute in toolsSubRoutes
                    } else {
                        currentRoute == item.route
                    }

                    NavigationBarItem(
                        icon = {
                            if (item.route == "home") {
                                // Merkez FAB tarzı emoji butonu
                                Box(
                                    modifier = androidx.compose.ui.Modifier
                                        .size(52.dp)
                                        .background(
                                            com.bluechip.finance.ui.theme.PurplePrimary.copy(alpha = 0.10f),
                                            androidx.compose.foundation.shape.CircleShape
                                        )
                                        .then(
                                            if (isSelected)
                                                androidx.compose.ui.Modifier.border(
                                                    2.dp,
                                                    com.bluechip.finance.ui.theme.PurplePrimary,
                                                    androidx.compose.foundation.shape.CircleShape
                                                )
                                            else
                                                androidx.compose.ui.Modifier.border(
                                                    1.5f.dp,
                                                    MaterialTheme.colorScheme.onSurface.copy(alpha = 0.2f),
                                                    androidx.compose.foundation.shape.CircleShape
                                                )
                                        ),
                                    contentAlignment = androidx.compose.ui.Alignment.Center
                                ) {
                                    Text(moodEmoji, fontSize = 34.sp, lineHeight = 38.sp)
                                }
                            } else {
                            Box(
                                modifier = androidx.compose.ui.Modifier
                                    .then(if (isSelected) androidx.compose.ui.Modifier
                                        .background(
                                            com.bluechip.finance.ui.theme.PurplePrimary.copy(alpha = 0.12f),
                                            androidx.compose.foundation.shape.RoundedCornerShape(12.dp)
                                        )
                                        .padding(horizontal = 16.dp, vertical = 6.dp)
                                    else androidx.compose.ui.Modifier.padding(horizontal = 8.dp, vertical = 6.dp)),
                                contentAlignment = androidx.compose.ui.Alignment.Center
                            ) {
                                Icon(item.icon!!, item.label,
                                    tint = if (isSelected) com.bluechip.finance.ui.theme.PurplePrimary
                                           else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                            }
                            } // end if home
                        },
                        label = { Text(item.label, fontSize = 10.sp,
                            color = if (isSelected) com.bluechip.finance.ui.theme.PurplePrimary
                                    else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f)) },
                        selected = isSelected,
                        colors = NavigationBarItemDefaults.colors(
                            indicatorColor = androidx.compose.ui.graphics.Color.Transparent
                        ),
                        onClick = {
                            if (item.route == "tools") {
                                if (currentRoute in toolsSubRoutes) {
                                    navController.popBackStack("tools", inclusive = false)
                                } else if (currentRoute != "tools") {
                                    navController.navigate("tools") {
                                        popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                }
                            } else {
                                if (currentRoute != item.route) {
                                    navController.navigate(item.route) {
                                        popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                }
                            }
                        }
                    )
                }
            }
            }
        }
    ) { padding ->

        // Ödüllü reklam dialog
        if (showRewardedDialog) {
            androidx.compose.ui.window.Dialog(onDismissRequest = { showRewardedDialog = false }) {
                Card(
                    shape = androidx.compose.foundation.shape.RoundedCornerShape(24.dp),
                    colors = CardDefaults.cardColors(containerColor = colors.cardBg),
                    elevation = CardDefaults.cardElevation(8.dp)
                ) {
                    Column(
                        modifier = androidx.compose.ui.Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        // İkon
                        androidx.compose.foundation.layout.Box(
                            modifier = androidx.compose.ui.Modifier
                                .size(72.dp)
                                .background(
                                    androidx.compose.ui.graphics.Color(0xFFFFB300).copy(alpha = 0.15f),
                                    androidx.compose.foundation.shape.CircleShape
                                ),
                            contentAlignment = Alignment.Center
                        ) { Text("⭐", fontSize = 36.sp) }

                        Text("Reklamsız Mod ⭐", fontWeight = FontWeight.Bold,
                            fontSize = 20.sp, color = colors.textPrimary)

                        // Geri sayım kartı
                        if (adFreeActive) {
                            Card(
                                shape = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
                                colors = CardDefaults.cardColors(
                                    containerColor = colors.success.copy(alpha = 0.1f)
                                )
                            ) {
                                Column(modifier = androidx.compose.ui.Modifier.padding(16.dp),
                                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text("✅", fontSize = 24.sp)
                                        Spacer(androidx.compose.ui.Modifier.width(12.dp))
                                        Column {
                                            Text("Aktif!", fontWeight = FontWeight.Bold,
                                                color = colors.success, fontSize = 15.sp)
                                            Text("$remainingDays gün kaldı 🎉",
                                                fontSize = 13.sp, color = colors.textSecondary)
                                        }
                                    }
                                    // Süreyi uzat butonu (max 30 güne kadar)
                                    if (remainingDays < 30) {
                                        Button(
                                            onClick = {
                                                showRewardedDialog = false
                                                activity?.let { act ->
                                                    UnityAdsManager.showRewarded(
                                                        activity = act,
                                                        onRewarded = {
                                                            com.bluechip.finance.data.AdFreeManager.activate(context)
                                                            adFreeActive = true
                                                            remainingDays = com.bluechip.finance.data.AdFreeManager.remainingDays(context)
                                                            android.widget.Toast.makeText(context,
                                                                "+3 gun eklendi! Toplam: $remainingDays gun", android.widget.Toast.LENGTH_LONG).show()
                                                        },
                                                        onNotReady = {
                                                            android.widget.Toast.makeText(context,
                                                                "Reklam hazir degil, bekleyin.", android.widget.Toast.LENGTH_SHORT).show()
                                                        }
                                                    )
                                                }
                                            },
                                            modifier = androidx.compose.ui.Modifier.fillMaxWidth(),
                                            shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
                                            colors = ButtonDefaults.buttonColors(
                                                containerColor = androidx.compose.ui.graphics.Color(0xFFFFB300)
                                            )
                                        ) { Text("▶ +3 Gün İzle (max 30g)", fontWeight = FontWeight.Bold,
                                            color = androidx.compose.ui.graphics.Color.White) }
                                    } else {
                                        Text("🏆 Maksimum süreye ulaştınız!", fontSize = 12.sp,
                                            color = colors.success,
                                            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                                    }
                                }
                            }
                        } else {
                            Card(
                                shape = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
                                colors = CardDefaults.cardColors(
                                    containerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.08f)
                                )
                            ) {
                                Column(modifier = androidx.compose.ui.Modifier.padding(16.dp),
                                    verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Row { Text("🎬", fontSize = 16.sp); Spacer(androidx.compose.ui.Modifier.width(8.dp)); Text("Kısa bir video izle", fontSize = 13.sp, color = colors.textPrimary) }
                                    Row { Text("🚫", fontSize = 16.sp); Spacer(androidx.compose.ui.Modifier.width(8.dp)); Text("Her izleme +3 gün (max 30)", fontSize = 13.sp, color = colors.textPrimary) }
                                    Row { Text("⚡", fontSize = 16.sp); Spacer(androidx.compose.ui.Modifier.width(8.dp)); Text("Reklam hazır değilse sayılmaz", fontSize = 13.sp, color = colors.textSecondary) }
                                }
                            }
                        }

                        // Butonlar
                        Row(
                            modifier = androidx.compose.ui.Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            OutlinedButton(
                                onClick = { showRewardedDialog = false },
                                modifier = androidx.compose.ui.Modifier.weight(1f),
                                shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)
                            ) { Text("Kapat") }
                            if (!adFreeActive) {
                                Button(
                                    onClick = {
                                        showRewardedDialog = false
                                        activity?.let { act ->
                                            UnityAdsManager.showRewarded(
                                                activity = act,
                                                onRewarded = {
                                                    com.bluechip.finance.data.AdFreeManager.activate(context)
                                                    adFreeActive = true
                                                    remainingDays = com.bluechip.finance.data.AdFreeManager.remainingDays(context)
                                                    android.widget.Toast.makeText(context,
                                                        "Tebrikler! 3 gun reklamsiz!", android.widget.Toast.LENGTH_LONG).show()
                                                },
                                                onNotReady = {
                                                    android.widget.Toast.makeText(context,
                                                        "Reklam hazir degil, bekleyin.", android.widget.Toast.LENGTH_SHORT).show()
                                                }
                                            )
                                        }
                                    },
                                    modifier = androidx.compose.ui.Modifier.weight(1f),
                                    shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
                                    colors = ButtonDefaults.buttonColors(
                                        containerColor = androidx.compose.ui.graphics.Color(0xFFFFB300)
                                    )
                                ) { Text("⭐ İzle", fontWeight = FontWeight.Bold, color = androidx.compose.ui.graphics.Color.White) }
                            }
                        }
                    }
                }
            }
        }

        if (showSupportDialog) {
            androidx.compose.ui.window.Dialog(onDismissRequest = { showSupportDialog = false }) {
                com.bluechip.finance.ui.components.SupportUsCard(
                    visible = true,
                    forceShow = true,
                    onForceDismiss = { showSupportDialog = false }
                )
            }
        }

        Column(modifier = Modifier.padding(padding).fillMaxSize()) {
        NavHost(navController, startDestination = "home", modifier = Modifier.weight(1f)) {
            composable("home") { HomeScreen(onNavigate = { route ->
                navController.navigate(route) {
                    popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                    launchSingleTop = true; restoreState = true
                }
            }) }
            composable("overtime") { OvertimeScreen() }
            composable("severance") { SeveranceScreen() }
            composable("tax") { TaxScreen() }
            composable("tools") { ToolsScreen(onNavigate = { navController.navigate(it) }) }
            composable("leave") { AnnualLeaveScreen() }
            composable("bordro") { BordroScreen() }
            composable("unemployment") { UnemploymentScreen() }
            composable("retirement") { RetirementScreen() }
            composable("inflation") { InflationScreen() }
            composable("comparison") { ComparisonScreen() }
            composable("profile") { ProfileScreen(onNavigate = { navController.navigate(it) }) }
            composable("profile_income") { ProfileScreen(onNavigate = { navController.navigate(it) }, autoAddIncome = true) }
            composable("rights") { RightsScreen() }
            composable("payments") { PaymentScreen() }
            composable("payments_add") { PaymentScreen(autoAdd = true) }
            composable("savings")  { SavingsScreen() }
            composable("notif_settings") { com.bluechip.finance.ui.screens.NotificationSettingsScreen(onBack = { navController.popBackStack() }) }
            composable("special_days") { com.bluechip.finance.ui.screens.SpecialDaysScreen(onBack = { navController.popBackStack() }) }
            composable("special_days_add") { com.bluechip.finance.ui.screens.SpecialDaysScreen(onBack = { navController.popBackStack() }, autoAdd = true) }
            composable("overtime_track") { com.bluechip.finance.ui.screens.OvertimeTrackScreen() }
            }
        }
        }
    }

