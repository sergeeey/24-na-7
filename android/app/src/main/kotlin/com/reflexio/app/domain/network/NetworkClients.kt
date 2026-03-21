package com.reflexio.app.domain.network

import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

object NetworkClients {
    val sharedClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(120, TimeUnit.SECONDS) // Увеличено до 120с для тяжелых вызовов /ask (LLM)
            .writeTimeout(30, TimeUnit.SECONDS)
            .pingInterval(20, TimeUnit.SECONDS)
            .build()
    }
}
