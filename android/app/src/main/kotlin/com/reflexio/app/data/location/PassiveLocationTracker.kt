package com.reflexio.app.data.location

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.util.Log
import androidx.core.content.ContextCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import com.reflexio.app.data.model.CachedLocation
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

// ПОЧЕМУ passive, а не continuous tracking: батарея важнее точности.
// Получаем текущее место раз в N минут (вызывается из Worker), не держим GPS постоянно.
class PassiveLocationTracker(private val context: Context) {

    companion object {
        private const val TAG = "PassiveLocationTracker"

        fun hasPermission(context: Context): Boolean {
            return ContextCompat.checkSelfPermission(
                context, Manifest.permission.ACCESS_FINE_LOCATION
            ) == PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(
                    context, Manifest.permission.ACCESS_COARSE_LOCATION
                ) == PackageManager.PERMISSION_GRANTED
        }
    }

    private val client: FusedLocationProviderClient =
        LocationServices.getFusedLocationProviderClient(context)

    @Suppress("MissingPermission")
    suspend fun getCurrentLocation(): CachedLocation? {
        if (!hasPermission(context)) return null

        return try {
            val cts = CancellationTokenSource()
            val priority = if (ContextCompat.checkSelfPermission(
                    context, Manifest.permission.ACCESS_FINE_LOCATION
                ) == PackageManager.PERMISSION_GRANTED
            ) {
                Priority.PRIORITY_BALANCED_POWER_ACCURACY
            } else {
                Priority.PRIORITY_LOW_POWER
            }

            suspendCancellableCoroutine { cont ->
                client.getCurrentLocation(priority, cts.token)
                    .addOnSuccessListener { location ->
                        if (location != null) {
                            cont.resume(
                                CachedLocation(
                                    latitude = location.latitude,
                                    longitude = location.longitude,
                                    accuracy = location.accuracy,
                                    timestampMs = location.time,
                                    resolvedPlace = null,
                                    syncedAt = System.currentTimeMillis(),
                                )
                            )
                        } else {
                            cont.resume(null)
                        }
                    }
                    .addOnFailureListener { e ->
                        Log.w(TAG, "Location fetch failed", e)
                        cont.resume(null)
                    }
                cont.invokeOnCancellation { cts.cancel() }
            }
        } catch (e: Exception) {
            Log.w(TAG, "getCurrentLocation error", e)
            null
        }
    }
}
