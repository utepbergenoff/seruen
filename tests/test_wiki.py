import pytest

from pipeline.wiki import accept_search_hit, first_sentences, name_matches

MONUMENT = {"historic": "monument", "name": "Бауыржан Момышұлы"}
THEATRE = {"amenity": "theatre", "name": "Театр кукол"}


def test_search_hit_must_be_about_astana_and_monuments_must_be_monument_articles():
    # real wrong hits from the Astana run
    assert not accept_search_hit(MONUMENT, "Момышулы, Бауыржан", "Советский офицер, Герой Советского Союза.")
    assert not accept_search_hit(THEATRE, "Гомельский театр кукол", "Кукольный театр в Гомеле.")
    assert not accept_search_hit({"tourism": "attraction", "name": "Атырау көпірі"}, "Атырау",
                                 "Город в европейской части Казахстана.")
    # real correct hits
    assert accept_search_hit({"historic": "memorial", "name": "Рақымжан Қошқарбаев"}, "Рақымжан Қошқарбаев ескерткіші",
                             "Рақымжан Қошқарбаев ескерткіші Астана қаласында 2016 жылы ашылды.")
    assert accept_search_hit({"amenity": "arts_centre", "name": "Астаналық Цирк"}, "Астаналық цирк",
                             "Астаналық цирк — Астана қаласының мәдениет басқармасына қарасты мекеме.")


@pytest.mark.parametrize("osm,title", [
    ("Байтерек", "Байтерек (монумент)"),
    ("Хан Шатыр", "Хан Шатыр"),
    ("Музей «Алжир»", "Музей Алжир"),
    ("Хан Шатыр", "Хан Шатыр (Астана)"),
    ("Национальный музей Республики Казахстан", "Национальный музей Республики Казахстан"),
])
def test_name_match_accepts_same_place(osm, title):
    assert name_matches(osm, title)


@pytest.mark.parametrize("osm,title", [
    ("Памятник", "Памятник Абаю (Астана)"),
    ("Мемориал", "Мемориал Защитникам Отечества"),
    ("Театр", "Астана Опера"),
    ("Музей", "Национальный музей Республики Казахстан"),
    ("Ескерткіш", "Ескерткіш Абайға"),
    ("Жамбыл", "Жамбыл (Астраханский район)"),  # monument vs a village of the same name
    ("Сарыарқа", "Сарыарқа (Карагандинская область)"),
])
def test_name_match_rejects_generic_or_different_names(osm, title):
    assert not name_matches(osm, title)


def test_first_sentences_keeps_two_and_skips_abbreviations():
    text = (
        "Музей был основан в 1999 г. по указу президента. "
        "Здание построено им. архитектора Норманом Фостером. "
        "Третье предложение не нужно."
    )
    assert first_sentences(text, 2) == (
        "Музей был основан в 1999 г. по указу президента. "
        "Здание построено им. архитектора Норманом Фостером."
    )
