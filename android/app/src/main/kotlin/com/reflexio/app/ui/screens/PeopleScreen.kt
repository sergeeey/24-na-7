package com.reflexio.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import android.content.Context
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.reflexio.app.data.contacts.CallLogReader
import com.reflexio.app.data.db.CallAggregate
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.domain.contacts.ContactMatcher
import com.reflexio.app.domain.network.MemoryApi
import com.reflexio.app.domain.network.PendingApproval
import com.reflexio.app.domain.network.PersonListItem
import com.reflexio.app.domain.network.ServerEndpointResolver
import com.reflexio.app.ui.permissions.ContactsPermissionGate
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// ПОЧЕМУ: цвета как файловые константы — переиспользуются в двух приватных Composable,
// совпадают с палитрой остальных экранов (SearchScreen, ThreadsScreen)
private val IndigoAccent = Color(0xFF7C6CFF)
private val TealAccent = Color(0xFF00E5CC)
private val AmberAccent = Color(0xFFFFC75A)

private sealed class PeopleUiState {
    object Loading : PeopleUiState()
    data class Error(val message: String) : PeopleUiState()
    data class Success(
        val persons: List<PersonListItem>,
        val pending: List<PendingApproval>,
        val callStats: Map<String, CallAggregate> = emptyMap(),
    ) : PeopleUiState()
}

private data class PeopleNotebookSections(
    val priority: List<PersonListItem>,
    val recent: List<PersonListItem>,
    val others: List<PersonListItem>,
)

private fun buildPeopleSections(
    persons: List<PersonListItem>,
    callStats: Map<String, CallAggregate> = emptyMap(),
): PeopleNotebookSections {
    if (persons.isEmpty()) return PeopleNotebookSections(emptyList(), emptyList(), emptyList())
    val ranked = persons.sortedByDescending { personPriorityScore(it, callStats) }.distinctBy { it.name }
    val priority = ranked.take(4)
    val recent = ranked.drop(priority.size).take(6)
    val others = ranked.drop(priority.size + recent.size)
    return PeopleNotebookSections(priority, recent, others)
}

private fun personPriorityScore(
    person: PersonListItem,
    callStats: Map<String, CallAggregate> = emptyMap(),
): Int {
    var score = person.sampleCount * 3
    if (person.voiceReady) score += 14
    if (person.relationship != "unknown" && person.relationship.isNotBlank()) score += 6
    if (!person.lastSeen.isNullOrBlank()) score += 10

    // ПОЧЕМУ caps: без них человек с 100 пропущенными от колл-центра обгонит реальных друзей.
    val stats = callStats[person.name]
    if (stats != null) {
        score += minOf(stats.callCount * 5, 40)
        score += minOf(stats.totalSeconds / 60, 30)
        val daysAgo = (System.currentTimeMillis() - stats.lastCallMs) / 86_400_000L
        if (daysAgo < 7) score += 15
    }
    return score
}

private fun buildPersonSubtitle(
    person: PersonListItem,
    callStats: Map<String, CallAggregate> = emptyMap(),
): String {
    val bits = mutableListOf<String>()
    person.relationship
        .takeIf { it.isNotBlank() && it != "unknown" }
        ?.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
        ?.let(bits::add)
    person.lastSeen?.take(10)?.let { bits.add("контакт $it") }
    if (person.sampleCount > 0) bits.add("следов ${person.sampleCount}")
    val stats = callStats[person.name]
    if (stats != null) bits.add("звонков ${stats.callCount}")
    return bits.joinToString(" · ").ifBlank { "Пока мало контекста, но карточка уже готова для накопления памяти." }
}

