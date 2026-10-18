"""Conservative activity hints from names and source descriptions, never generated prose."""
import re


def activity(poi):
    text = " ".join(filter(None, (poi.name, poi.name_kk, poi.name_en,
                                 poi.description if poi.description_source != "generated" else "")))
    for kind, pattern in (
        ("cinema", r"кинотеатр|cinema|кинотеатрлар"),
        ("theatre", r"театр|theat(?:re|er)"),
        ("museum", r"музей|museum|мұражай|галере|gallery"),
        ("outdoor", r"памятник|монумент|скульптур|набережн|алле[яи]|сквер|monument|sculpture|embankment|ескерткіш|жағалау|детская площадка|playground|ойын алаңы"),
    ):
        if re.search(pattern, text, re.I):
            return kind
    return None


def outdoor_walk_place(poi):
    kind = activity(poi)
    if poi.indoor or kind in {"cinema", "theatre", "museum"}:
        return False
    return poi.category in {"park", "viewpoint"} or kind == "outdoor"
