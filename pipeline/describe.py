"""A5: short descriptions for POI without a Wikipedia one -> data/raw/descriptions_YYYYMMDD.json.

Named places: Gemini, 1-2 neutral sentences from name/category/tags only, checked by
check_generated(); anything that fails the check falls back to the template.
Generic/unnamed places: template only. Every result is description_source="generated".
"""

import hashlib
import json
import os
import re
import sys
import time

from pipeline.config import CACHE_DIR

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
BATCH = 50  # free tier allows ~20 requests/day for flash: 820 named places -> ~17 calls
PAUSE_S = 7  # free tier ~10 requests/min
PROMPT = """Ты пишешь короткие описания мест в Астане для городского помощника.
Для каждого места ниже напиши 1–2 нейтральных предложения на русском языке ТОЛЬКО по фактам
из полей name, kind и features. Не придумывай детали (годы, адреса, меню, цены, отзывы, часы),
не используй слова «лучший», «самый», «уникальный». Не пиши «работает ночью» — только то, что в features.
Если фактов мало — одно короткое предложение. Пиши естественно, без конструкции «— это».
Верни JSON-массив объектов {"poi_id": ..., "description": ...} в том же порядке.

Места:
"""

KIND = {
    "coffee": "Кофейня", "food": "Кафе или ресторан", "park": "Парк или сквер", "kids": "Место для детей",
    "culture": "Место культуры", "viewpoint": "Достопримечательность", "shopping": "Торговый центр",
    "sport": "Спортивный объект", "night": "Бар", "unusual": "Необычное место",
    "library": "Библиотека", "cowork": "Коворкинг",
}
TAG_TEXT = {
    "wi-fi": "Wi-Fi", "терраса": "терраса", "розетки": "розетки", "тихо": "тихо", "кофе": "кофе",
    "бесплатно": "вход бесплатный", "ночью": "работает допоздна", "фото": "место для фото",
    "история": "исторический объект",
}


def template_description(poi: dict) -> str:
    if poi.get("name_generic"):
        return f"{poi['name']} по данным OpenStreetMap."
    text = f"{KIND[poi['category']]} «{poi['name']}»."
    features = [TAG_TEXT[t] for t in poi.get("tags", []) if t in TAG_TEXT]
    if features:
        text += " По данным OpenStreetMap: " + ", ".join(features) + "."
    return text


_HYPE = re.compile(r"лучш|самый|самая|самое|уникальн|легендарн|\bbest\b|\bfinest\b|ең жақсы", re.I)
_SENTENCE_END = re.compile(r"[.!?…](?:\s|$)")


def check_generated(text: str, poi: dict) -> str | None:
    """None if the generated description is acceptable, else a reason code."""
    text = (text or "").strip()
    if not text:
        return "empty"
    if _HYPE.search(text):
        return "hype"
    allowed = set(re.findall(r"\d+", " ".join([poi.get("name") or "", poi.get("opening_hours_raw") or ""])))
    if any(n not in allowed for n in re.findall(r"\d+", text)):
        return "invented_number"
    if len(_SENTENCE_END.findall(text)) > 2 or len(text) > 300:
        return "too_long"
    return None


def _gemini_batch(client, batch: list[dict]) -> dict[str, str]:
    from google.genai import types

    # human-readable tag meaning: the raw tag "ночью" only means "closes at 23:00 or later"
    items = [{"poi_id": p["poi_id"], "name": p["name"], "kind": KIND[p["category"]].lower(),
              "features": [TAG_TEXT[t] for t in p["tags"] if t in TAG_TEXT]} for p in batch]
    payload = json.dumps(items, ensure_ascii=False)
    path = CACHE_DIR / "gemini" / f"{hashlib.sha1((GEMINI_MODEL + payload).encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=PROMPT + payload,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
    )
    out = {r["poi_id"]: r["description"] for r in json.loads(resp.text) if "poi_id" in r}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    time.sleep(PAUSE_S)
    return out


def describe_all(records: list[dict], have_description: set[str]) -> tuple[dict[str, dict], dict]:
    """-> ({poi_id: {description, description_source, description_method}}, stats)."""
    from dotenv import load_dotenv

    load_dotenv()
    todo = [p for p in records if p["poi_id"] not in have_description]
    named = [p for p in todo if not p.get("name_generic")]
    stats = {"todo": len(todo), "llm": 0, "template": 0, "rejected": {}, "gemini_calls": 0, "model": None}
    generated: dict[str, str] = {}

    key = os.getenv("GEMINI_API_KEY")
    if key and named:
        from google import genai

        client = genai.Client(api_key=key)
        stats["model"] = GEMINI_MODEL
        for i in range(0, len(named), BATCH):
            try:
                generated.update(_gemini_batch(client, named[i : i + BATCH]))
                stats["gemini_calls"] += 1
            except Exception as err:  # quota/network/bad JSON: rest falls back to template
                print(f"[describe] Gemini stopped at batch {i // BATCH}: {str(err)[:200]}", file=sys.stderr)
                break
    elif not key:
        print("[describe] GEMINI_API_KEY not set -> template descriptions only")

    out: dict[str, dict] = {}
    for p in todo:
        text, method = generated.get(p["poi_id"]), "llm"
        reason = check_generated(text, p) if text else "missing"
        if reason:
            if text:
                stats["rejected"][reason] = stats["rejected"].get(reason, 0) + 1
            text, method = template_description(p), "template"
        stats[method] += 1
        out[p["poi_id"]] = {"description": text, "description_source": "generated", "description_method": method}
    return out, stats
