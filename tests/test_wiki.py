import pytest

from pipeline.wiki import first_sentences, name_matches


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
