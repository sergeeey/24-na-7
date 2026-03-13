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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.reflexio.app.domain.network.MemoryApi
import com.reflexio.app.domain.network.SearchEvent
import com.reflexio.app.domain.network.SearchResponse
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private sealed class SearchUiState {
    object Idle : SearchUiState()
    object Loading : SearchUiState()
    data class Success(val data: SearchResponse) : SearchUiState()
    data class Error(val message: String) : SearchUiState()
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SearchScreen(
    baseHttpUrl: String,
    initialQuery: String = "",
    onInitialQueryConsumed: () -> Unit = {},
    onAskAboutEvent: (String) -> Unit,
    onOpenPerson: (String) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    var query by remember(initialQuery) { mutableStateOf(initialQuery) }
    var state by remember { mutableStateOf<SearchUiState>(SearchUiState.Idle) }
    val suggestions = listOf("Марат", "мама", "деньги", "работа", "обещал")

    suspend fun runSearch(input: String) {
        val trimmed = input.trim()
        if (trimmed.isBlank()) {
            state = SearchUiState.Idle
            return
        }
        state = SearchUiState.Loading
        state = try {
            val result = withContext(Dispatchers.IO) {
                MemoryApi.queryEvents(baseHttpUrl, trimmed)
            }
            SearchUiState.Success(result)
        } catch (e: Exception) {
            SearchUiState.Error(e.message ?: "Ошибка поиска")
        }
    }

    LaunchedEffect(initialQuery) {
        if (initialQuery.isNotBlank()) {
            query = initialQuery
            delay(100)
            runSearch(initialQuery)
            onInitialQueryConsumed()
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            text = "Найдите разговор, тему или человека из своей памяти.",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            shape = RoundedCornerShape(18.dp),
            label = { Text("О чём вы говорили?") },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { scope.launch { runSearch(query) } }),
        )

        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            suggestions.forEach { suggestion ->
                AssistChip(
                    onClick = {
                        query = suggestion
                    },
                    label = { Text(suggestion) },
                    colors = AssistChipDefaults.assistChipColors(),
                )
            }
            AssistChip(
                onClick = {},
                label = { Text("Искать") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                enabled = false,
            )
        }

        LaunchedEffect(query) {
            val trimmed = query.trim()
            if (trimmed.isBlank()) {
                state = SearchUiState.Idle
                return@LaunchedEffect
            }
            delay(350)
            if (trimmed == query.trim()) {
                runSearch(trimmed)
            }
        }

        when (val current = state) {
            SearchUiState.Idle -> {
                Text(
                    text = "Быстрый вход в память: найдите разговор, обещание, тему или человека.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            SearchUiState.Loading -> {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.Center,
                ) {
                    CircularProgressIndicator()
                }
            }
            is SearchUiState.Error -> {
                Text(
                    text = current.message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.error,
                )
            }
            is SearchUiState.Success -> {
                if (current.data.events.isEmpty()) {
                    Text(
                        text = "Ничего не найдено. Попробуйте другой запрос или более короткое имя.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    Text(
                        text = "Найдено: ${current.data.total}",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    LazyColumn(
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        items(current.data.events, key = { it.id }) { event ->
                            SearchEventCard(
                                event = event,
                                onAskAboutEvent = onAskAboutEvent,
                                onOpenPerson = onOpenPerson,
                            )
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SearchEventCard(
    event: SearchEvent,
    onAskAboutEvent: (String) -> Unit,
    onOpenPerson: (String) -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f),
        ),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = event.timestamp,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = event.snippet,
                style = MaterialTheme.typography.bodyLarge,
                maxLines = 4,
                overflow = TextOverflow.Ellipsis,
            )
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                event.topTopic?.let {
                    AssistChip(onClick = {}, label = { Text(it) })
                }
                event.people.take(3).forEach { person ->
                    AssistChip(onClick = { onOpenPerson(person) }, label = { Text(person) })
                }
                event.topics.drop(if (event.topTopic != null) 1 else 0).take(2).forEach { topic ->
                    AssistChip(onClick = {}, label = { Text(topic) })
                }
            }
            AssistChip(
                onClick = { onAskAboutEvent("Что важно в разговоре: ${event.snippet.take(80)}?") },
                label = { Text("Спросить об этом") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            )
        }
    }
}
