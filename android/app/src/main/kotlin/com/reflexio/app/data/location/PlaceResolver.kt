package com.reflexio.app.data.location

import com.reflexio.app.data.model.CachedLocation

// ПОЧЕМУ frequency-based clustering а не reverse geocoding API:
// 1) Работает офлайн 2) Не требует API ключа 3) Privacy-first — координаты не уходят наружу.
// Пользователь сам называет места после кластеризации.
object PlaceResolver {

    // ~100 метров — радиус кластера
    private const val CLUSTER_RADIUS_METERS = 100.0

    data class PlaceCluster(
        val centerLat: Double,
        val centerLng: Double,
        val count: Int,
        val label: String?,
    )

    /**
     * Кластеризует точки по близости. Простой greedy алгоритм:
     * берём первую неприсвоенную точку как центр, собираем все точки в радиусе.
     */
    fun clusterLocations(locations: List<CachedLocation>): List<PlaceCluster> {
        if (locations.isEmpty()) return emptyList()

        val remaining = locations.toMutableList()
        val clusters = mutableListOf<PlaceCluster>()

        while (remaining.isNotEmpty()) {
            val center = remaining.removeFirst()
            val nearby = remaining.filter { loc ->
                haversineMeters(center.latitude, center.longitude, loc.latitude, loc.longitude) <= CLUSTER_RADIUS_METERS
            }
            remaining.removeAll(nearby.toSet())

            val allPoints = listOf(center) + nearby
            clusters.add(
                PlaceCluster(
                    centerLat = allPoints.sumOf { it.latitude } / allPoints.size,
                    centerLng = allPoints.sumOf { it.longitude } / allPoints.size,
                    count = allPoints.size,
                    label = center.resolvedPlace,
                )
            )
        }

        return clusters.sortedByDescending { it.count }
    }

    /**
     * Присваивает resolvedPlace на основе близости к известным кластерам.
     */
    fun resolvePlace(
        location: CachedLocation,
        knownPlaces: Map<String, Pair<Double, Double>>,
    ): String? {
        for ((name, coords) in knownPlaces) {
            if (haversineMeters(location.latitude, location.longitude, coords.first, coords.second) <= CLUSTER_RADIUS_METERS) {
                return name
            }
        }
        return null
    }

    private fun haversineMeters(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
        val r = 6_371_000.0
        val dLat = Math.toRadians(lat2 - lat1)
        val dLng = Math.toRadians(lng2 - lng1)
        val a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2)) *
            Math.sin(dLng / 2) * Math.sin(dLng / 2)
        val c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
        return r * c
    }
}
