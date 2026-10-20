"""Great-circle distance and a simple, explainable travel-time estimate."""
import math

from .config import AVG_SPEED_KMPH, EARTH_RADIUS_KM, PREP_MIN, ROAD_CIRCUITY


def haversine_km(lat1, lon1, lat2, lon2, radius=EARTH_RADIUS_KM):
    """Great-circle distance in km.

    a = sin^2(dphi/2) + cos(phi1) cos(phi2) sin^2(dlambda/2);  d = 2 R asin(sqrt(a))
    """
    for v in (lat1, lon1, lat2, lon2):
        if not isinstance(v, (int, float)) or isinstance(v, bool) or math.isnan(v):
            raise ValueError("coordinates must be numbers")
    if abs(lat1) > 90 or abs(lat2) > 90 or abs(lon1) > 180 or abs(lon2) > 180:
        raise ValueError("latitude must be within +-90 and longitude within +-180")
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def road_km(straight_km):
    return straight_km * ROAD_CIRCUITY


def travel_minutes(straight_km, speed_kmph=AVG_SPEED_KMPH, prep_min=PREP_MIN):
    """Estimated minutes for a donor to reach the hospital: prep + road km / speed."""
    if straight_km < 0:
        raise ValueError("distance cannot be negative")
    return prep_min + road_km(straight_km) / speed_kmph * 60.0
