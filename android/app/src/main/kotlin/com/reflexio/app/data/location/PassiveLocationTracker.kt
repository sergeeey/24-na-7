package com.reflexio.app.data.location

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Geocoder
import android.os.Build
import android.util.Log
import androidx.core.content.ContextCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import com.reflexio.app.data.model.CachedLocation
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.util.Locale
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
    private val geocoder: Geocoder? = try {
        if (Geocoder.isPresent()) Geocoder(context, Locale("ru")) else null
    } catch (_: Exception) { null }

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
                                    resolvedPlace = null, // resolved below
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
            }?.let { cached ->
                // WHY: reverse geocode to human-readable place name.
                // "43.238, 76.945" is useless in digest, "ул. Абая 150, Алматы" is useful.
                val place = resolvePlace(cached.latitude, cached.longitude)
                cached.copy(resolvedPlace = place)
            }
        } catch (e: Exception) {
            Log.w(TAG, "getCurrentLocation error", e)
            null
        }
    }

    // WHY: Geocoder on IO dispatcher — it does network I/O on older Android.
    // Returns short address: "ул. Абая 150" or "Алматы" as fallback.
    @Suppress("DEPRECATION")
    private suspend fun resolvePlace(lat: Double, lon: Double): String? {
        val gc = geocoder ?: return null
        return withContext(Dispatchers.IO) {
            try {
                val addresses = gc.getFromLocation(lat, lon, 1)
                if (addresses.isNullOrEmpty()) return@withContext null
                val addr = addresses[0]
                // WHY: thoroughfare (street) + subThoroughfare (house number) is most useful.
                // Fallback chain: street → locality → admin area.
                val street = addr.thoroughfare
                val house = addr.subThoroughfare
                val locality = addr.locality
                when {
                    street != null && house != null -> "$street $house"
                    street != null -> street
                    locality != null -> locality
                    else -> addr.adminArea
                }
            } catch (e: Exception) {
                Log.w(TAG, "Geocoder failed", e)
                null
            }
        }
    }
}
