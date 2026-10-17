import pytest

from pipeline.enrich import haversine_m, match, plan_cells

# ~0.0001 deg lat = 11 m in Astana
BASE_LAT, BASE_LON = 51.1280, 71.4300


def osm(poi_id, name, dlat=0.0, dlon=0.0):
    return {"poi_id": poi_id, "name": name, "lat": BASE_LAT + dlat, "lon": BASE_LON + dlon}


def g(pid, name, dlat=0.0, dlon=0.0):
    return {"id": pid, "name": name, "lat": BASE_LAT + dlat, "lon": BASE_LON + dlon}


def test_same_place_nearby_is_matched_far_or_different_name_is_not():
    pois = [osm("osm_node_1", "Коктем"), osm("osm_node_2", "Арасан", dlat=0.01)]
    places = [g("G1", "Коктем", dlat=0.0001), g("G2", "Арасан", dlat=0.0111), g("G3", "Бургер Кинг", dlat=0.01)]
    out = match(pois, places)
    assert out["osm_node_1"]["google_place_id"] == "G1"
    assert out["osm_node_1"]["distance_m"] < 50
    assert "osm_node_2" not in out  # G2 has the right name but is ~120 m away


def test_generic_words_and_quotes_are_ignored_in_names():
    out = match([osm("osm_node_1", "Кафе «Коктем»")], [g("G1", "Коктем", dlon=0.0002)])
    assert out["osm_node_1"]["google_place_id"] == "G1"


def test_real_astana_pairs_with_extra_words_or_latin_spelling_are_matched():
    pairs = [("Хива", "Хива, Астана Нурсултан"), ("Кабачок", "Кабачок пивной бар"),
             ("Фархи", "restaurant FARHI"), ("Мюллер", "Muller"), ('Бар "Томпсон"', 'BAR "Thompson"')]
    for i, (o, gname) in enumerate(pairs):
        out = match([osm(f"osm_node_{i}", o)], [g(f"G{i}", gname, dlat=0.0001)])
        assert f"osm_node_{i}" in out, (o, gname)


def test_unrelated_neighbours_are_not_matched():
    # real near-misses from the Astana run: same building, different business
    for o, gname in [("Mega", "Coffee Boom"), ("Арарат", "Кафе «Сафия»"), ("Дастархан", 'Избушка "Достык"')]:
        assert match([osm("osm_node_1", o)], [g("G1", gname, dlat=0.0001)]) == {}, (o, gname)


def _covered(poi, cells):
    return any(haversine_m(poi["lat"], poi["lon"], c["lat"], c["lon"]) <= c["radius_m"] for c in cells)


def test_plan_cells_covers_every_poi_and_skips_empty_areas():
    pois = [osm("a", "x"), osm("b", "y", dlat=0.05, dlon=0.05)]  # two spots ~6.5 km apart
    cells = plan_cells(pois)
    assert len(cells) == 2
    assert all(_covered(p, cells) for p in pois)
    assert plan_cells([]) == []


def test_dense_cell_is_split_so_each_call_can_return_all_its_places():
    # 45 places spread over ~400 m x 850 m (one 1 km cell)
    dense = [osm(f"p{i}", "x", dlat=0.0004 * (i % 10), dlon=0.003 * (i // 10)) for i in range(45)]
    cells = plan_cells(dense, max_per_cell=20)
    assert len(cells) > 1
    assert all(_covered(p, cells) for p in dense)


def test_plan_refuses_to_exceed_the_call_cap():
    spread = [osm(f"p{i}", "x", dlat=0.02 * (i % 10), dlon=0.02 * (i // 10)) for i in range(40)]
    with pytest.raises(ValueError):
        plan_cells(spread, cap=10)


def test_one_google_place_is_never_merged_into_two_osm_records():
    pois = [osm("osm_node_1", "Коктем"), osm("osm_way_2", "Коктем", dlat=0.0002)]
    out = match(pois, [g("G1", "Коктем", dlat=0.0001)])
    assert [v["google_place_id"] for v in out.values()] == ["G1"]
