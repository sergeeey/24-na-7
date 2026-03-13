package com.reflexio.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.reflexio.app.domain.network.MemoryApi
import com.reflexio.app.domain.network.PendingApproval
import com.reflexio.app.domain.network.PersonListItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// ПОЧЕМУ: цвета как файловые константы — переиспользуются в двух приватных Composable,
// совпадают с палитрой остальных экранов (SearchScreen, ThreadsScreen)
private val IndigoAccent = Color(0xFF7C6CFF)
private val TealAccent = Color(0xFF00E5CC)

private sealed class PeopleUiState {
    object Loading : PeopleUiState()
    data class Error(val message: String) : PeopleUiState()
    data class Success(
        val persons: List<PersonListItem>,
        val pending: List<PendingApproval>,
    ) : PeopleUiState()
}

/**
 * Экран "Люди" — социальный граф пользователя.
 *
 * Отображает список известных людей и коллапсируемую секцию ожидающих подтверждения.
 * Approve/Reject обрабатываются немедленно через MemoryApi; после действия pending обновляется.
 */
@Composable
fun PeopleScreen(
    baseHttpUrl: String,
    onOpenPerson: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf<PeopleUiState>(PeopleUiState.Loading) }

    // ПОЧЕМУ: reload вынесен как локальная suspend-функция — вызывается и при старте (LaunchedEffect)
    // и после каждого approve/reject, чтобы оба списка всегда были актуальны
    suspend fun reload() {
        state = PeopleUiState.Loading
        state = try {
            val persons = withContext(Dispatchers.IO) { MemoryApi.fetchPersons(baseHttpUrl) }
            val pending = withContext(Dispatchers.IO) { MemoryApi.fetchPending(baseHttpUrl) }
            PeopleUiState.Success(persons, pending)
        } catch (e: Exception) {
            PeopleUiState.Error(e.message ?: "Не удалось загрузить данные")
        }
    }

    LaunchedEffect(baseHttpUrl) { reload() }

    when (val current = state) {
        PeopleUiState.Loading -> Box(
            modifier = modifier.fillMaxSize(),
            contentAlignment = Alignment.Center,
        ) {
            CircularProgressIndicator(color = IndigoAccent)
        }

        is PeopleUiState.Error -> Box(
            modifier = modifier.fillMaxSize(),
            contentAlignment = Alignment.Center,
        ) {
            Text(current.message, color = MaterialTheme.colorScheme.error)
        }

        is PeopleUiState.Success -> LazyColumn(
            modifier = modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item { Box(modifier = Modifier.padding(top = 8.dp)) }

            // Секция ожидающих подтверждения — коллапсируемая
            item {
                PendingSection(
                    pending = current.pending,
                    onApprove = { approval ->
                        scope.launch {
                            try {
                                withContext(Dispatchers.IO) {
                                    MemoryApi.approvePerson(baseHttpUrl, approval.name)
                                }
                                reload()
                            } catch (_: Exception) { /* молча — сервер мог уже обработать */ }
                        }
                    },
                    onReject = { approval ->
                        scope.launch {
                            try {
                                withContext(Dispatchers.IO) {
                                    MemoryApi.rejectPerson(baseHttpUrl, approval.name)
                                }
                                reload()
                            } catch (_: Exception) { }
                        }
                    },
                )
            }

            if (current.persons.isNotEmpty()) {
                item {
                    Text(
                        text = "Все люди (${current.persons.size})",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 4.dp, start = 4.dp),
                    )
                }
            }

            if (current.persons.isEmpty()) {
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(18.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f),
                        ),
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            Text("Социальный граф пуст", fontWeight = FontWeight.SemiBold)
                            Text(
                                "Люди появятся здесь после того как система распознает голоса из записей.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            } else {
                items(current.persons, key = { it.name }) { person ->
                    PersonListCard(person = person, onClick = { onOpenPerson(person.name) })
                }
            }

            item { Box(modifier = Modifier.padding(bottom = 16.dp)) }
        }
    }
}

/**
 * Коллапсируемая секция "Ожидают подтверждения".
 * Раскрыта по умолчанию если есть записи; свёрнута если pending пуст.
 */
