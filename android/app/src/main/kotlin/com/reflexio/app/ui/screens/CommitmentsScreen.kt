package com.reflexio.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.reflexio.app.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

// ПОЧЕМУ отдельный экран, а не часть DailySummary:
// Обещания — это cross-day сущность (30 дней назад).
// DailySummary = один день, Commitments = долгосрочная картина.

private val ColorTeal = Color(0xFF00E5CC)
private val ColorIndigo = Color(0xFF7C6CFF)

/**
 * Экран «Обещания»: загружает GET /commitments и показывает
 * карточки обещаний с фильтром по людям (чипсы).
 */
@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
fun CommitmentsScreen(
    baseHttpUrl: String,
    modifier: Modifier = Modifier,
) {
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var commitments by remember { mutableStateOf<List<CommitmentItem>>(emptyList()) }
    var people by remember { mutableStateOf<List<PersonSummary>>(emptyList()) }
    var selectedPerson by remember { mutableStateOf<String?>(null) }
    var retryCount by remember { mutableStateOf(0) }

    // Загрузка данных
    LaunchedEffect(baseHttpUrl, retryCount, selectedPerson) {
        loading = true
        error = null
        val result = withContext(Dispatchers.IO) {
            fetchCommitments(baseHttpUrl, selectedPerson)
        }
        loading = false
        when (result) {
            is CommitmentsResult.Success -> {
                commitments = result.commitments
                // Людей загружаем один раз (без фильтра)
                if (people.isEmpty()) {
                    val peopleResult = withContext(Dispatchers.IO) {
                        fetchPeople(baseHttpUrl)
                    }
                    if (peopleResult is PeopleResult.Success) {
                        people = peopleResult.people
                    }
                }
            }
            is CommitmentsResult.Error -> error = result.message
        }
    }

    Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
        // Header
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Default.Insights,
                    contentDescription = null,
                    tint = ColorIndigo,
                    modifier = Modifier.size(28.dp),
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text("Обещания", style = MaterialTheme.typography.titleLarge)
            }
            IconButton(onClick = { retryCount++ }) {
                Icon(Icons.Default.Refresh, contentDescription = "Обновить")
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Фильтр по людям (чипсы)
        if (people.isNotEmpty()) {
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                FilterChip(
                    selected = selectedPerson == null,
                    onClick = { selectedPerson = null },
                    label = { Text("Все") },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = ColorIndigo.copy(alpha = 0.15f),
                    ),
                )
                people.forEach { person ->
                    FilterChip(
                        selected = selectedPerson == person.name,
                        onClick = {
                            selectedPerson = if (selectedPerson == person.name) null else person.name
                        },
                        label = { Text("${person.name} (${person.count})") },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = ColorTeal.copy(alpha = 0.15f),
                        ),
                    )
                }
            }
            Spacer(modifier = Modifier.height(12.dp))
        }

        // Контент
        when {
            loading -> {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(color = ColorIndigo)
                }
            }
            error != null -> {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Не удалось загрузить", style = MaterialTheme.typography.bodyLarge)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            error ?: "",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            commitments.isEmpty() -> {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "Пока нет обещаний.\nГоворите в микрофон — система извлечёт их автоматически.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            else -> {
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(commitments) { item ->
                        AnimatedVisibility(
                            visible = true,
                            enter = fadeIn() + expandVertically(),
                        ) {
                            CommitmentCard(item)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CommitmentCard(item: CommitmentItem) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Действие (главное)
            Text(
                text = item.action,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Medium,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
            )

            Spacer(modifier = Modifier.height(6.dp))

            // Кому + когда
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // Персона
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Default.Person,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp),
                        tint = ColorIndigo,
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = item.person,
                        style = MaterialTheme.typography.labelMedium,
                        color = ColorIndigo,
                    )
                }

                // Дедлайн (если есть)
                if (!item.deadline.isNullOrBlank()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            Icons.Default.Schedule,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = item.deadline,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }

            // Контекст (если есть)
            if (!item.context.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = item.context,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }

            // Дата записи
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = item.timestamp,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
            )
        }
    }
}

// ── Data models ──

private data class CommitmentItem(
    val person: String,
    val action: String,
    val deadline: String?,
    val context: String?,
    val timestamp: String,
    val eventSummary: String?,
)

private data class PersonSummary(
    val name: String,
    val count: Int,
)

// ── Network ──

private sealed class CommitmentsResult {
    data class Success(val commitments: List<CommitmentItem>) : CommitmentsResult()
    data class Error(val message: String) : CommitmentsResult()
}

private sealed class PeopleResult {
    data class Success(val people: List<PersonSummary>) : PeopleResult()
    data class Error(val message: String) : PeopleResult()
}

private fun fetchCommitments(baseHttpUrl: String, person: String?): CommitmentsResult {
    val url = buildString {
        append("$baseHttpUrl/commitments?days_back=30&limit=50")
        if (!person.isNullOrBlank()) {
            append("&person=${java.net.URLEncoder.encode(person, "UTF-8")}")
        }
    }
    val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()
    return try {
        val requestBuilder = Request.Builder().url(url).get()
        val apiKey = BuildConfig.SERVER_API_KEY
        if (apiKey.isNotEmpty()) {
            requestBuilder.addHeader("Authorization", "Bearer $apiKey")
        }
        val response = client.newCall(requestBuilder.build()).execute()
        if (!response.isSuccessful) {
            return CommitmentsResult.Error("HTTP ${response.code}")
        }
        val body = response.body?.string() ?: return CommitmentsResult.Error("Empty response")
        val json = JSONObject(body)

        val items = mutableListOf<CommitmentItem>()
        val arr = json.optJSONArray("commitments")
        if (arr != null) {
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i) ?: continue
                items.add(
                    CommitmentItem(
                        person = obj.optString("person", ""),
                        action = obj.optString("action", ""),
                        deadline = obj.optString("deadline", "").ifEmpty { null },
                        context = obj.optString("context", "").ifEmpty { null },
                        timestamp = obj.optString("timestamp", ""),
                        eventSummary = obj.optString("event_summary", "").ifEmpty { null },
                    )
                )
            }
        }
        CommitmentsResult.Success(items)
    } catch (e: Exception) {
        CommitmentsResult.Error(e.message ?: e.javaClass.simpleName)
    }
}

private fun fetchPeople(baseHttpUrl: String): PeopleResult {
    val url = "$baseHttpUrl/commitments/people?days_back=30"
    val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()
    return try {
        val requestBuilder = Request.Builder().url(url).get()
        val apiKey = BuildConfig.SERVER_API_KEY
        if (apiKey.isNotEmpty()) {
            requestBuilder.addHeader("Authorization", "Bearer $apiKey")
        }
        val response = client.newCall(requestBuilder.build()).execute()
        if (!response.isSuccessful) {
            return PeopleResult.Error("HTTP ${response.code}")
        }
        val body = response.body?.string() ?: return PeopleResult.Error("Empty response")
        val json = JSONObject(body)

        val items = mutableListOf<PersonSummary>()
        val arr = json.optJSONArray("people")
        if (arr != null) {
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i) ?: continue
                items.add(
                    PersonSummary(
                        name = obj.optString("person", ""),
                        count = obj.optInt("commitment_count", 0),
                    )
                )
            }
        }
        PeopleResult.Success(items)
    } catch (e: Exception) {
        PeopleResult.Error(e.message ?: e.javaClass.simpleName)
    }
}