/**
 * Экран "Люди" — социальный граф пользователя.
 *
 * Отображает список известных людей и коллапсируемую секцию ожидающих подтверждения.
 * Approve/Reject обрабатываются немедленно через MemoryApi; после действия pending обновляется.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PeopleScreen(
    baseHttpUrl: String,
    onOpenPerson: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf<PeopleUiState>(PeopleUiState.Loading) }
    var search by remember { mutableStateOf("") }
    var contactsGranted by remember { mutableStateOf(false) }

    // ПОЧЕМУ: reload вынесен как локальная suspend-функция — вызывается и при старте (LaunchedEffect)
    // и после каждого approve/reject, чтобы оба списка всегда были актуальны
    suspend fun reload() {
        state = PeopleUiState.Loading
        state = try {
            val persons = withContext(Dispatchers.IO) { MemoryApi.fetchPersons(baseHttpUrl) }
            val pending = withContext(Dispatchers.IO) { MemoryApi.fetchPending(baseHttpUrl) }
            // ПОЧЕМУ call sync здесь: данные нужны только для ranking на этом экране.
            // Sync = read ContentResolver → write Room cache → aggregate.
            val callStats = if (contactsGranted) {
                withContext(Dispatchers.IO) { syncAndAggregateCallLog(context, persons) }
            } else {
                emptyMap()
            }
            PeopleUiState.Success(persons, pending, callStats)
        } catch (e: Exception) {
            PeopleUiState.Error(ServerEndpointResolver.userFacingError(e.message, baseHttpUrl))
        }
    }

    LaunchedEffect(baseHttpUrl, contactsGranted) { reload() }

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

            item {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        text = "Личная записная книжка по людям",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "Открывай человека и быстро вспоминай контекст: о чём вы говорите, что обещали и что важно сейчас.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedTextField(
                        value = search,
                        onValueChange = { search = it },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(18.dp),
                        singleLine = true,
                        label = { Text("Найти человека") },
                    )
                }
            }

            // Opt-in для контактов и журнала звонков
            if (!contactsGranted) {
                item {
                    ContactsPermissionGate(
                        onGranted = { contactsGranted = true },
                    )
                }
            }

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

            val filteredPersons = current.persons.filter {
                search.isBlank() || it.name.contains(search.trim(), ignoreCase = true)
            }
            val sections = buildPeopleSections(filteredPersons, current.callStats)

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
            } else if (filteredPersons.isEmpty()) {
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
                            Text("Никого не нашли", fontWeight = FontWeight.SemiBold)
                            Text(
                                "Попробуйте короче имя или откройте кого-то из найденных разговоров.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            } else {
                if (sections.priority.isNotEmpty()) {
                    item {
                        SectionHeader(
                            title = "Важно сейчас",
                            subtitle = "Люди с самым плотным и полезным контекстом.",
                        )
                    }
                    item {
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            sections.priority.forEach { person ->
                                PersonNotebookChip(person = person, callStats = current.callStats, onClick = { onOpenPerson(person.name) })
                            }
                        }
                    }
                }

                if (sections.recent.isNotEmpty()) {
                    item {
                        SectionHeader(
                            title = "Недавние и частые",
                            subtitle = "Открой и быстро вспомни, что у вас по этому человеку.",
                        )
                    }
                    items(sections.recent, key = { it.name }) { person ->
                        PersonListCard(person = person, callStats = current.callStats, onClick = { onOpenPerson(person.name) })
                    }
                }

                if (sections.others.isNotEmpty()) {
                    item {
                        SectionHeader(
                            title = "Вся записная книжка",
                            subtitle = "${filteredPersons.size} человек в памяти.",
                        )
                    }
                    items(sections.others, key = { it.name }) { person ->
                        PersonListCard(person = person, callStats = current.callStats, onClick = { onOpenPerson(person.name) })
                    }
                }
            }

            item { Box(modifier = Modifier.padding(bottom = 16.dp)) }
        }
    }
}

@Composable
private fun SectionHeader(title: String, subtitle: String) {
    Column(
        modifier = Modifier.padding(start = 4.dp, top = 4.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = subtitle,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f),
        )
    }
}

@Composable
private fun PersonNotebookChip(
    person: PersonListItem,
    callStats: Map<String, CallAggregate> = emptyMap(),
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(
            containerColor = IndigoAccent.copy(alpha = 0.12f),
        ),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(person.name, fontWeight = FontWeight.Bold)
            Text(
                buildPersonSubtitle(person, callStats),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
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
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PersonListCard(
    person: PersonListItem,
    callStats: Map<String, CallAggregate> = emptyMap(),
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

            Text(
                text = buildPersonSubtitle(person, callStats),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
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
                if (person.sampleCount > 0) {
                    AssistChip(
                        onClick = {},
                        label = { Text("${person.sampleCount} следов") },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = AmberAccent.copy(alpha = 0.18f),
                            labelColor = AmberAccent,
                        ),
                    )
                }
                callStats[person.name]?.let { stats ->
                    AssistChip(
                        onClick = {},
                        label = { Text("${stats.callCount} звонков") },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = TealAccent.copy(alpha = 0.18f),
                            labelColor = TealAccent,
                        ),
                    )
                }
            }
        }
    }
}

/**
 * Синхронизирует call log из ContentResolver в Room кэш и возвращает агрегаты.
 * Matching: имена из call log сопоставляются с серверными именами через ContactMatcher.
 */
private suspend fun syncAndAggregateCallLog(
    context: Context,
    serverPersons: List<PersonListItem>,
): Map<String, CallAggregate> {
    val dao = RecordingDatabase.getInstance(context).callLogCacheDao()

    // Sync: read ContentResolver → Room (max раз в 5 минут)
    val lastSync = dao.lastSyncTime() ?: 0L
    if (System.currentTimeMillis() - lastSync > 5 * 60 * 1000L) {
        val calls = CallLogReader.readCallLog(context.contentResolver)
        if (calls.isNotEmpty()) {
            dao.insertAll(calls)
            // Удаляем записи старше 35 дней
            dao.deleteOlderThan(System.currentTimeMillis() - 35 * 86_400_000L)
        }
    }

    // Aggregate
    val aggregates = dao.aggregateByContact()
    val callLogNames = aggregates.map { it.contactName }.toSet()
    val result = mutableMapOf<String, CallAggregate>()

    for (person in serverPersons) {
        val matchedName = ContactMatcher.matchCallLogName(person.name, callLogNames)
        if (matchedName != null) {
            aggregates.firstOrNull { it.contactName == matchedName }?.let {
                result[person.name] = it
            }
        }
    }
    return result
}
