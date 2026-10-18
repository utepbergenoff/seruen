"""Everyday atmosphere choices. Visual claims require reviewed photos of this branch."""

PROFILES = {
    "light_cafe": {"categories": ["coffee", "food"], "scene": "indoor", "features": ["bright", "visible_seating"],
                   "titles": {"ru": "Светлое кафе", "kk": "Жарық кафе", "en": "Bright café"}},
    "green_inside": {"categories": ["coffee", "food", "shopping"], "scene": "indoor", "features": ["greenery"],
                     "titles": {"ru": "Зелень в интерьере", "kk": "Ішінде өсімдіктер бар", "en": "Plants indoors"}},
    "spacious_inside": {"categories": ["shopping", "coffee", "food", "library"], "scene": "indoor", "features": ["open_space"],
                        "titles": {"ru": "Просторно внутри", "kk": "Іші кең", "en": "Spacious indoors"}},
    "green_walk": {"categories": ["park"], "scene": "outdoor", "features": ["greenery", "open_space"],
                   "titles": {"ru": "Прогулка среди зелени", "kk": "Жасыл желекте серуен", "en": "A green walk"}},
}


def visual_tags(features):
    tags = set(features)
    if "natural_light" in tags:
        tags.add("bright")
    return tags


def apply_profile(request):
    profile = PROFILES.get(request.preferences.atmosphere_profile)
    if profile:
        if not request.preferences.preferred_categories:
            request.preferences.preferred_categories = profile["categories"].copy()
    return request
