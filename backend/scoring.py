def score(semantic, distance, radius, popularity, status, tag_match):
    proximity = max(0, 1 - distance / max(radius, 1))
    open_bonus = {"open": 1, "likely_open": 0.7, "unknown": 0.4, "closed": 0}[status]
    return 0.4 * semantic + 0.25 * proximity + 0.15 * popularity + 0.1 * open_bonus + 0.1 * tag_match
