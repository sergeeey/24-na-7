package com.reflexio.app.domain.network

import com.reflexio.app.BuildConfig
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

data class EvidenceMeta(
    val id: String,
    val timestamp: String,
    val sentimentScore: Double,
    val topTopic: String,
)

data class SearchEvent(
    val id: String,
    val timestamp: String,
    val snippet: String,
    val topTopic: String?,
    val topics: List<String>,
    val people: List<String>,
)

data class SearchResponse(
    val total: Int,
    val events: List<SearchEvent>,
)

data class BalanceDomainInfo(
    val domain: String,
    val score: Float,
    val mentions: Int,
    val sentiment: Float,
)

data class BalanceInfo(
    val domains: List<BalanceDomainInfo>,
    val balanceScore: Float,
    val alert: String?,
    val recommendation: String?,
)

data class DigestSummaryData(
    val summaryText: String?,
    val keyThemes: List<String>,
    val emotions: List<String>,
    val balance: BalanceInfo?,
)

data class EventsSummaryData(
    val total: Int,
    val topTopics: List<String>,
)

data class AskResponseData(
    val answer: String,
    val confidence: Double,
    val confidenceLabel: String,
    val evidenceCount: Int,
    val warning: String?,
    val primaryTool: String?,
    val evidenceMetadata: List<EvidenceMeta>,
    val digest: DigestSummaryData?,
    val events: EventsSummaryData?,
)

data class ActionItemData(
    val text: String,
    val done: Boolean,
    val urgency: String,
)

data class DailyDigestData(
    val date: String,
    val summaryText: String,
    val keyThemes: List<String>,
    val emotions: List<String>,
    val actions: List<ActionItemData>,
    val totalRecordings: Int,
    val totalDuration: String,
    val sourcesCount: Int,
    val notice: String?,
    val status: String?,
    // v2 fields — richer digest context
    val locations: List<String> = emptyList(),
    val evidenceStrength: Float = 0f,
    val trustedFraction: Float = 0f,
    val threadCount: Int = 0,
    val longThreadCount: Int = 0,
    val episodesUsed: Int = 0,
    val degraded: Boolean = false,
    val verdict: String? = null,
    val novelty: List<String> = emptyList(),
    // Consumed content — what user watched/listened to
    val consumedCount: Int = 0,
    val consumedSources: Map<String, Int> = emptyMap(),
    val consumedTopics: List<String> = emptyList(),
)

data class ThreadSummary(
    val id: String,
    val summary: String,
    val latestSummary: String,
    val continuityScore: Float,
    val lastSeenAt: String,
    val topics: List<String>,
    val participants: List<String>,
)

data class PersonInsightData(
    val name: String,
    val interactionsCount: Int,
    val voiceReady: Boolean,
    val neighbors: List<String>,
    val recentTopics: List<String>,
    val warning: String? = null,
)

data class PersonListItem(
    val name: String,
    val relationship: String,
    val voiceReady: Boolean,
    val sampleCount: Int,
    val lastSeen: String?,
)

data class PendingApproval(
    val name: String,
    val sampleCount: Int,
    val avgConfidence: Float,
)

data class InsightCard(
    val role: String,
    val text: String,
)

data class DigestReviewDay(
    val date: String,
    val status: String,  // "green", "yellow", "red", "gray"
)

data class MirrorPortrait(
    val daysBack: Int,
    val topEmotions: List<String>,
    val topTopics: List<String>,
    val topPeople: List<String>,
    val avgSentiment: Float?,
    val episodesCount: Int,
    val openCommitments: Int,
)

object MemoryApi {
    private val jsonMediaType = "application/json".toMediaType()

