package com.reflexio.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.reflexio.app.domain.network.MemoryApi
import com.reflexio.app.domain.network.PersonInsightData
import com.reflexio.app.domain.network.SearchEvent
import com.reflexio.app.domain.network.ThreadSummary
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private data class PersonCommitment(
    val action: String,
    val deadline: String?,
    val timestamp: String,
)

private data class PersonNotebookModel(
    val profile: PersonInsightData,
    val commitments: List<PersonCommitment>,
    val recentEvents: List<SearchEvent>,
    val threads: List<ThreadSummary>,
)

private fun fetchPersonCommitments(baseHttpUrl: String, person: String): List<PersonCommitment> {
    val encodedName = java.net.URLEncoder.encode(person, "UTF-8")
    val url = "${baseHttpUrl.removeSuffix("/")}/commitments?days_back=30&limit=10&person=$encodedName"
    val requestBuilder = com.reflexio.app.domain.network.ServerEndpointResolver.attachAuth(
        okhttp3.Request.Builder().url(url),
        url,
    ).get()
    com.reflexio.app.domain.network.NetworkClients.sharedClient.newCall(requestBuilder.build()).execute().use { resp ->
        if (!resp.isSuccessful) return emptyList()
        val body = resp.body?.string() ?: return emptyList()
        val json = org.json.JSONObject(body)
        val arr = json.optJSONArray("commitments") ?: return emptyList()
        return buildList {
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i) ?: continue
                add(
                    PersonCommitment(
                        action = obj.optString("action", ""),
                        deadline = obj.optString("deadline", "").ifEmpty { null },
                        timestamp = obj.optString("timestamp", ""),
                    ),
                )
            }
        }
    }
}

