package com.reflexio.app.data.contacts

import android.content.ContentResolver
import android.provider.ContactsContract

data class PhoneContact(
    val displayName: String,
    val normalizedNumber: String?,
)

// ПОЧЕМУ ContentResolver а не Contacts Provider напрямую:
// тестируемость — можно подменить resolver в тестах.
object ContactsReader {

    fun readContacts(resolver: ContentResolver): List<PhoneContact> {
        val contacts = mutableListOf<PhoneContact>()
        val projection = arrayOf(
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
            ContactsContract.CommonDataKinds.Phone.NORMALIZED_NUMBER,
        )
        resolver.query(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            projection,
            null,
            null,
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME + " ASC",
        )?.use { cursor ->
            val nameIdx = cursor.getColumnIndexOrThrow(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
            val numberIdx = cursor.getColumnIndexOrThrow(ContactsContract.CommonDataKinds.Phone.NORMALIZED_NUMBER)
            val seen = mutableSetOf<String>()
            while (cursor.moveToNext()) {
                val name = cursor.getString(nameIdx) ?: continue
                if (!seen.add(name.lowercase())) continue
                contacts.add(
                    PhoneContact(
                        displayName = name,
                        normalizedNumber = cursor.getString(numberIdx),
                    )
                )
            }
        }
        return contacts
    }
}
