package com.bluechip.finance.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bluechip.finance.ui.theme.GradientButton
import com.bluechip.finance.ui.theme.IndigoDeep
import com.bluechip.finance.ui.theme.LocalAppColors
import com.bluechip.finance.util.ChatMessage
import com.bluechip.finance.util.DeepSeekClient
import com.bluechip.finance.util.DeepSeekKeyManager
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.material.icons.filled.Key
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import kotlinx.coroutines.launch

private val quickQuestions = listOf(
    "Bu ay ne kadar harcadim?",
    "Tasarruf onerileri ver",
    "Maas artisi nasil istenir?",
    "Kidem tazminati nedir?",
    "Acil fon ne kadar olmali?",
    "Finansal durumumu analiz et"
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AiAssistantScreen() {
    val context   = LocalContext.current
    val colors    = LocalAppColors.current
    val scope     = rememberCoroutineScope()
    val listState = rememberLazyListState()
    val keyboard  = LocalSoftwareKeyboardController.current

    var hasKey    by remember { mutableStateOf(DeepSeekKeyManager.hasKey(context)) }
    var keyInput  by remember { mutableStateOf("") }
    var keyVisible by remember { mutableStateOf(false) }

    var inputText by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    val history         = remember { mutableStateListOf<ChatMessage>() }
    val displayMessages = remember { mutableStateListOf<Pair<String, Boolean>>() }

    // Key setup screen
    if (!hasKey) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Icon(Icons.Default.Key, null, tint = IndigoDeep, modifier = Modifier.size(56.dp))
            Spacer(Modifier.height(16.dp))
            Text("DeepSeek API Anahtari", fontWeight = FontWeight.Bold, fontSize = 20.sp)
            Spacer(Modifier.height(8.dp))
            Text(
                "AI asistani kullanmak icin kendi API anahtarinizi girin.\n\n" +
                "platform.deepseek.com → API Keys → Create API Key\n\n" +
                "Anahtar sifrelenerek cihazinizda saklanir, hicbir yere gonderilmez.",
                fontSize = 13.sp,
                color = Color.Gray,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center
            )
            Spacer(Modifier.height(24.dp))
            OutlinedTextField(
                value = keyInput,
                onValueChange = { keyInput = it },
                label = { Text("sk-...") },
                placeholder = { Text("API anahtarinizi yapistirin") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                visualTransformation = if (keyVisible) VisualTransformation.None
                                       else PasswordVisualTransformation(),
                trailingIcon = {
                    IconButton(onClick = { keyVisible = !keyVisible }) {
                        Icon(
                            if (keyVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                            null
                        )
                    }
                }
            )
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    if (keyInput.trim().startsWith("sk-")) {
                        DeepSeekKeyManager.saveKey(context, keyInput.trim())
                        hasKey = true
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = keyInput.trim().startsWith("sk-")
            ) {
                Text("Kaydet ve Baslat")
            }
        }
        return
    }

    fun sendMessage(text: String) {
        if (text.isBlank() || isLoading) return
        val userText = text.trim()
        inputText = ""
        keyboard?.hide()
        displayMessages.add(Pair(userText, true))
        isLoading = true
        scope.launch {
            val result = DeepSeekClient.sendMessage(context, history.toList(), userText)
            history.add(ChatMessage("user", userText))
            result.onSuccess { reply ->
                history.add(ChatMessage("assistant", reply))
                displayMessages.add(Pair(reply, false))
            }.onFailure { err ->
                displayMessages.add(Pair("Hata: ${err.message ?: "Bilinmeyen hata"}", false))
            }
            isLoading = false
            if (displayMessages.isNotEmpty()) {
                listState.animateScrollToItem(displayMessages.size - 1)
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        // Header
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(brush = GradientButton)
                .padding(16.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(40.dp)
                        .background(Color.White.copy(alpha = 0.2f), CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Default.SmartToy, null, tint = Color.White, modifier = Modifier.size(24.dp))
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("AI Asistan", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    Text("DeepSeek — Tum verilerinize erisim var", color = Color.White.copy(0.8f), fontSize = 12.sp)
                }
                IconButton(onClick = {
                    DeepSeekKeyManager.clearKey(context)
                    hasKey = false
                    keyInput = ""
                }) {
                    Icon(Icons.Default.Key, "API Key degistir", tint = Color.White.copy(0.7f),
                        modifier = Modifier.size(20.dp))
                }
            }
        }

        // Messages
        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            contentPadding = PaddingValues(vertical = 12.dp)
        ) {
            if (displayMessages.isEmpty()) {
                item {
                    Column(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Spacer(Modifier.height(16.dp))
                        Icon(Icons.Default.SmartToy, null, tint = IndigoDeep, modifier = Modifier.size(64.dp))
                        Spacer(Modifier.height(12.dp))
                        Text("Merhaba! Size nasil yardimci olabilirim?",
                            fontWeight = FontWeight.Medium, fontSize = 16.sp)
                        Spacer(Modifier.height(4.dp))
                        Text("Finansal verilerinize erisimim var.",
                            fontSize = 13.sp, color = Color.Gray)
                        Spacer(Modifier.height(24.dp))
                        Text("Hizli sorular:", fontWeight = FontWeight.Medium,
                            fontSize = 13.sp, color = Color.Gray)
                        Spacer(Modifier.height(8.dp))
                        quickQuestions.chunked(2).forEach { row ->
                            Row(
                                Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                row.forEach { q ->
                                    SuggestionChip(
                                        onClick = { sendMessage(q) },
                                        label = { Text(q, fontSize = 12.sp) },
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                                if (row.size == 1) Spacer(Modifier.weight(1f))
                            }
                            Spacer(Modifier.height(6.dp))
                        }
                    }
                }
            }
            items(displayMessages) { (content, isUser) ->
                AiChatBubble(content = content, isUser = isUser)
            }
            if (isLoading) {
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(32.dp)
                                .background(IndigoDeep, CircleShape),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(Icons.Default.SmartToy, null, tint = Color.White,
                                modifier = Modifier.size(18.dp))
                        }
                        Spacer(Modifier.width(8.dp))
                        Card(shape = RoundedCornerShape(16.dp, 16.dp, 16.dp, 4.dp)) {
                            Box(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                                Text("Dusunuyor...", color = Color.Gray, fontSize = 14.sp)
                            }
                        }
                    }
                }
            }
        }

        // Input area
        Surface(shadowElevation = 8.dp) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.Bottom
            ) {
                OutlinedTextField(
                    value = inputText,
                    onValueChange = { inputText = it },
                    placeholder = { Text("Soru sorun...", fontSize = 14.sp) },
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(24.dp),
                    maxLines = 4,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = { sendMessage(inputText) })
                )
                Spacer(Modifier.width(8.dp))
                FloatingActionButton(
                    onClick = { sendMessage(inputText) },
                    modifier = Modifier.size(48.dp),
                    containerColor = IndigoDeep,
                    contentColor = Color.White,
                    elevation = FloatingActionButtonDefaults.elevation(0.dp)
                ) {
                    Icon(Icons.Default.Send, null, modifier = Modifier.size(20.dp))
                }
            }
        }
    }
}

