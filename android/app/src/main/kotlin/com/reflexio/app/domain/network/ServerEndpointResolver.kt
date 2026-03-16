package com.reflexio.app.domain.network

import android.os.Build
import android.util.Log
import com.reflexio.app.BuildConfig
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Request

object ServerEndpointResolver {
    private const val TAG = "ServerEndpointResolver"
    private val localHosts = setOf("localhost", "127.0.0.1", "10.0.2.2")

    data class RouteResolution(
        val primaryUrl: String,
        val resolvedUrl: String,
        val decision: String,
        val isLocalPrimary: Boolean,
        val debugBuild: Boolean,
    )

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
        return resolveUiHttpRoute().resolvedUrl
    }

    fun resolveBackgroundWsUrl(): String {
        return resolveBackgroundWsRoute().resolvedUrl
    }

    fun resolveUiHttpRoute(): RouteResolution {
        return resolveRoute(
            primary = primaryHttpUrl(),
            fallback = fallbackHttpUrl(),
            logLabel = "resolveUiHttpBaseUrl",
        )
    }

    fun resolveBackgroundWsRoute(): RouteResolution {
        return resolveRoute(
            primary = primaryWsUrl(),
            fallback = fallbackWsUrl(),
            logLabel = "resolveBackgroundWsUrl",
        )
    }

    private fun resolveRoute(primary: String, fallback: String?, logLabel: String): RouteResolution {
        val localPrimary = shouldFallback(wsToHttp(primary))
        if (!localPrimary) {
            Log.d(TAG, "$logLabel primary=$primary fallback=skip")
            return RouteResolution(
                primaryUrl = primary,
                resolvedUrl = primary,
                decision = "primary_direct",
                isLocalPrimary = false,
                debugBuild = BuildConfig.DEBUG,
            )
        }
        if (shouldPinLocalDebugRoute()) {
            Log.w(TAG, "$logLabel primary=$primary fallback=disabled_for_debug_local")
            return RouteResolution(
                primaryUrl = primary,
                resolvedUrl = primary,
                decision = "local_debug_pinned",
                isLocalPrimary = true,
                debugBuild = BuildConfig.DEBUG,
            )
        }
        if (isReachable(wsToHttp(primary))) {
            Log.d(TAG, "$logLabel primary=$primary fallback=not_needed")
            return RouteResolution(
                primaryUrl = primary,
                resolvedUrl = primary,
                decision = "primary_reachable",
                isLocalPrimary = true,
                debugBuild = BuildConfig.DEBUG,
            )
        }
        val resolved = fallback ?: primary
        Log.d(TAG, "$logLabel primary=$primary fallback=$resolved")
        return RouteResolution(
            primaryUrl = primary,
            resolvedUrl = resolved,
            decision = if (resolved == primary) "primary_unreachable_no_fallback" else "fallback_remote",
            isLocalPrimary = true,
            debugBuild = BuildConfig.DEBUG,
        )
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

    fun isLocalUrl(url: String): Boolean =
        url.toHttpUrlOrNull()?.host in localHosts

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
                    "Локальный сервер недоступен. Проверь USB/adb reverse и что локальный backend запущен."
                } else {
                    "Нет соединения с сервером. Проверь сеть и попробуй ещё раз."
                }
            }
            else -> raw
        }
    }

    private fun shouldFallback(httpUrl: String): Boolean =
        httpUrl.toHttpUrlOrNull()?.host in localHosts

    // WHY: ранее debug-сборка на реальном устройстве ВСЕГДА пыталась ws://localhost:8000
    // и никогда не переходила на prod fallback. Это ломало приложение без adb reverse.
    // Теперь: если primary (localhost) недоступен → fallback на prod сервер.
    private fun shouldPinLocalDebugRoute(): Boolean = false

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
