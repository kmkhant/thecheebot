"""Small, dependency-free geo helpers."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8
_METERS_PER_DEGREE = 111_320.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bounding_box(
    lat: float, lon: float, radius_m: float
) -> tuple[float, float, float, float]:
    """Cheap lat/lon box around a point, for pre-filtering a spatial query.

    Longitudes may fall outside [-180, 180] when the box crosses the
    antimeridian; callers are expected to handle that wrap.
    """
    d_lat = radius_m / _METERS_PER_DEGREE
    min_lat = max(-90.0, lat - d_lat)
    max_lat = min(90.0, lat + d_lat)

    # Longitude lines converge at the poles, so the box gets very wide there.
    # Near a pole it may span every longitude, which is correct — not a wrap.
    cos_lat = math.cos(math.radians(max(-90.0, min(90.0, lat))))
    if cos_lat < 1e-9:
        return min_lat, max_lat, -180.0, 180.0

    d_lon = radius_m / (_METERS_PER_DEGREE * cos_lat)
    if d_lon >= 180.0:
        return min_lat, max_lat, -180.0, 180.0

    return min_lat, max_lat, lon - d_lon, lon + d_lon


def format_distance(meters: float) -> str:
    """Human-readable distance: '80 m', '1.4 km', '12 km'."""
    if meters < 950:
        return f"{int(round(meters / 10) * 10)} m"
    km = meters / 1000
    if km < 10:
        return f"{km:.1f} km"
    return f"{round(km)} km"
