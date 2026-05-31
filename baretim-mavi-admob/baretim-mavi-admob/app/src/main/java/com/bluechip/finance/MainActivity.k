package com.bluechip.finance

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
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
import com.bluechip.finance.ui.theme.BlueChipTheme
import com.bluechip.finance.ui.theme.LocalAppColors

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)

        // İlk açılışta App Open Ad göster; bittikten sonra UI yükle
        val appOpenAdManager = (application as MyApp).appOpenAdManager
        appOpenAdManager.loadAd()
        appOpenAdManager.showAdIfAvailable(this)

        setContent { BlueChipTheme { BlueChipApp() } }
    }
}

data class NavItem(val route: String, val label: String, val icon: ImageVector)

// Araçlar alt sayfaları
val toolsSubRoutes = setOf("leave", "bordro", "unemployment", "retirement", "inflation", "comparison", "profile")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BlueChipApp() {
    val navController = rememberNavController()
    val colors = LocalAppColors.current
    val items = listOf(
        NavItem("home", "Ana Sayfa", Icons.Default.Home),
        NavItem("overtime", "Mesai", Icons.Default.AccessTime),
        NavItem("severance", "Tazminat", Icons.Default.AccountBalance),
        NavItem("tax", "Vergi", Icons.Default.Receipt),
        NavItem("tools", "Araçlar", Icons.Default.Apps)
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Baretim Mavi", fontWeight = FontWeight.Bold, fontSize = 20.sp, color = colors.textPrimary) },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface)
            )
        },
        bottomBar = {
            Column {
            com.bluechip.finance.ui.components.BannerAd(modifier = Modifier.fillMaxWidth())
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                val navBackStack by navController.currentBackStackEntryAsState()
                val currentRoute = navBackStack?.destination?.route

                items.forEach { item ->
                    val isSelected = if (item.route == "tools") {
                        currentRoute == "tools" || currentRoute in toolsSubRoutes
                    } else {
                        currentRoute == item.route
                    }

                    NavigationBarItem(
                        icon = { Icon(item.icon, item.label) },
                        label = { Text(item.label, fontSize = 10.sp) },
                        selected = isSelected,
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
            composable("profile") { ProfileScreen() }
            }
        }
        }
    }

