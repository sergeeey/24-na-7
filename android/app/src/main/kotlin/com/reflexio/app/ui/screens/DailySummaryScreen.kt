package com.reflexio.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * Экран «Итог дня»: загружает GET /digest/daily?date= и отображает summary, темы, эмоции, действия.
 */
@Composable
fun DailySummaryScreen(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    baseHttpUrl: String
) {
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var data by remember { mutableStateOf<DailyDigestData?>(null) }
    var retryCount by remember { mutableStateOf(0) }

    val today = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

    LaunchedEffect(baseHttpUrl, today, retryCount) {
        loading = true
        error = null
        data = null
        val result = withContext(Dispatchers.IO) {
            fetchDailyDigest(baseHttpUrl, today)
        }
        loading = false
        when (result) {
            is DailyDigestResult.Success -> data = result.data
            is DailyDigestResult.Error -> error = result.message
        }
    }

    Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Итог дня", style = MaterialTheme.typography.titleLarge)
            Button(onClick = onBack) { Text("Назад") }
        }
        Spacer(modifier = Modifier.height(8.dp))

        when {
            loading -> {
                Column(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    CircularProgressIndicator()
                    Spacer(modifier = Modifier.height(16.dp))
                    Text("Загрузка…", style = MaterialTheme.typography.bodyMedium)
                }
            }
            error != null -> {
                Text(
                    text = "Ошибка: $error",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(8.dp)
                )
                Button(onClick = { retryCount++ }) {
                    Text("Повторить")
                }
            }
            data != null -> {
                DailySummaryContent(data = data!!)
            }
        }
    }
}

@Composable
private fun DailySummaryContent(data: DailyDigestData) {
    val scroll = rememberScrollState()
    Column(modifier = Modifier.verticalScroll(scroll)) {
        data.summary_text.takeIf { it.isNotBlank() }?.let { summary ->
            Text("Итог", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(4.dp))
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
            ) {
                Text(
                    text = summary,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(12.dp)
                )
            }
            Spacer(modifier = Modifier.height(16.dp))
        }

        if (data.key_themes.isNotEmpty()) {
            Text("Ключевые темы", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(4.dp))
            data.key_themes.forEach { theme ->
                Text("• $theme", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 2.dp))
            }
            Spacer(modifier = Modifier.height(16.dp))
        }

        if (data.emotions.isNotEmpty()) {
            Text("Эмоции", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(4.dp))
            Text(data.emotions.joinToString(", "), style = MaterialTheme.typography.bodyMedium)
            Spacer(modifier = Modifier.height(16.dp))
        }

        if (data.actions.isNotEmpty()) {
            Text("Действия", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(4.dp))
            data.actions.forEach { action ->
                val done = action.done
                Text(
                    text = (if (done) "✓ " else "□ ") + action.text,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(vertical = 2.dp)
                )
            }
            Spacer(modifier = Modifier.height(16.dp))
        }

        Text("Статистика", style = MaterialTheme.typography.titleMedium)
        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = "Записей: ${data.total_recordings}, длительность: ${data.total_duration}",
            style = MaterialTheme.typography.bodyMedium
        )

        if (data.repetitions.isNotEmpty()) {
            Spacer(modifier = Modifier.height(16.dp))
            Text("Повторяется", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(4.dp))
            data.repetitions.forEach { rep ->
                Text("• $rep", style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 2.dp))
            }
        }
    }
}

private data class DailyDigestData(
    val date: String,
    val summary_text: String,
    val key_themes: List<String>,
    val emotions: List<String>,
    val actions: List<ActionItem>,
    val total_recordings: Int,
    val total_duration: String,
    val repetitions: List<String>
)

private data class ActionItem(val text: String, val done: Boolean)

private sealed class DailyDigestResult {
    data class Success(val data: DailyDigestData) : DailyDigestResult()
    data class Error(val message: String) : DailyDigestResult()
}

private fun fetchDailyDigest(baseHttpUrl: String, date: String): DailyDigestResult {
    val url = "$baseHttpUrl/digest/daily?date=$date".replace("//digest", "/digest")
    val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    return try {
        val request = Request.Builder().url(url).get().build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            return DailyDigestResult.Error("HTTP ${response.code}")
        }
        val body = response.body?.string() ?: return DailyDigestResult.Error("Empty response")
        val json = org.json.JSONObject(body)
        val keyThemes = mutableListOf<String>()
        val jaThemes = json.optJSONArray("key_themes")
        if (jaThemes != null) for (i in 0 until jaThemes.length()) keyThemes.add(jaThemes.optString(i, ""))
        val emotions = mutableListOf<String>()
        val jaEmotions = json.optJSONArray("emotions")
        if (jaEmotions != null) for (i in 0 until jaEmotions.length()) emotions.add(jaEmotions.optString(i, ""))
        val actions = mutableListOf<ActionItem>()
        val jaActions = json.optJSONArray("actions")
        if (jaActions != null) {
            for (i in 0 until jaActions.length()) {
                val obj = jaActions.optJSONObject(i)
                if (obj != null) {
                    actions.add(ActionItem(obj.optString("text", ""), obj.optBoolean("done", false)))
                }
            }
        }
        val repetitions = mutableListOf<String>()
        val jaRep = json.optJSONArray("repetitions")
        if (jaRep != null) for (i in 0 until jaRep.length()) repetitions.add(jaRep.optString(i, ""))
        val data = DailyDigestData(
            date = json.optString("date", date),
            summary_text = json.optString("summary_text", ""),
            key_themes = keyThemes,
            emotions = emotions,
            actions = actions,
            total_recordings = json.optInt("total_recordings", 0),
            total_duration = json.optString("total_duration", "0m 0s"),
            repetitions = repetitions
        )
        DailyDigestResult.Success(data)
    } catch (e: Exception) {
        DailyDigestResult.Error(e.message ?: e.javaClass.simpleName)
    }
}
