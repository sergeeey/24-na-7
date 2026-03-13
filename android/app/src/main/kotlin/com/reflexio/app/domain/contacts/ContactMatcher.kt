package com.reflexio.app.domain.contacts

import com.reflexio.app.data.contacts.PhoneContact

// ПОЧЕМУ fuzzy: ASR даёт "Марат", контакт хранит "Марат Ибрагимов".
// Exact match не сработает. Но fuzzy должен быть консервативным —
// prefix match + короткие имена (< 3 символов) игнорируются чтобы "Ма" не матчил "Мария".
object ContactMatcher {

    private const val MIN_NAME_LENGTH = 3

    /**
     * Сопоставляет серверных людей (из ASR) с телефонными контактами.
     * Возвращает map: serverName → PhoneContact (или null если не нашли).
     */
    fun match(
        serverNames: List<String>,
        contacts: List<PhoneContact>,
    ): Map<String, PhoneContact?> {
        val contactIndex = contacts.associateBy { it.displayName.lowercase().trim() }
        val result = mutableMapOf<String, PhoneContact?>()

        for (serverName in serverNames) {
            val normalized = serverName.lowercase().trim()
            if (normalized.length < MIN_NAME_LENGTH) {
                result[serverName] = null
                continue
            }

            // 1. Exact match
            val exact = contactIndex[normalized]
            if (exact != null) {
                result[serverName] = exact
                continue
            }

            // 2. Prefix match: "Марат" matches "Марат Ибрагимов"
            val prefix = contacts.firstOrNull { contact ->
                val contactLower = contact.displayName.lowercase().trim()
                contactLower.startsWith(normalized) || normalized.startsWith(contactLower)
            }
            if (prefix != null) {
                result[serverName] = prefix
                continue
            }

            // 3. Contains match: "Ибрагимов" in "Марат Ибрагимов"
            val contains = contacts.firstOrNull { contact ->
                val contactLower = contact.displayName.lowercase().trim()
                contactLower.contains(normalized) || normalized.contains(contactLower)
            }
            result[serverName] = contains
        }

        return result
    }

    /**
     * Находит call log имя, наиболее похожее на серверное имя.
     * Call log использует CACHED_NAME из контактов — может отличаться от displayName.
     */
    fun matchCallLogName(
        serverName: String,
        callLogNames: Set<String>,
    ): String? {
        val normalized = serverName.lowercase().trim()
        if (normalized.length < MIN_NAME_LENGTH) return null

        // Exact
        callLogNames.firstOrNull { it.lowercase().trim() == normalized }?.let { return it }
        // Prefix
        callLogNames.firstOrNull {
            val n = it.lowercase().trim()
            n.startsWith(normalized) || normalized.startsWith(n)
        }?.let { return it }
        // Contains
        return callLogNames.firstOrNull {
            val n = it.lowercase().trim()
            n.contains(normalized) || normalized.contains(n)
        }
    }
}
