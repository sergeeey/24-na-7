package com.reflexio.app.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * Экран «Аналитика»: отчёты за день/месяц, характеристика, работа, отношения,
 * возможность подключить свой LLM для обработки данных.
 */
@Composable
fun AnalyticsScreen(
    onBack: () -> Unit,
    onOpenDailySummary: () -> Unit,
    modifier: Modifier = Modifier
) {
    val scroll = rememberScrollState()
    Column(modifier = modifier.padding(16.dp).verticalScroll(scroll)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Аналитика", style = MaterialTheme.typography.titleLarge)
            Button(onClick = onBack) { Text("Назад") }
        }
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "Здесь можно вытащить отчёты по своим записям. В будущем — подключить свой LLM и обрабатывать данные через него.",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(bottom = 16.dp)
        )

        AnalyticsItem(
            title = "Итог дня",
            description = "Краткий итог за сегодня: темы, эмоции, действия",
            available = true,
            onClick = onOpenDailySummary
        )
        Spacer(modifier = Modifier.height(8.dp))
        AnalyticsItem(
            title = "Отчёт за месяц",
            description = "Сводка за месяц: темы, паттерны, динамика",
            available = false
        )
        Spacer(modifier = Modifier.height(8.dp))
        AnalyticsItem(
            title = "Характеристика",
            description = "Самопортрет по записям: как вы говорите о себе, работе, целях",
            available = false
        )
        Spacer(modifier = Modifier.height(8.dp))
        AnalyticsItem(
            title = "Работа и сеть",
            description = "Темы по работе, коллегам, отношениям, встречам",
            available = false
        )
        Spacer(modifier = Modifier.height(16.dp))
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
            shape = MaterialTheme.shapes.medium
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = "Подключить свой LLM",
                    style = MaterialTheme.typography.titleMedium
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Войти в свой аккаунт (OpenAI, Anthropic, др.) и обрабатывать данные через свою модель: отчёты, характеристики, выводы. В разработке.",
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
    }
}

@Composable
private fun AnalyticsItem(
    title: String,
    description: String,
    available: Boolean,
    onClick: (() -> Unit)? = null
) {
    val modifier = if (available && onClick != null) {
        Modifier.fillMaxWidth().clickable(onClick = onClick)
    } else {
        Modifier.fillMaxWidth()
    }
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = if (available) MaterialTheme.colorScheme.surfaceVariant
            else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.7f)
        ),
        shape = MaterialTheme.shapes.medium
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = title, style = MaterialTheme.typography.titleSmall)
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = description,
                    style = MaterialTheme.typography.bodySmall
                )
            }
            if (!available) {
                Text(
                    text = "Скоро",
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(start = 8.dp)
                )
            }
        }
    }
}
