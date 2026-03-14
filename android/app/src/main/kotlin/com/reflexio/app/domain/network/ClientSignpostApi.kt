package com.reflexio.app.domain.network

import android.util.Log
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

object ClientSignpostApi {
    private const val TAG = "ClientSignpostApi"
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    fun postRouteResolution(
        source: String,
        routeKind: String,
        route: ServerEndpointResolver.RouteResolution,
    ) {
        val targetBaseUrl = when {
            route.debugBuild && route.isLocalPrimary -> route.primaryUrl
            else -> route.resolvedUrl
        }
        val baseHttpUrl = ServerEndpointResolver.wsToHttp(targetBaseUrl)
        val url = "${baseHttpUrl.removeSuffix("/")}/ingest/client-signpost"
        val body = JSONObject()
            .put("source", source)
            .put("route_kind", routeKind)
            .put("primary_url", route.primaryUrl)
            .put("resolved_url", route.resolvedUrl)
            .put("decision", route.decision)
            .put("is_local_primary", route.isLocalPrimary)
            .put("debug_build", route.debugBuild)
            .toString()
            .toRequestBody(jsonMediaType)

        val request = ServerEndpointResolver.attachAuth(Request.Builder().url(url), url)
            .post(body)
            .build()

        runCatching {
            NetworkClients.sharedClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    Log.w(TAG, "client signpost failed: code=${response.code}")
                }
            }
        }.onFailure { error ->
            Log.w(TAG, "client signpost failed: ${error.message}")
        }
    }
}
