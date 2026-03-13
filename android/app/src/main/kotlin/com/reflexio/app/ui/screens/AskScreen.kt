package com.reflexio.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.reflexio.app.domain.network.AskResponseData
import com.reflexio.app.domain.network.MemoryApi
import com.reflexio.app.domain.network.ServerEndpointResolver
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private sealed class AskUiState {
    object Idle : AskUiState()
    object Loading : AskUiState()
    data class Success(val result: AskResponseData) : AskUiState()
    data class Error(val message: String) : AskUiState()
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AskScreen(
    baseHttpUrl: String,
    initialQuestion: String = "",
    onInitialQuestionConsumed: () -> Unit = {},
    onOpenSearch: (String) -> Unit = {},
    onOpenPeople: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    var question by remember(initialQuestion) { mutableStateOf(initialQuestion) }
    var state by remember { mutableStateOf<AskUiState>(AskUiState.Idle) }
    val samples = listOf(
        "Что было сегодня?",
        "Что я обещал?",
        "Какие паттерны?",
        "Что важно по деньгам?",
    )

    fun submit(input: String) {
        val trimmed = input.trim()
        if (trimmed.isBlank()) return
        scope.launch {
            state = AskUiState.Loading
            state = try {
                val result = withContext(Dispatchers.IO) {
                    MemoryApi.ask(baseHttpUrl, trimmed)
                }
                AskUiState.Success(result)
            } catch (e: Exception) {
                AskUiState.Error(ServerEndpointResolver.userFacingError(e.message, baseHttpUrl))
            }
        }
    }

    LaunchedEffect(initialQuestion) {
        if (initialQuestion.isNotBlank()) {
            question = initialQuestion
            submit(initialQuestion)
            onInitialQuestionConsumed()
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.82f),
            ),
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = "Главный вход в память",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    text = "Спроси обычным языком про людей, обещания, темы дня или повторяющиеся линии.",
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }

        OutlinedTextField(
            value = question,
            onValueChange = { question = it },
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
            label = { Text("Спросите что угодно о своём дне") },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { submit(question) }),
        )

        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            samples.forEach { sample ->
                AssistChip(
                    onClick = {
                        question = sample
                        submit(sample)
                    },
                    label = { Text(sample) },
                    leadingIcon = { Icon(Icons.Default.AutoAwesome, contentDescription = null) },
                    colors = AssistChipDefaults.assistChipColors(),
                )
            }
            AssistChip(
                onClick = onOpenPeople,
                label = { Text("Кто рядом?") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                colors = AssistChipDefaults.assistChipColors(),
            )
        }

        when (val current = state) {
            AskUiState.Idle -> {
                Text(
                    text = "Лучше всего работают вопросы про людей, обещания, деньги, повторяющиеся темы и выводы по дню.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            AskUiState.Loading -> {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.Center,
                ) {
                    CircularProgressIndicator()
                }
            }
            is AskUiState.Error -> {
                Text(
                    text = current.message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.error,
                )
            }
            is AskUiState.Success -> {
                AskAnswerView(
                    result = current.result,
                    onOpenSearch = onOpenSearch,
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AskAnswerView(
    result: AskResponseData,
    onOpenSearch: (String) -> Unit,
) {
    LazyColumn(
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.9f),
                ),
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text(
                        text = result.answer,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = "Уверенность: ${result.confidenceLabel} · улик: ${result.evidenceCount}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    result.warning?.let {
                        Text(
                            text = humanizeWarning(it),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                }
            }
        }

        result.digest?.let { digest ->
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text("Слой дайджеста", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                        digest.summaryText?.let {
                            Text(it, style = MaterialTheme.typography.bodyMedium)
                        }
                        if (digest.keyThemes.isNotEmpty() || digest.emotions.isNotEmpty()) {
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                digest.keyThemes.take(4).forEach { theme ->
                                    AssistChip(onClick = { onOpenSearch(theme) }, label = { Text(theme) })
                                }
                                digest.emotions.take(2).forEach { emotion ->
                                    AssistChip(onClick = {}, label = { Text(emotion) })
                                }
                            }
                        }
                        digest.balance?.let { balance ->
                            Text(
                                text = "Баланс: ${"%.2f".format(balance.balanceScore)}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.secondary,
                            )
                            balance.domains.take(3).forEach { domain ->
                                Text(
                                    text = "${domain.domain}: ${"%.1f".format(domain.score)}/10",
                                    style = MaterialTheme.typography.bodySmall,
                                )
                            }
                        }
                    }
                }
            }
        }

        result.events?.let { events ->
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text("Слой событий", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                        Text(
                            text = "Найдено событий: ${events.total}",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            events.topTopics.forEach { topic ->
                                AssistChip(
                                    onClick = { onOpenSearch(topic) },
                                    label = { Text(topic) },
                                )
                            }
                        }
                    }
                }
            }
        }

        if (result.evidenceMetadata.isNotEmpty()) {
            item {
                Text("Улики", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            }
            items(result.evidenceMetadata, key = { it.id }) { evidence ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                ) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(
                            text = evidence.timestamp,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.primary,
                        )
                        Text(
                            text = evidence.topTopic.ifBlank { "Событие" },
                            style = MaterialTheme.typography.bodyMedium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        AssistChip(
                            onClick = { onOpenSearch(evidence.topTopic.ifBlank { evidence.timestamp }) },
                            label = { Text("Открыть похожее") },
                        )
                    }
                }
            }
        }
    }
}

private fun humanizeWarning(warning: String): String {
    val normalized = warning.lowercase()
    return if ("мало данных" in normalized || "недостаточно данных" in normalized) {
        "За выбранный период пока мало осмысленных записей. Попробуй спросить про вчера, про человека или про более длинный период."
    } else {
        warning
    }
}
