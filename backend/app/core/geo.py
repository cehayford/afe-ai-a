"""Small geometry helpers.

Service areas and units use plain latitude/longitude so the app runs on SQLite in
development. On PostGIS these become spatial queries; the signatures stay the same.
"""

import math
from decimal import ROUND_HALF_UP, Decimal

EARTH_RADIUS_M = 6_371_000

LatLng = tuple[float, float]


def coord(value) -> Decimal:
    """Store coordinates at 6 decimal places (about 0.1 m), whatever the input type."""
    return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def distance_m(a: LatLng, b: LatLng) -> float:
    """Great-circle distance in metres (haversine)."""
    lat1, lng1 = map(math.radians, a)
    lat2, lng2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def polygon_contains(polygon: list[LatLng], point: LatLng) -> bool:
    """Ray-casting point-in-polygon test. Fine at neighbourhood scale."""
    lat, lng = point
    inside = False
    n = len(polygon)
    for i in range(n):
        lat_i, lng_i = polygon[i]
        lat_j, lng_j = polygon[(i - 1) % n]
        if (lng_i > lng) != (lng_j > lng):
            crossing_lat = (lat_j - lat_i) * (lng - lng_i) / (lng_j - lng_i) + lat_i
            if lat < crossing_lat:
                inside = not inside
    return inside
