package com.reflexio.app.domain.network

import android.os.Build
import android.util.Log
import com.reflexio.app.BuildConfig
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Request

object ServerEndpointResolver {
    private const val TAG = "ServerEndpointResolver"
    private val localHosts = setOf("localhost", "127.0.0.1", "10.0.2.2")

    fun isEmulator(): Boolean =
        Build.FINGERPRINT.contains("generic")
                || Build.MODEL.contains("sdk", ignoreCase = true)
                || Build.MODEL.contains("Android SDK", ignoreCase = true)

    fun primaryWsUrl(): String =
        if (isEmulator()) BuildConfig.SERVER_WS_URL else BuildConfig.SERVER_WS_URL_DEVICE

    fun primaryHttpUrl(): String = wsToHttp(primaryWsUrl())

    fun fallbackWsUrl(): String? =
        BuildConfig.SERVER_WS_URL_FALLBACK.takeIf { it.isNotBlank() }

    fun fallbackHttpUrl(): String? =
        BuildConfig.SERVER_WS_URL_FALLBACK
            .takeIf { it.isNotBlank() }
            ?.let(::wsToHttp)

    fun wsToHttp(url: String): String =
        url.replace("ws://", "http://").replace("wss://", "https://")

    fun resolveUiHttpBaseUrl(): String {
        val primary = primaryHttpUrl()
        if (!shouldFallback(primary)) {
            Log.d(TAG, "resolveUiHttpBaseUrl primary=$primary fallback=skip")
            return primary
        }
        if (isReachable(primary)) {
            Log.d(TAG, "resolveUiHttpBaseUrl primary=$primary fallback=not_needed")
            return primary
        }
        val resolved = fallbackHttpUrl() ?: primary
        Log.d(TAG, "resolveUiHttpBaseUrl primary=$primary fallback=$resolved")
        return resolved
    }

    fun resolveBackgroundWsUrl(): String {
        val primary = primaryWsUrl()
        if (!shouldFallback(wsToHttp(primary))) {
            Log.d(TAG, "resolveBackgroundWsUrl primary=$primary fallback=skip")
            return primary
        }
        val resolved = fallbackWsUrl() ?: primary
        Log.d(TAG, "resolveBackgroundWsUrl primary=$primary fallback=$resolved")
        return resolved
    }

    fun resolveBackgroundHttpUrl(): String = wsToHttp(resolveBackgroundWsUrl())

    fun attachAuth(builder: Request.Builder, url: String): Request.Builder {
        val token = apiKeyForUrl(url)
        if (token.isNotBlank()) {
            builder.addHeader("Authorization", "Bearer $token")
        }
        return builder
    }

    fun apiKeyForUrl(url: String): String {
        val urlHost = url.toHttpUrlOrNull()?.host
        val fallbackHost = fallbackHttpUrl()?.toHttpUrlOrNull()?.host
        return if (urlHost != null && fallbackHost != null && urlHost == fallbackHost) {
            BuildConfig.SERVER_API_KEY_FALLBACK.ifBlank { BuildConfig.SERVER_API_KEY }
        } else {
            BuildConfig.SERVER_API_KEY
        }
    }

    fun userFacingError(message: String?, baseHttpUrl: String): String {
        val raw = message?.trim().orEmpty()
        if (raw.isBlank()) return "Не удалось связаться с сервером."
        val host = baseHttpUrl.toHttpUrlOrNull()?.host
        return when {
            raw.contains("127.0.0.1")
                    || raw.contains("localhost")
                    || raw.contains("failed to connect", ignoreCase = true)
                    || raw.contains("connection refused", ignoreCase = true)
                    || raw.contains("timeout", ignoreCase = true) -> {
                if (host != null && host in localHosts) {
                    "Локальный сервер недоступен. Проверь USB/adb reverse или переключись на боевой сервер."
                } else {
                    "Нет соединения с сервером. Проверь сеть и попробуй ещё раз."
                }
            }
            else -> raw
        }
    }

    private fun shouldFallback(httpUrl: String): Boolean =
        httpUrl.toHttpUrlOrNull()?.host in localHosts

    private fun isReachable(httpUrl: String): Boolean {
        return try {
            val request = Request.Builder()
                .url("${httpUrl.removeSuffix("/")}/health")
                .get()
                .build()
            NetworkClients.sharedClient.newCall(request).execute().use { response ->
                response.isSuccessful
            }
        } catch (_: Exception) {
            false
        }
    }

}
