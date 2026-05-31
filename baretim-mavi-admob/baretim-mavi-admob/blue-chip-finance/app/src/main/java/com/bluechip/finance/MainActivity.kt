package com.bluechip.finance

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.bluechip.finance.ui.screens.*
import com.bluechip.finance.ui.theme.BlueChipTheme
import com.bluechip.finance.viewmodel.NewsViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent {
            BlueChipTheme {
                BlueChipApp()
            }
        }
    }
}

data class NavItem(val route: String, val label: String, val icon: ImageVector)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BlueChipApp() {
    val navController = rememberNavController()
    val newsViewModel: NewsViewModel = viewModel()
    
    val items = listOf(
        NavItem("home", "Ana Sayfa", Icons.Default.Home),
        NavItem("overtime", "Mesai", Icons.Default.History),
        NavItem("severance", "Tazminat", Icons.Default.Payments),
        NavItem("tax", "Vergi", Icons.Default.ReceiptLong),
        NavItem("leave", "İzin", Icons.Default.Event)
    )

    Scaffold(
        bottomBar = {
            NavigationBar {
                val navBackStackEntry by navController.currentBackStackEntryAsState()
                val currentRoute = navBackStackEntry?.destination?.route
                items.forEach { item ->
                    NavigationBarItem(
                        icon = { Icon(item.icon, contentDescription = item.label) },
                        label = { Text(item.label, fontSize = 10.sp) },
                        selected = currentRoute == item.route,
                        onClick = {
                            navController.navigate(item.route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        }
                    )
                }
            }
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = "home",
            modifier = Modifier.padding(innerPadding)
        ) {
            // BURASI ÖNEMLİ: HomeScreen artık viewModel bekliyor.
            composable("home") { 
                HomeScreen(viewModel = newsViewModel) 
            }
            composable("overtime") { OvertimeScreen() }
            composable("severance") { SeveranceScreen() }
            composable("tax") { TaxScreen() }
            composable("leave") { AnnualLeaveScreen() }
        }
    }
}
