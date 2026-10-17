import math
from collections import Counter
from dataclasses import dataclass

from .embeddings import Embeddings, poi_text, tokenize
from .geo import default_stay, haversine, radius_for, speed, walk_minutes
from .hours import open_status
from .loader import canonical_name
from .schemas import Candidate, OpenStatus, POI
from .scoring import score


@dataclass
class Hit:
    poi: POI
    candidate: Candidate
    status: OpenStatus
    stay: int


@dataclass
class SearchResult:
    hits: list[Hit]
    excluded: list[Candidate]
    radius: float
    expanded: bool
    found: int
    reserve: int
    mode: str
    category_relaxed: bool = False


class Retriever:
    def __init__(self, dataset, index_path):
        self.pois = dataset.pois
        self.documents = [Counter(tokenize(poi_text(p))) for p in self.pois]
        self.lengths = [sum(d.values()) for d in self.documents]
        self.avg_length = sum(self.lengths) / max(len(self.lengths), 1)
        df = Counter(t for d in self.documents for t in d)
        self.idf = {t: math.log(1 + (len(self.pois) - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        try:
            self.embeddings = Embeddings(index_path, dataset)
        except (OSError, ValueError, KeyError, TypeError):
            self.embeddings = None
        self.mode = "bm25+lsa" if self.embeddings else "bm25"

    def relevance(self, text):
        terms = set(tokenize(text))
        bm25 = []
        for doc, length in zip(self.documents, self.lengths):
            value = sum(
                self.idf.get(t, 0) * doc[t] * 2.5 / (doc[t] + 1.5 * (0.25 + 0.75 * length / max(self.avg_length, 1)))
                for t in terms
            )
            bm25.append(value)
        maximum = max(bm25, default=0) or 1
        bm25 = [v / maximum for v in bm25]
        if self.embeddings is None:
            return bm25
        similarities = self.embeddings.similarities(text)
        return [0.5 * b + 0.5 * float(e) for b, e in zip(bm25, similarities)]

    def search(self, request, intent, now, airport_reserve=60):
        reserve = min(airport_reserve, intent.time_budget_min) if intent.before_flight else 0
        available = intent.time_budget_min - reserve
        stay = default_stay(available)
        walking_speed = speed(request, intent, now)
        night = now.hour >= 22 or now.hour < 6
        radius = radius_for(available, walking_speed, night)
        weather = request.context.weather
        severe = weather is not None and (weather.temp_c <= -15 or weather.wind_ms >= 10)
        if severe:
            radius = min(radius, 500)
        semantics = self.relevance(" ".join([request.query, *intent.tags, *intent.categories]))
        max_radius = 500 if severe else 1000 if night else float("inf")

        def collect(current_radius, expanded):
            hits, excluded = [], []
            for p, semantic in zip(self.pois, semantics):
                distance = math.ceil(haversine(request.location.lat, request.location.lon, p.lat, p.lon))
                walk = walk_minutes(distance, walking_speed)
                status = open_status(p, now)
                tags = set(tokenize(" ".join(p.tags)))
                matched = sorted(set(intent.tags) & tags)
                reason = None
                chosen_stay = min(stay, available - 2 * walk)
                min_stay = max(1, math.ceil(stay * 0.7)) if expanded else stay
                if p.category in intent.exclude_categories:
                    reason = "excluded_category"
                elif intent.companions == "child" and (p.adult_only or p.category == "night" or not p.kid_friendly):
                    reason = "not_child_friendly"
                elif intent.categories and p.category not in intent.categories:
                    reason = "category_mismatch"
                elif request.context.accessibility and p.wheelchair != "yes":
                    reason = "accessibility_unconfirmed"
                elif p.temporary and (
                    not p.event_start
                    or not p.event_end
                    or not p.event_source
                    or not p.event_start <= now <= p.event_end
                ):
                    reason = "event_unverified"
                elif status.state == "closed":
                    reason = "closed"
                elif distance > current_radius:
                    reason = "out_of_radius"
                elif chosen_stay < min_stay:
                    reason = "over_budget"
                elif night and not (p.indoor or {"lit", "busy", "освещено", "людно"} & set(p.tags)):
                    reason = "night_safety_unconfirmed"
                tag_match = len(matched) / max(len(intent.tags), 1)
                rank = score(semantic, distance, current_radius, p.popularity, status.state, tag_match)
                reasons = [f"tag:{t}" for t in matched]
                if severe and p.indoor:
                    rank += 0.15
                    reasons.append("indoor_weather_priority")
                if not reason:
                    reasons += ["within_radius", "within_budget"]
                candidate = Candidate(
                    poi_id=p.poi_id,
                    name=p.name,
                    category=p.category,
                    distance_m=distance,
                    walk_min=walk,
                    score=round(rank, 6),
                    reasons=reasons,
                    excluded_because=reason,
                )
                if reason:
                    excluded.append(candidate)
                else:
                    hits.append(Hit(p, candidate, status, chosen_stay))
            hits.sort(key=lambda h: (-h.candidate.score, h.candidate.distance_m, h.poi.poi_id))
            return hits, excluded

        hits, excluded = collect(radius, False)
        expanded = not hits
        if expanded:
            radius = min(radius * 1.5, max_radius)
            hits, excluded = collect(radius, True)
        found = len(hits)
        diversified, counts, chains = [], Counter(), set()
        for hit in hits:
            chain = canonical_name(hit.poi.chain or hit.poi.name)
            if counts[hit.poi.category] >= 2 or chain in chains:
                continue
            diversified.append(hit)
            counts[hit.poi.category] += 1
            chains.add(chain)
            if len(diversified) == 10:
                break
        return SearchResult(diversified, excluded, radius, expanded, found, reserve, self.mode)
