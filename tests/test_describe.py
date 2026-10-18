from pipeline.describe import check_generated, template_description


def poi(**kw):
    base = {"poi_id": "osm_node_1", "name": "Коктем", "category": "coffee", "tags": ["wi-fi", "терраса", "крытое"],
            "opening_hours_raw": None, "name_generic": False}
    return {**base, **kw}


def test_template_names_the_kind_of_place_and_its_tags_without_inventing():
    text = template_description(poi())
    assert text.startswith("Кофейня")
    assert "Wi-Fi" in text and "терраса" in text
    assert text.count(".") <= 2


def test_check_generated_accepts_neutral_short_text():
    assert check_generated("Кофейня «Коктем» с Wi-Fi и летней террасой.", poi()) is None


def test_check_generated_rejects_hype_invented_numbers_and_wrong_length():
    p = poi()
    assert check_generated("", p) == "empty"
    assert check_generated("Лучшая кофейня города.", p) == "hype"
    assert check_generated("The best coffee in Astana.", p) == "hype"
    assert check_generated("Кофейня открыта с 2015 года.", p) == "invented_number"
    assert check_generated("Раз. Два. Три предложения.", p) == "too_long"
    assert check_generated("Кофейня «Коктем» №3 с Wi-Fi.", poi(name="Коктем №3")) is None  # number from the name is fine


def test_template_for_unnamed_playground_says_only_what_the_data_says():
    text = template_description(poi(name="Детская площадка", category="kids", tags=[], name_generic=True))
    assert text == "Детская площадка по данным OpenStreetMap."


def test_template_never_presents_category_assumptions_as_osm_facts():
    lib = poi(name="Библиотека №3", category="library", tags=["тихо", "розетки", "бесплатно", "wi-fi"],
              tags_inferred=["тихо", "розетки", "бесплатно"])
    text = template_description(lib)
    assert "Wi-Fi" in text and "тихо" not in text and "розетки" not in text


def test_generated_text_must_name_the_place():
    assert check_generated("Уютная кофейня с Wi-Fi.", poi()) == "wrong_place"


def test_template_does_not_repeat_the_kind_when_the_name_already_says_it():
    assert template_description(poi(name="Библиотека", category="library", tags=[])) == "Библиотека."
    assert template_description(poi(name="Центральная библиотека", category="library", tags=[])) == "Центральная библиотека."
