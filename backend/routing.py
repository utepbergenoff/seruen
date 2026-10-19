"""Bounded calls to the existing free walking OSRM; no API keys or billable providers."""

import asyncio
import math
import time
from dataclasses import dataclass

import httpx

from .geo import haversine, in_astana

ENDPOINT = "https://routing.openstreetmap.de/routed-foot/route/v1/foot/"


@dataclass
class Routed:
    distances: list[int]
    minutes: list[int]
    geometry: list[list[float]]
    source: str
    error: str | None = None


class WalkingRouter:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport
        self.lock, self.last_call = asyncio.Lock(), 0.0

    @staticmethod
    def estimate(points, speed, error=None):
        distances = [math.ceil(haversine(a.lat, a.lon, b.lat, b.lon) * 1.3) for a, b in zip(points, points[1:])]
        return Routed(distances, [math.ceil(d / speed) for d in distances],
                      [[p.lon, p.lat] for p in points], "distance_estimate", error)

    async def route(self, points, speed):
        fallback = self.estimate(points, speed)
        if not self.settings.routing_enabled or self.settings.mock:
            return fallback
        if len(points) < 2 or all(d == 0 for d in fallback.distances):
            return fallback
        # Respect the public router's pace without turning rapid successive plan
        # calculations into straight lines. Wait only within this request: no jobs,
        # coordinate cache or retries. Under sustained load fail in bounded time.
        try:
            async with asyncio.timeout(2.5):
                async with self.lock:
                    delay = max(0, 1 - (time.monotonic() - self.last_call))
                    if delay:
                        await asyncio.sleep(delay)
                    self.last_call = time.monotonic()
        except TimeoutError:
            fallback.error = "routing_busy"
            return fallback
        coordinates = ";".join(f"{p.lon:.6f},{p.lat:.6f}" for p in points)
        try:
            async with httpx.AsyncClient(timeout=self.settings.routing_timeout_s, transport=self.transport,
                                         follow_redirects=False) as client:
                async with client.stream("GET", ENDPOINT + coordinates,
                                         params={"overview": "simplified", "geometries": "geojson",
                                                 "steps": "false", "radiuses": ";".join("100" for _ in points)},
                                         headers={"User-Agent": "SeruenAstana/1.0"}) as response:
                    if response.status_code != 200:
                        fallback.error = "routing_unavailable"
                        return fallback
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 500_000:
                            raise ValueError("oversized")
            import json
            body = json.loads(raw)
            if body.get("code") != "Ok":
                raise ValueError("no_route")
            route = body["routes"][0]
            legs, waypoints = route["legs"], body["waypoints"]
            if len(legs) != len(points) - 1 or len(waypoints) != len(points):
                raise ValueError("invalid_legs")
            for point, waypoint in zip(points, waypoints):
                lon, lat = waypoint["location"]
                if not in_astana(lat, lon) or haversine(point.lat, point.lon, lat, lon) > 100:
                    raise ValueError("remote_snapping")
            distances = []
            for i, leg in enumerate(legs):
                d = leg["distance"]
                straight = haversine(points[i].lat, points[i].lon, points[i+1].lat, points[i+1].lon)
                if type(d) not in (float, int) or not math.isfinite(d) or not 0 <= d <= 100_000:
                    raise ValueError("invalid_distance")
                # Include snapping uncertainty; never return less than direct distance.
                offsets = sum(haversine(p.lat, p.lon, w["location"][1], w["location"][0])
                              for p, w in zip(points[i:i+2], waypoints[i:i+2]))
                # A repeated venue/finish is the same place, not a trip to the street and back.
                # OSRM snaps indoor POIs to a street; charging both offsets here made a
                # zero-length finish leg take several minutes.
                distances.append(0 if straight < 0.5 else math.ceil(max(straight, d + offsets)))
            geometry = route["geometry"]["coordinates"]
            if len(geometry) > 5000 or len(geometry) < 2 or any(
                len(p) != 2 or not in_astana(p[1], p[0]) for p in geometry
            ):
                raise ValueError("invalid_geometry")
            # The pedestrian profile supplies street distances; personal/child pace supplies minutes.
            return Routed(distances, [math.ceil(d / speed) for d in distances], geometry, "osrm_foot")
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            fallback.error = "routing_unavailable"
            return fallback