@Composable
private fun PendingSection(
    pending: List<PendingApproval>,
    onApprove: (PendingApproval) -> Unit,
    onReject: (PendingApproval) -> Unit,
) {
    // ПОЧЕМУ: remember(pending.size) — раскрываем секцию автоматически когда появляются
    // новые записи (например после фонового обновления), но не сворачиваем при удалении
    var expanded by remember(pending.size) { mutableStateOf(pending.isNotEmpty()) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.72f),
        ),
    ) {
        Column {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { expanded = !expanded }
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("Ожидают подтверждения", fontWeight = FontWeight.SemiBold)
                    if (pending.isNotEmpty()) {
                        AssistChip(
                            onClick = {},
                            label = { Text("${pending.size}") },
                            colors = AssistChipDefaults.assistChipColors(
                                containerColor = IndigoAccent.copy(alpha = 0.2f),
                                labelColor = IndigoAccent,
                            ),
                        )
                    }
                }
                Icon(
                    imageVector = if (expanded) Icons.Default.KeyboardArrowUp else Icons.Default.KeyboardArrowDown,
                    contentDescription = if (expanded) "Свернуть" else "Развернуть",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            AnimatedVisibility(
                visible = expanded,
                enter = expandVertically(),
                exit = shrinkVertically(),
            ) {
                Column(
                    modifier = Modifier
                        .padding(horizontal = 12.dp)
                        .padding(bottom = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    if (pending.isEmpty()) {
                        Text(
                            "Нет новых голосов для идентификации.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(4.dp),
                        )
                    } else {
                        pending.forEach { approval ->
                            PendingApprovalCard(
                                approval = approval,
                                onApprove = { onApprove(approval) },
                                onReject = { onReject(approval) },
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * Карточка одного ожидающего подтверждения человека.
 */
@Composable
private fun PendingApprovalCard(
    approval: PendingApproval,
    onApprove: () -> Unit,
    onReject: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        // ПОЧЕМУ: secondaryContainer сигнализирует "требует внимания" без агрессивного цвета
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.72f),
        ),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    text = approval.name,
                    fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.bodyLarge,
                )
                Text(
                    text = "Образцов: ${approval.sampleCount} · уверенность: ${"%.0f".format(approval.avgConfidence * 100)}%",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Row {
                // ПОЧЕМУ: IconButton компактнее Button в строке и достаточно для бинарного выбора
                IconButton(onClick = onApprove) {
                    Icon(
                        imageVector = Icons.Default.Check,
                        contentDescription = "Подтвердить",
                        tint = TealAccent,
                        modifier = Modifier.size(24.dp),
                    )
                }
                IconButton(onClick = onReject) {
                    Icon(
                        imageVector = Icons.Default.Close,
                        contentDescription = "Отклонить",
                        tint = MaterialTheme.colorScheme.error,
                        modifier = Modifier.size(24.dp),
                    )
                }
            }
        }
    }
}

/**
 * Карточка одного известного человека из социального графа.
 */
@Composable
private fun PersonListCard(
    person: PersonListItem,
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f),
        ),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = person.name,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleMedium,
                )
                // ПОЧЕМУ: teal-чип для voice_ready — ключевая фича Reflexio,
                // вынесен в угол чтобы статус был заметен с первого взгляда
                if (person.voiceReady) {
                    AssistChip(
                        onClick = {},
                        label = { Text("voice", style = MaterialTheme.typography.labelSmall) },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = TealAccent.copy(alpha = 0.18f),
                            labelColor = TealAccent,
                        ),
                    )
                }
            }

            if (person.relationship.isNotBlank() && person.relationship != "unknown") {
                AssistChip(
                    onClick = {},
                    label = { Text(person.relationship) },
                    colors = AssistChipDefaults.assistChipColors(
                        containerColor = IndigoAccent.copy(alpha = 0.15f),
                        labelColor = IndigoAccent,
                    ),
                )
            }

            person.lastSeen?.takeIf { it.isNotBlank() }?.let { date ->
                Text(
                    text = "Последний раз: ${date.take(10)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
