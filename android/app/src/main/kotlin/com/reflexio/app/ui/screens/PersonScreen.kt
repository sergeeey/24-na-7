package com.reflexio.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.reflexio.app.domain.network.MemoryApi
import com.reflexio.app.domain.network.PersonInsightData
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

// ПОЧЕМУ: data class приватный к файлу — не нужен в общем API слое,
// используется только в этом экране для отображения обещаний конкретного человека
private data class PersonCommitment(
    val action: String,
    val deadline: String?,
    val timestamp: String,
)

// ПОЧЕМУ: функция вынесена на уровень файла (не внутрь Composable),
// чтобы избежать повторного создания замыкания при рекомпозиции
private fun fetchPersonCommitments(baseHttpUrl: String, person: String): List<PersonCommitment> {
    val encodedName = java.net.URLEncoder.encode(person, "UTF-8")
    val url = "${baseHttpUrl.removeSuffix("/")}/commitments?days_back=30&limit=10&person=$encodedName"
    val requestBuilder = okhttp3.Request.Builder().url(url).get()
    val apiKey = com.reflexio.app.BuildConfig.SERVER_API_KEY
    if (apiKey.isNotEmpty()) {
        requestBuilder.addHeader("Authorization", "Bearer $apiKey")
    }
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

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PersonScreen(
    baseHttpUrl: String,
    name: String,
    modifier: Modifier = Modifier,
) {
    var loading by remember(name) { mutableStateOf(true) }
    var error by remember(name) { mutableStateOf<String?>(null) }
    var data by remember(name) { mutableStateOf<PersonInsightData?>(null) }
    var commitments by remember(name) { mutableStateOf<List<PersonCommitment>>(emptyList()) }

    LaunchedEffect(baseHttpUrl, name) {
        loading = true
        error = null
        try {
            data = withContext(Dispatchers.IO) { MemoryApi.fetchPersonInsights(baseHttpUrl, name) }
        } catch (e: Exception) {
            error = e.message ?: "Не удалось загрузить профиль"
        } finally {
            loading = false
        }
        // ПОЧЕМУ: загружаем обещания независимо от ошибки основного профиля —
        // commitments могут существовать даже если insights недоступны
        try {
            commitments = withContext(Dispatchers.IO) {
                fetchPersonCommitments(baseHttpUrl, name)
            }
        } catch (_: Exception) {
            commitments = emptyList()
        }
    }

    when {
        loading -> Box(modifier = modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
            CircularProgressIndicator()
        }
        error != null -> Box(modifier = modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
            Text(error!!, color = MaterialTheme.colorScheme.error)
        }
        data != null -> Card(
            modifier = modifier
                .fillMaxSize()
                .padding(16.dp),
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f)),
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text(data!!.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Text(
                    "Взаимодействий: ${data!!.interactionsCount} · voice profile: ${if (data!!.voiceReady) "готов" else "нет"}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                )
                data!!.warning?.let {
                    Text(
                        text = it,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (data!!.recentTopics.isNotEmpty()) {
                    Text("Последние темы", fontWeight = FontWeight.SemiBold)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        data!!.recentTopics.forEach { topic ->
                            AssistChip(onClick = {}, label = { Text(topic) })
                        }
                    }
                }
                if (data!!.neighbors.isNotEmpty()) {
                    Text("Связи", fontWeight = FontWeight.SemiBold)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        data!!.neighbors.forEach { neighbor ->
                            AssistChip(onClick = {}, label = { Text(neighbor) })
                        }
                    }
                }
                if (data!!.warning != null && data!!.recentTopics.isEmpty() && data!!.neighbors.isEmpty()) {
                    Text(
                        "Попробуйте открыть профиль человека, который уже фигурирует в найденных событиях.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                // ПОЧЕМУ: секция обещаний идёт последней — дополнительный контекст,
                // не должна перебивать основную информацию о человеке
                if (commitments.isNotEmpty()) {
                    Text("Обещания", fontWeight = FontWeight.SemiBold)
                    commitments.forEach { commitment ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp),
                            colors = CardDefaults.cardColors(
                                containerColor = MaterialTheme.colorScheme.surfaceVariant,
                            ),
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
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
                                    text = commitment.timestamp,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