    fun queryEvents(baseHttpUrl: String, query: String, limit: Int = 20): SearchResponse {
        val encodedQuery = URLEncoder.encode(query, StandardCharsets.UTF_8.toString())
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/query/events?q=$encodedQuery&limit=$limit")
            .get()
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            val raw = resp.body?.string() ?: throw RuntimeException("Empty response")
            if (!resp.isSuccessful) throw RuntimeException("HTTP ${resp.code}: $raw")
            val json = JSONObject(raw)
            val data = json.optJSONObject("data") ?: JSONObject()
            val list = data.optJSONArray("events") ?: JSONArray()
            val events = buildList {
                for (i in 0 until list.length()) {
                    val item = list.optJSONObject(i) ?: continue
                    val text = item.optString("summary").ifBlank { item.optString("text") }
                    val topics = safeJsonList(item.optString("topics_json"))
                    val people = safeJsonList(item.optString("participants_json"))
                    add(
                        SearchEvent(
                            id = item.optString("episode_id").ifBlank { item.optString("id") },
                            timestamp = item.optString("created_at"),
                            snippet = text,
                            topTopic = topics.firstOrNull(),
                            topics = topics,
                            people = people,
                        )
                    )
                }
            }
            return SearchResponse(
                total = data.optInt("total", events.size),
                events = events,
            )
        }
    }

    fun ask(baseHttpUrl: String, question: String): AskResponseData {
        val body = JSONObject()
            .put("question", question)
            .put("include_evidence", false)
            .toString()
            .toRequestBody(jsonMediaType)
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/ask")
            .post(body)
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            val raw = resp.body?.string() ?: throw RuntimeException("Empty response")
            if (!resp.isSuccessful) throw RuntimeException("HTTP ${resp.code}: $raw")
            val json = JSONObject(raw)

            val evidenceMetadata = mutableListOf<EvidenceMeta>()
            var digest: DigestSummaryData? = null
            var events: EventsSummaryData? = null
            val primaryTool = json.optString("primary_tool").ifBlank { null }
            val dataArr = json.optJSONArray("data")
            if (dataArr != null && dataArr.length() > 0) {
                val first = dataArr.optJSONObject(0)
                val evidenceArr = first?.optJSONArray("evidence_metadata")
                if (evidenceArr != null) {
                    for (i in 0 until evidenceArr.length()) {
                        val item = evidenceArr.optJSONObject(i) ?: continue
                        evidenceMetadata.add(
                            EvidenceMeta(
                                id = item.optString("id"),
                                timestamp = item.optString("timestamp"),
                                sentimentScore = item.optDouble("sentiment_score", 0.0),
                                topTopic = item.optString("top_topic"),
                            )
                        )
                    }
                }
                val innerData = first?.optJSONObject("data")
                when (primaryTool) {
                    "get_digest" -> digest = innerData?.let(::parseDigestData)
                    "query_events" -> events = innerData?.let(::parseEventsData)
                }
            }

            return AskResponseData(
                answer = json.optString("answer", "Нет ответа"),
                confidence = json.optDouble("confidence", 0.0),
                confidenceLabel = json.optString("confidence_label", "speculative"),
                evidenceCount = json.optInt("evidence_count", 0),
                warning = json.optString("warning").ifBlank { null },
                primaryTool = primaryTool,
                evidenceMetadata = evidenceMetadata,
                digest = digest,
                events = events,
            )
        }
    }

    fun fetchDigest(baseHttpUrl: String, date: String): DailyDigestData {
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/digest/$date?format=json")
            .get()
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            val raw = resp.body?.string() ?: throw RuntimeException("Empty response")
            if (!resp.isSuccessful) throw RuntimeException("HTTP ${resp.code}: $raw")
            val json = JSONObject(raw)
            // WHY: parse instability_markers for trusted_fraction
            val markers = json.optJSONObject("instability_markers")
            return DailyDigestData(
                date = json.optString("date", date),
                summaryText = json.optString("summary_text", ""),
                keyThemes = jsonArrayToList(json.optJSONArray("key_themes")),
                emotions = extractEmotionList(json.optJSONArray("emotions")),
                actions = parseActions(json.optJSONArray("actions")),
                totalRecordings = json.optInt("total_recordings", 0),
                totalDuration = json.optString("total_duration", "0m 0s"),
                sourcesCount = json.optInt("sources_count", 0),
                notice = json.optString("_notice").ifBlank { null },
                status = json.optString("_status").ifBlank { null },
                locations = jsonArrayToList(json.optJSONArray("locations")),
                evidenceStrength = json.optDouble("evidence_strength", 0.0).toFloat(),
                trustedFraction = markers?.optDouble("trusted_fraction", 0.0)?.toFloat() ?: 0f,
                threadCount = json.optInt("thread_count", 0),
                longThreadCount = json.optInt("long_thread_count", 0),
                episodesUsed = json.optInt("episodes_used", 0),
                degraded = json.optBoolean("degraded", false),
                verdict = json.optString("verdict").ifBlank { null },
                novelty = jsonArrayToList(json.optJSONArray("novelty")),
                consumedCount = json.optJSONObject("consumed_content")?.optInt("total_count", 0) ?: 0,
                consumedSources = run {
                    val src = json.optJSONObject("consumed_content")?.optJSONObject("sources")
                    if (src != null) src.keys().asSequence().associateWith { src.optInt(it, 0) } else emptyMap()
                },
                consumedTopics = run {
                    val arr = json.optJSONObject("consumed_content")?.optJSONArray("top_topics")
                    if (arr != null) (0 until arr.length()).map { arr.optString(it) } else emptyList()
                },
            )
        }
    }

    fun queryThreads(baseHttpUrl: String, daysBack: Int = 30): List<ThreadSummary> {
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/query/threads?days_back=$daysBack&limit=20")
            .get()
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            val raw = resp.body?.string() ?: throw RuntimeException("Empty response")
            if (!resp.isSuccessful) throw RuntimeException("HTTP ${resp.code}: $raw")
            val json = JSONObject(raw)
            val data = json.optJSONObject("data") ?: JSONObject()
            val threads = data.optJSONArray("threads") ?: JSONArray()
            return buildList {
                for (i in 0 until threads.length()) {
                    val item = threads.optJSONObject(i) ?: continue
                    add(
                        ThreadSummary(
                            id = item.optString("long_thread_id"),
                            summary = item.optString("summary"),
                            latestSummary = item.optString("latest_summary"),
                            continuityScore = item.optDouble("continuity_score", 0.0).toFloat(),
                            lastSeenAt = item.optString("last_seen_at"),
                            topics = jsonArrayToList(item.optJSONArray("top_topics")),
                            participants = jsonArrayToList(item.optJSONArray("top_participants")),
                        )
                    )
                }
            }
        }
    }

    fun fetchPersonInsights(baseHttpUrl: String, name: String): PersonInsightData {
        val encodedName = URLEncoder.encode(name, StandardCharsets.UTF_8.toString())
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/query/person/$encodedName")
            .get()
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            val raw = resp.body?.string() ?: throw RuntimeException("Empty response")
            if (!resp.isSuccessful) throw RuntimeException("HTTP ${resp.code}: $raw")
            val json = JSONObject(raw)
            val warning = json.optString("warning").ifBlank { null }
            val data = json.optJSONObject("data")
            if (data == null) {
                return PersonInsightData(
                    name = name,
                    interactionsCount = 0,
                    voiceReady = false,
                    neighbors = emptyList(),
                    recentTopics = emptyList(),
                    warning = warning,
                )
            }
            val person = data.optJSONObject("person") ?: JSONObject()
            val neighbors = data.optJSONArray("graph_neighbors")
            val recentInteractions = data.optJSONArray("recent_interactions")
            return PersonInsightData(
                name = person.optString("name", name),
                interactionsCount = data.optInt("interactions_count", 0),
                voiceReady = person.optBoolean("voice_ready", false),
                neighbors = buildList {
                    if (neighbors != null) {
                        for (i in 0 until neighbors.length()) {
                            val item = neighbors.optJSONObject(i)
                            item?.optString("name")?.takeIf { it.isNotBlank() }?.let(::add)
                        }
                    }
                },
                recentTopics = buildList {
                    if (recentInteractions != null) {
                        for (i in 0 until recentInteractions.length()) {
                            val item = recentInteractions.optJSONObject(i) ?: continue
                            safeJsonList(item.optString("topics_json")).forEach { topic ->
                                if (topic !in this) add(topic)
                            }
                            if (size >= 5) break
                        }
                    }
                },
                warning = warning,
            )
        }
    }

    fun fetchPersons(baseHttpUrl: String): List<PersonListItem> {
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/graph/persons")
            .get()
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            val raw = resp.body?.string() ?: throw RuntimeException("Empty response")
            if (!resp.isSuccessful) throw RuntimeException("HTTP ${resp.code}: $raw")
            val arr = parseRootArray(raw, "persons")
            return buildList {
                for (i in 0 until arr.length()) {
                    val item = arr.optJSONObject(i) ?: continue
                    add(PersonListItem(
                        name = item.optString("name"),
                        relationship = item.optString("relationship", "unknown"),
                        voiceReady = item.optBoolean("voice_ready", false),
                        sampleCount = item.optInt("sample_count", 0),
                        lastSeen = item.optString("last_seen").ifBlank { null },
                    ))
                }
            }
        }
    }

    fun fetchPending(baseHttpUrl: String): List<PendingApproval> {
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/graph/pending")
            .get()
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            val raw = resp.body?.string() ?: throw RuntimeException("Empty response")
            if (!resp.isSuccessful) throw RuntimeException("HTTP ${resp.code}: $raw")
            val arr = parseRootArray(raw, "pending")
            return buildList {
                for (i in 0 until arr.length()) {
                    val item = arr.optJSONObject(i) ?: continue
                    add(PendingApproval(
                        name = item.optString("name"),
                        sampleCount = item.optInt("sample_count", 0),
                        avgConfidence = item.optDouble("avg_confidence", 0.0).toFloat(),
                    ))
                }
            }
        }
    }

    fun approvePerson(baseHttpUrl: String, name: String) {
        val encodedName = URLEncoder.encode(name, StandardCharsets.UTF_8.toString())
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/graph/approve/$encodedName")
            .post("{}".toRequestBody(jsonMediaType))
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            if (!resp.isSuccessful) {
                val raw = resp.body?.string() ?: ""
                throw RuntimeException("HTTP ${resp.code}: $raw")
            }
        }
    }

    fun rejectPerson(baseHttpUrl: String, name: String) {
        val encodedName = URLEncoder.encode(name, StandardCharsets.UTF_8.toString())
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/graph/reject/$encodedName")
            .post("{}".toRequestBody(jsonMediaType))
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            if (!resp.isSuccessful) {
                val raw = resp.body?.string() ?: ""
                throw RuntimeException("HTTP ${resp.code}: $raw")
            }
        }
    }

    fun fetchBalanceInsights(baseHttpUrl: String, day: String): List<InsightCard> {
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/balance/insights?day=$day")
            .get()
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            val raw = resp.body?.string() ?: throw RuntimeException("Empty response")
            if (!resp.isSuccessful) throw RuntimeException("HTTP ${resp.code}: $raw")
            val json = JSONObject(raw)
            val arr = json.optJSONArray("insights") ?: JSONArray()
            return buildList {
                for (i in 0 until arr.length()) {
                    val item = arr.optJSONObject(i) ?: continue
                    // WHY: server returns "insight", not "text" — try both
                    add(InsightCard(
                        role = item.optString("role"),
                        text = item.optString("insight").ifBlank { item.optString("text") },
                    ))
                }
            }
        }
    }

    fun fetchMirrorPortrait(baseHttpUrl: String, daysBack: Int = 7): MirrorPortrait {
        val request = requestBuilder("${baseHttpUrl.removeSuffix("/")}/mirror/portrait?days_back=$daysBack")
            .get()
            .build()
        NetworkClients.sharedClient.newCall(request).execute().use { resp ->
            val raw = resp.body?.string() ?: throw RuntimeException("Empty response")
            if (!resp.isSuccessful) throw RuntimeException("HTTP ${resp.code}: $raw")
            val json = JSONObject(raw)
            return MirrorPortrait(
                daysBack = json.optInt("days_back", daysBack),
                topEmotions = buildList {
                    val arr = json.optJSONArray("top_emotions") ?: JSONArray()
                    for (i in 0 until arr.length()) {
                        arr.optJSONObject(i)?.optString("emotion")?.takeIf { it.isNotBlank() }?.let(::add)
                    }
                },
                topTopics = buildList {
                    val arr = json.optJSONArray("top_topics") ?: JSONArray()
                    for (i in 0 until arr.length()) {
                        arr.optJSONObject(i)?.optString("topic")?.takeIf { it.isNotBlank() }?.let(::add)
                    }
                },
                topPeople = buildList {
                    val arr = json.optJSONArray("top_people") ?: JSONArray()
                    for (i in 0 until arr.length()) {
                        arr.optJSONObject(i)?.optString("person")?.takeIf { it.isNotBlank() }?.let(::add)
                    }
                },
                avgSentiment = if (json.isNull("avg_sentiment")) null else json.optDouble("avg_sentiment", 0.0).toFloat(),
                episodesCount = json.optInt("episodes_count", 0),
                openCommitments = json.optInt("open_commitments", 0),
            )
        }
    }

    private fun requestBuilder(url: String): Request.Builder {
        val builder = Request.Builder().url(url)
        return ServerEndpointResolver.attachAuth(builder, url)
    }

    private fun parseDigestData(data: JSONObject): DigestSummaryData {
        return DigestSummaryData(
            summaryText = data.optString("summary_text").ifBlank {
                data.optJSONObject("verdict")?.optString("text")
            },
            keyThemes = jsonArrayToList(data.optJSONArray("key_themes")),
            emotions = extractEmotionList(data.opt("emotions")),
            balance = data.optJSONObject("balance")?.let { balanceJson ->
                BalanceInfo(
                    domains = buildList {
                        val domains = balanceJson.optJSONArray("domains") ?: JSONArray()
                        for (i in 0 until domains.length()) {
                            val item = domains.optJSONObject(i) ?: continue
                            add(
                                BalanceDomainInfo(
                                    domain = item.optString("domain"),
                                    score = item.optDouble("score", 0.0).toFloat(),
                                    mentions = item.optInt("mentions", 0),
                                    sentiment = item.optDouble("sentiment", 0.0).toFloat(),
                                )
                            )
                        }
                    },
                    balanceScore = balanceJson.optDouble("balance_score", 0.0).toFloat(),
                    alert = balanceJson.optString("alert").ifBlank { null },
                    recommendation = balanceJson.optString("recommendation").ifBlank { null },
                )
            },
        )
    }

    private fun parseEventsData(data: JSONObject): EventsSummaryData {
        val counter = linkedMapOf<String, Int>()
        val events = data.optJSONArray("events") ?: JSONArray()
        for (i in 0 until events.length()) {
            val item = events.optJSONObject(i) ?: continue
            safeJsonList(item.optString("topics_json")).forEach { topic ->
                counter[topic] = (counter[topic] ?: 0) + 1
            }
        }
        return EventsSummaryData(
            total = data.optInt("total", events.length()),
            topTopics = counter.entries.sortedByDescending { it.value }.take(5).map { it.key },
        )
    }

    private fun parseActions(array: JSONArray?): List<ActionItemData> {
        if (array == null) return emptyList()
        return buildList {
            for (i in 0 until array.length()) {
                val item = array.optJSONObject(i) ?: continue
                add(
                    ActionItemData(
                        text = item.optString("text"),
                        done = item.optBoolean("done", false),
                        urgency = item.optString("urgency", "medium"),
                    )
                )
            }
        }
    }

    private fun extractEmotionList(raw: Any?): List<String> {
        return when (raw) {
            is JSONArray -> buildList {
                for (i in 0 until raw.length()) {
                    when (val item = raw.opt(i)) {
                        is String -> if (item.isNotBlank()) add(item)
                        is JSONObject -> item.optString("emotion").takeIf { it.isNotBlank() }?.let(::add)
                    }
                }
            }
            is JSONObject -> listOfNotNull(
                raw.optString("primary").ifBlank { null },
                raw.optString("secondary").ifBlank { null },
            )
            else -> emptyList()
        }
    }

    private fun jsonArrayToList(array: JSONArray?): List<String> {
        if (array == null) return emptyList()
        return buildList {
            for (i in 0 until array.length()) {
                array.optString(i).takeIf { it.isNotBlank() }?.let(::add)
            }
        }
    }

    private fun safeJsonList(raw: String?): List<String> {
        if (raw.isNullOrBlank()) return emptyList()
        return try {
            jsonArrayToList(JSONArray(raw))
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun parseRootArray(raw: String, fieldName: String): JSONArray {
        val trimmed = raw.trim()
        return when {
            trimmed.startsWith("[") -> JSONArray(trimmed)
            trimmed.startsWith("{") -> JSONObject(trimmed).optJSONArray(fieldName) ?: JSONArray()
            else -> JSONArray()
        }
    }
}