@Composable
fun PersonScreen(
    baseHttpUrl: String,
    name: String,
    onAskPerson: (String) -> Unit = {},
    onOpenThreads: () -> Unit = {},
    onPersonErased: (String) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    var loading by remember(name) { mutableStateOf(true) }
    var error by remember(name) { mutableStateOf<String?>(null) }
    var notebook by remember(name) { mutableStateOf<PersonNotebookModel?>(null) }
    var showEraseDialog by remember { mutableStateOf(false) }
    var erasing by remember { mutableStateOf(false) }

    LaunchedEffect(baseHttpUrl, name) {
        loading = true
        error = null
        try {
            notebook = withContext(Dispatchers.IO) {
                val profile = MemoryApi.fetchPersonInsights(baseHttpUrl, name)
                val commitments = fetchPersonCommitments(baseHttpUrl, name)
                val recentEvents = MemoryApi.queryEvents(baseHttpUrl, name, limit = 6).events
                val threads = MemoryApi.queryThreads(baseHttpUrl)
                    .filter { thread ->
                        thread.participants.any { it.equals(name, ignoreCase = true) } ||
                            thread.summary.contains(name, ignoreCase = true) ||
                            thread.latestSummary.contains(name, ignoreCase = true)
                    }
                    .take(4)
                PersonNotebookModel(
                    profile = profile,
                    commitments = commitments,
                    recentEvents = recentEvents,
                    threads = threads,
                )
            }
        } catch (e: Exception) {
            error = e.message ?: "Не удалось загрузить профиль"
            notebook = null
        } finally {
            loading = false
        }
    }

    when {
        loading -> Box(modifier = modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }

        error != null -> Box(modifier = modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(error!!, color = MaterialTheme.colorScheme.error)
        }

        notebook != null -> {
            PersonNotebook(
                notebook = notebook!!,
                onAskPerson = { onAskPerson("Что важно сейчас по человеку ${notebook!!.profile.name}?") },
                onOpenThreads = onOpenThreads,
                onErase = { showEraseDialog = true },
                erasing = erasing,
                modifier = modifier,
            )
            if (showEraseDialog) {
                AlertDialog(
                    onDismissRequest = { showEraseDialog = false },
                    title = { Text("Удалить данные") },
                    text = { Text("Все голосовые данные «$name» будут удалены навсегда. Это действие нельзя отменить.") },
                    confirmButton = {
                        TextButton(onClick = {
                            showEraseDialog = false
                            erasing = true
                            scope.launch {
                                val ok = withContext(Dispatchers.IO) { MemoryApi.erasePerson(baseHttpUrl, name) }
                                erasing = false
                                if (ok) onPersonErased(name)
                                else error = "Не удалось удалить данные"
                            }
                        }) { Text("Удалить", color = MaterialTheme.colorScheme.error) }
                    },
                    dismissButton = {
                        TextButton(onClick = { showEraseDialog = false }) { Text("Отмена") }
                    },
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PersonNotebook(
    notebook: PersonNotebookModel,
    onAskPerson: () -> Unit,
    onOpenThreads: () -> Unit,
    onErase: () -> Unit = {},
    erasing: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val profile = notebook.profile
    val importantNow = buildList {
        notebook.commitments.take(2).forEach { add("Обещание: ${it.action}") }
        notebook.recentEvents.firstOrNull()?.snippet?.takeIf { it.isNotBlank() }?.let {
            add("Последний заметный контакт: ${it.take(96)}")
        }
        notebook.threads.firstOrNull()?.latestSummary?.takeIf { it.isNotBlank() }?.let {
            add("Тянущаяся линия: ${it.take(96)}")
        }
        if (profile.warning != null) add(profile.warning)
    }.distinct().take(4)

    Card(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.9f)),
    ) {
        Column(
            modifier = Modifier
                .padding(18.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(profile.name, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(
                buildProfileSummary(profile, notebook),
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onAskPerson) { Text("Спросить") }
                TextButton(onClick = onOpenThreads, enabled = notebook.threads.isNotEmpty()) { Text("Потоки") }
            }

            NotebookMetricRow(notebook = notebook)

            if (importantNow.isNotEmpty()) {
                NotebookSection(title = "Что важно сейчас") {
                    importantNow.forEach { point ->
                        NoteCard(text = point)
                    }
                }
            }

            if (profile.recentTopics.isNotEmpty()) {
                NotebookSection(title = "О чём вы обычно") {
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        profile.recentTopics.forEach { topic ->
                            AssistChip(onClick = {}, label = { Text(topic) })
                        }
                    }
                }
            }

            if (notebook.commitments.isNotEmpty()) {
                NotebookSection(title = "Обещания") {
                    notebook.commitments.forEach { commitment ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(14.dp),
                            colors = CardDefaults.cardColors(
                                containerColor = MaterialTheme.colorScheme.surfaceVariant,
                            ),
                        ) {
                            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text(
                                    text = commitment.action,
                                    style = MaterialTheme.typography.bodyMedium,
                                    maxLines = 3,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                commitment.deadline?.let {
                                    Text(
                                        text = "Срок: $it",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.primary,
                                    )
                                }
                                Text(
                                    text = commitment.timestamp.take(10),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                                )
                            }
                        }
                    }
                }
            }

            if (notebook.threads.isNotEmpty()) {
                NotebookSection(title = "Линии отношений") {
                    notebook.threads.forEach { thread ->
                        NoteCard(text = thread.latestSummary.ifBlank { thread.summary })
                    }
                }
            }

            if (notebook.recentEvents.isNotEmpty()) {
                NotebookSection(title = "Последние взаимодействия") {
                    notebook.recentEvents.forEach { event ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(14.dp),
                            colors = CardDefaults.cardColors(
                                containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.86f),
                            ),
                        ) {
                            Column(
                                modifier = Modifier.padding(12.dp),
                                verticalArrangement = Arrangement.spacedBy(6.dp),
                            ) {
                                Text(
                                    event.timestamp.take(16),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.primary,
                                )
                                Text(
                                    event.snippet,
                                    style = MaterialTheme.typography.bodyMedium,
                                    maxLines = 3,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                        }
                    }
                }
            }

            if (profile.neighbors.isNotEmpty()) {
                NotebookSection(title = "Кто рядом в этом контексте") {
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        profile.neighbors.forEach { neighbor ->
                            AssistChip(onClick = {}, label = { Text(neighbor) })
                        }
                    }
                }
            }

            // ── Erase person data (GDPR) ──
            Spacer(modifier = Modifier.height(8.dp))
            Button(
                onClick = onErase,
                enabled = !erasing,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.errorContainer,
                    contentColor = MaterialTheme.colorScheme.onErrorContainer,
                ),
            ) {
                if (erasing) {
                    CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                } else {
                    Text("Удалить голосовые данные")
                }
            }
        }
    }
}

@Composable
private fun NotebookMetricRow(notebook: PersonNotebookModel) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        MetricTile(
            title = "Контактов",
            value = notebook.profile.interactionsCount.toString(),
            modifier = Modifier.weight(1f),
        )
        MetricTile(
            title = "Тем",
            value = notebook.profile.recentTopics.size.toString(),
            modifier = Modifier.weight(1f),
        )
        MetricTile(
            title = "Обещаний",
            value = notebook.commitments.size.toString(),
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun MetricTile(title: String, value: String, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.85f),
        ),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(title, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun NotebookSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
        content()
    }
}

@Composable
private fun NoteCard(text: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.9f),
        ),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(12.dp),
            style = MaterialTheme.typography.bodyMedium,
            maxLines = 4,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

private fun buildProfileSummary(
    profile: PersonInsightData,
    notebook: PersonNotebookModel,
): String {
    val bits = mutableListOf<String>()
    if (profile.voiceReady) bits += "голос уже знаком системе"
    if (profile.interactionsCount > 0) bits += "взаимодействий: ${profile.interactionsCount}"
    notebook.recentEvents.firstOrNull()?.timestamp?.take(10)?.let { bits += "последний контакт $it" }
    return bits.joinToString(" · ").ifBlank { "Это карточка памяти по человеку: всё важное будет собираться сюда по мере взаимодействий." }
}
