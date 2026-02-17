package com.reflexio.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.reflexio.app.data.model.Recording
import com.reflexio.app.data.model.RecordingStatus
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun RecordingListScreen(
    recordings: List<Recording>,
    modifier: Modifier = Modifier
) {
    if (recordings.isEmpty()) {
        Text(
            text = "No recordings yet",
            style = MaterialTheme.typography.bodyMedium,
            modifier = modifier.padding(16.dp)
        )
        return
    }
    LazyColumn(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        items(recordings) { recording ->
            RecordingItem(recording = recording)
        }
    }
}

@Composable
private fun RecordingItem(
    recording: Recording,
    modifier: Modifier = Modifier
) {
    val dateStr = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault())
        .format(Date(recording.createdAt))
    val durationStr = "${recording.durationSeconds}s"
    val statusLabel = when (recording.status) {
        RecordingStatus.PENDING_UPLOAD -> "Sending…"
        RecordingStatus.PROCESSED -> "Done"
        RecordingStatus.FAILED -> "Failed"
        else -> recording.status
    }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = dateStr,
                        style = MaterialTheme.typography.titleSmall
                    )
                    Text(
                        text = durationStr,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                Text(
                    text = statusLabel,
                    style = MaterialTheme.typography.labelMedium
                )
            }
            recording.transcription?.takeIf { it.isNotBlank() }?.let { text ->
                Text(
                    text = text,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
        }
    }
}
