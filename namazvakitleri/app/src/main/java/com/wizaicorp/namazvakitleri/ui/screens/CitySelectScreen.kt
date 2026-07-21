package com.wizaicorp.namazvakitleri.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.wizaicorp.namazvakitleri.api.AladhanApi
import com.wizaicorp.namazvakitleri.data.City
import com.wizaicorp.namazvakitleri.data.Lang
import kotlinx.coroutines.launch

@Composable
fun CitySelectScreen(
    selectedCity: City,
    onCitySelected: (City) -> Unit,
    onBack: () -> Unit
) {
    var cityInput    by remember { mutableStateOf("") }
    var countryInput by remember { mutableStateOf("Turkey") }
    var isSearching  by remember { mutableStateOf(false) }
    var foundCity    by remember { mutableStateOf<City?>(null) }
    var error        by remember { mutableStateOf<String?>(null) }
    val scope        = rememberCoroutineScope()
    val cityFocus    = remember { FocusRequester() }

    fun search() {
        val city    = cityInput.trim()
        val country = countryInput.trim().ifBlank { "Turkey" }
        if (city.isBlank()) return
        scope.launch {
            isSearching = true
            error       = null
            foundCity   = null
            try {
                AladhanApi.getPrayerTimes(city, country)
                foundCity = City(city, city, country)
            } catch (e: Exception) {
                error = Lang.get("city_not_found")
            } finally {
                isSearching = false
            }
        }
    }

    FeatureScaffold(title = Lang.get("city_search"), onBack = onBack) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            OutlinedTextField(
                value         = cityInput,
                onValueChange = { cityInput = it; foundCity = null; error = null },
                label         = { Text(Lang.get("city_label")) },
                placeholder   = { Text(Lang.get("city_hint")) },
                modifier      = Modifier.fillMaxWidth().focusRequester(cityFocus),
                singleLine    = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next)
            )

            OutlinedTextField(
                value         = countryInput,
                onValueChange = { countryInput = it; foundCity = null; error = null },
                label         = { Text(Lang.get("country_label")) },
                placeholder   = { Text(Lang.get("country_hint")) },
                modifier      = Modifier.fillMaxWidth(),
                singleLine    = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { search() })
            )

            Button(
                onClick  = { search() },
                modifier = Modifier.fillMaxWidth(),
                enabled  = cityInput.isNotBlank() && !isSearching
            ) {
                if (isSearching) {
                    CircularProgressIndicator(
                        modifier    = Modifier.size(20.dp),
                        strokeWidth = 2.dp,
                        color       = MaterialTheme.colorScheme.onPrimary
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(Lang.get("searching"))
                } else {
                    Icon(Icons.Default.Search, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text(Lang.get("search"))
                }
            }

            error?.let {
                Surface(
                    shape    = MaterialTheme.shapes.medium,
                    color    = MaterialTheme.colorScheme.errorContainer,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text     = it,
                        modifier = Modifier.padding(12.dp),
                        color    = MaterialTheme.colorScheme.onErrorContainer
                    )
                }
            }

            foundCity?.let { city ->
                Surface(
                    shape    = MaterialTheme.shapes.medium,
                    color    = MaterialTheme.colorScheme.primaryContainer,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text       = "${city.name}, ${city.country}",
                            style      = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color      = MaterialTheme.colorScheme.onPrimaryContainer
                        )
                        Spacer(Modifier.height(12.dp))
                        Button(
                            onClick  = { onCitySelected(city) },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(Lang.get("select_this_city"))
                        }
                    }
                }
            }

            Spacer(Modifier.weight(1f))

            Text(
                text     = "${Lang.get("current_city")}: ${selectedCity.name}, ${selectedCity.country}",
                style    = MaterialTheme.typography.bodySmall,
                color    = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                modifier = Modifier.align(Alignment.CenterHorizontally)
            )
        }
    }

    LaunchedEffect(Unit) { cityFocus.requestFocus() }
}
