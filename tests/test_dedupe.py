from pipeline.dedupe import dedupe, to_poi


def node(tags, id_=1, lat=51.128, lon=71.43):
    return {"type": "node", "id": id_, "lat": lat, "lon": lon, "tags": tags}


def test_cafe_becomes_indoor_coffee_with_mood_tags_and_unknown_accessibility():
    p = to_poi(node({"amenity": "cafe", "name": "Коктем", "internet_access": "wlan",
                     "outdoor_seating": "yes", "opening_hours": "Mo-Su 08:00-22:00"}))
    assert p["poi_id"] == "osm_node_1"
    assert p["category"] == "coffee"
    assert {"wi-fi", "терраса"} <= set(p["tags"])
    assert p["indoor"] is True and p["adult_only"] is False
    assert p["wheelchair"] == "unknown"
    assert p["opening_hours_raw"] == "Mo-Su 08:00-22:00" and p["hours_source"] == "osm"
    assert p["sources"] == ["osm"]


def test_mapping_rows_from_the_spec():
    bar = to_poi(node({"amenity": "pub", "name": "Chalet pub", "opening_hours": "Mo-Su 12:00-02:00"}))
    assert (bar["category"], bar["adult_only"], bar["kid_friendly"]) == ("night", True, False)
    assert "ночью" in bar["tags"]

    play = to_poi(node({"leisure": "playground", "name": "Площадка"}))
    assert (play["category"], play["kid_friendly"], play["indoor"]) == ("kids", True, False)

    lib = to_poi(node({"amenity": "library", "name": "Библиотека №3", "wheelchair": "limited"}))
    assert lib["category"] == "library" and {"тихо", "розетки", "бесплатно"} <= set(lib["tags"])
    assert lib["wheelchair"] == "limited"

    art = to_poi(node({"tourism": "artwork", "name": "Арт-объект на крыше"}))
    assert art["category"] == "unusual"

    mall = to_poi({"type": "way", "id": 7, "center": {"lat": 51.09, "lon": 71.40},
                   "tags": {"shop": "mall", "name": "Mega Silk Way"}})
    assert (mall["poi_id"], mall["category"], mall["indoor"], mall["lat"]) == ("osm_way_7", "shopping", True, 51.09)

    assert to_poi(node({"amenity": "bench"})) is None


def test_office_coworking_is_cowork_and_art_spaces_are_unusual():
    cw = to_poi(node({"office": "coworking", "name": "Astana Hub"}))
    assert cw["category"] == "cowork" and {"розетки", "wi-fi"} <= set(cw["tags"])
    assert to_poi(node({"amenity": "arts_centre", "name": "Sayajay аrt"}))["category"] == "unusual"
    assert to_poi(node({"amenity": "theatre", "name": "Астана Опера"}))["category"] == "culture"
    assert to_poi(node({"leisure": "escape_game", "name": "Клаустрофобия"}))["category"] == "unusual"
    assert to_poi(node({"amenity": "planetarium", "name": "Планетарий"}))["category"] == "unusual"


def test_dedupe_drops_duplicates_missing_coords_and_junk_with_reasons():
    rich = to_poi(node({"amenity": "cafe", "name": "Коктем", "opening_hours": "24/7", "website": "x"}, id_=1))
    poor = to_poi(node({"amenity": "cafe", "name": "Кафе Коктем"}, id_=2, lat=51.12815))  # ~17 m away
    far = to_poi(node({"amenity": "cafe", "name": "Коктем"}, id_=3, lat=51.14))  # another branch
    nocoord = to_poi({"type": "way", "id": 4, "tags": {"amenity": "cafe", "name": "Без точки"}})
    junk = to_poi(node({"amenity": "cafe", "name": "???"}, id_=5, lat=51.2))
    unnamed_cafe = to_poi(node({"amenity": "cafe"}, id_=6, lat=51.21))
    unnamed_playground = to_poi(node({"leisure": "playground"}, id_=7, lat=51.22))

    kept, dropped = dedupe([rich, poor, far, nocoord, junk, unnamed_cafe, unnamed_playground])

    assert {p["poi_id"] for p in kept} == {"osm_node_1", "osm_node_3", "osm_node_7"}
    reasons = {d["poi_id"]: d["reason"] for d in dropped}
    assert reasons == {"osm_node_2": "duplicate", "osm_way_4": "no_coords",
                       "osm_node_5": "junk_name", "osm_node_6": "no_name"}
    playground = next(p for p in kept if p["poi_id"] == "osm_node_7")
    assert playground["name"] == "Детская площадка"


def test_category_assumptions_are_kept_apart_from_osm_facts():
    lib = to_poi(node({"amenity": "library", "name": "Библиотека №3"}))
    assert {"тихо", "розетки", "бесплатно"} <= set(lib["tags"])  # still searchable
    assert set(lib["tags_inferred"]) == {"тихо", "розетки", "бесплатно"}  # but marked as assumption


def test_last_checked_is_the_osm_collection_date_not_today():
    from datetime import date
    p = to_poi(node({"amenity": "cafe", "name": "X"}), today=date(2026, 10, 1))
    assert p["last_checked"] == "2026-10-01"