@Composable
private fun AiChatBubble(content: String, isUser: Boolean) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
        verticalAlignment = Alignment.Top
    ) {
        if (!isUser) {
            Box(
                modifier = Modifier
                    .size(32.dp)
                    .background(IndigoDeep, CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Default.SmartToy, null, tint = Color.White, modifier = Modifier.size(18.dp))
            }
            Spacer(Modifier.width(8.dp))
        }
        Card(
            shape = if (isUser) RoundedCornerShape(16.dp, 16.dp, 4.dp, 16.dp)
                    else        RoundedCornerShape(16.dp, 16.dp, 16.dp, 4.dp),
            colors = CardDefaults.cardColors(
                containerColor = if (isUser) IndigoDeep else MaterialTheme.colorScheme.surface
            ),
            modifier = Modifier.widthIn(max = 280.dp)
        ) {
            Text(
                text = content,
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                color = if (isUser) Color.White else MaterialTheme.colorScheme.onSurface,
                fontSize = 14.sp,
                lineHeight = 20.sp
            )
        }
        if (isUser) {
            Spacer(Modifier.width(8.dp))
            Box(
                modifier = Modifier
                    .size(32.dp)
                    .background(IndigoDeep.copy(0.15f), CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Text("S", fontWeight = FontWeight.Bold, color = IndigoDeep, fontSize = 14.sp)
            }
        }
    }
}
