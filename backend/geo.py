import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .schemas import Budget, Intent, RecommendRequest

ALMATY = ZoneInfo("Asia/Almaty")


def haversine(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def in_astana(lat, lon):
    return 51.00 <= lat <= 51.25 and 71.25 <= lon <= 71.65


def target_time(request: RecommendRequest, intent: Intent, current: datetime | None = None):
    now = request.context.now if request.context.simulate and request.context.now else current or datetime.now(ALMATY)
    now = now.astimezone(ALMATY)
    if intent.when == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    if intent.when in ("evening", "night"):
        hour = 18 if intent.when == "evening" else 23
        if now.hour < hour:
            return now.replace(hour=hour, minute=0, second=0, microsecond=0)
    return now


def speed(request, intent, now):
    winter = now.month in (11, 12, 1, 2, 3) or (
        request.context.weather is not None and request.context.weather.temp_c <= 0
    )
    return 60 if intent.companions == "child" or winter else 75


def default_stay(budget):
    return max(15, int(budget * 0.5))


def radius_for(budget, walking_speed, night=False):
    radius = max(0, (budget - default_stay(budget)) / 2 * walking_speed / 1.3)
    return min(radius, 1000) if night else radius


def walk_minutes(distance_m, walking_speed):
    return math.ceil(distance_m * 1.3 / walking_speed)


def budget_for(walk_min, stay_min, reserve=0, to_end=None):
    return Budget(
        walk_there_min=walk_min,
        stay_min=stay_min,
        walk_back_min=walk_min if to_end is None else 0,
        walk_to_end_min=to_end,
        reserve_min=reserve,
        total_min=walk_min + (walk_min if to_end is None else to_end) + stay_min + reserve,
    )
