"""A4: Wikipedia/Wikidata descriptions (RU/KZ/EN) -> data/raw/wiki_YYYYMMDD.json.

Run: python -m pipeline.wiki
"""

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from rapidfuzz import fuzz

from pipeline.config import CACHE_DIR, RAW_DIR, USER_AGENT, latest_raw

WIKI_CACHE = CACHE_DIR / "wiki"
LANGS = ["ru", "kk", "en"]
SEARCH_KINDS = {
    ("tourism", "museum"), ("tourism", "gallery"), ("tourism", "attraction"),
    ("tourism", "viewpoint"), ("tourism", "artwork"),
    ("amenity", "theatre"), ("amenity", "arts_centre"),
}
MATCH_THRESHOLD = 85
PAUSE_S = 0.2

_ABBREV = re.compile(r"(?:\b(?:г|гг|им|ул|пр|т\.е|т\.к|св|ок|в|н\.э|до н\.э|см|др|пр|St|Mr|Dr|etc|e\.g|i\.e)|\b[А-ЯA-Z])\.$")


def first_sentences(text: str, n: int = 2) -> str:
    """First n sentences; does not split after abbreviations like 'г.' or 'им.' or initials."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    out, start = [], 0
    for m in re.finditer(r"[.!?…](?=\s+[«\"(]?[А-ЯЁӘҒҚҢӨҰҮҺІA-Z0-9])", text):
        chunk = text[start : m.end()]
        if _ABBREV.search(chunk):
            continue
        out.append(chunk.strip())
        start = m.end()
        if len(out) == n:
            return " ".join(out)
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return " ".join(out[:n])


def _norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"\(.*?\)", " ", s)  # "(Астана)" disambiguation
    s = re.sub(r"[«»\"'“”„]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


GENERIC = {
    "памятник", "мемориал", "музей", "театр", "галерея", "скульптура", "монумент", "стела",
    "бюст", "арт-объект", "арт", "объект", "парк", "кинотеатр", "библиотека", "достопримечательность",
    # Kazakh
    "ескерткіш", "ескерткіші", "мұражай", "мұражайы", "театры", "саябақ", "саябағы", "мүсін",
    "кітапхана", "кітапханасы", "монументі", "мемориалы",
}


# A "(...)" qualifier in a title is fine only if it points at Astana or an object type;
# "Жамбыл (Астраханский район)" is a village, not our monument.
_OK_QUALIFIER = re.compile(
    r"астан|нур-султан|нұр-сұлтан|акмол|astana|монумент|памятник|ескерткіш|мемориал|музей|театр|"
    r"здание|сооружение|парк|скульптур|monument|museum|theatre|building",
    re.I,
)


def name_matches(osm_name: str, wiki_title: str, threshold: int = MATCH_THRESHOLD) -> bool:
    """Accept a search hit only if the article title clearly is this place."""
    qualifier = re.search(r"\((.*?)\)", wiki_title)
    if qualifier and not _OK_QUALIFIER.search(qualifier.group(1)):
        return False
    a, b = _norm(osm_name), _norm(wiki_title)
    if not a or not b or all(tok in GENERIC for tok in a.split()):
        return False  # a bare "Памятник" can match anything
    return fuzz.token_set_ratio(a, b) >= threshold and fuzz.token_sort_ratio(a, b) >= 60


class Http:
    """GET with on-disk cache (sha1 of URL) so re-runs make 0 requests."""

    def __init__(self) -> None:
        self.requests = 0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        WIKI_CACHE.mkdir(parents=True, exist_ok=True)

    def get_json(self, url: str) -> dict | None:
        path = WIKI_CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        resp = None
        for attempt in range(4):
            time.sleep(PAUSE_S)
            self.requests += 1
            try:
                resp = self.session.get(url, timeout=20)
            except requests.RequestException as err:
                print(f"[wiki] request failed {url}: {err}")
                return None
            if resp.status_code != 429:
                break
            wait = min(int(resp.headers.get("Retry-After", "0") or 0) or 5 * (attempt + 1), 20)
            print(f"[wiki] 429, waiting {wait}s", flush=True)
            time.sleep(wait)
        if resp is None or resp.status_code == 429:
            return None
        data = resp.json() if resp.status_code == 200 else None
        if resp.status_code in (200, 404):  # cache definite answers only
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data


def summary(http: Http, lang: str, title: str) -> tuple[str, str] | None:
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'), safe='')}"
    data = http.get_json(url)
    if not data or data.get("type") == "disambiguation" or not data.get("extract"):
        return None
    page = data.get("content_urls", {}).get("desktop", {}).get("page") or f"https://{lang}.wikipedia.org/wiki/{quote(title)}"
    return first_sentences(data["extract"], 2), page


def sitelinks_batch(http: Http, qids: list[str]) -> dict[str, dict[str, str]]:
    """{qid: {lang: title}}; one Wikidata request per 50 ids."""
    out: dict[str, dict[str, str]] = {}
    for i in range(0, len(qids), 50):
        chunk = sorted(qids[i : i + 50])
        url = (
            "https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
            f"&props=sitelinks|claims&sitefilter=ruwiki|kkwiki|enwiki&ids={'|'.join(chunk)}"
        )
        entities = (http.get_json(url) or {}).get("entities", {})
        for qid, ent in entities.items():
            instance_of = {
                c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                for c in ent.get("claims", {}).get("P31", [])
            }
            if "Q5" in instance_of:  # a person (monument's subject), not the place itself
                continue
            links = ent.get("sitelinks", {})
            out[qid] = {lang: links[f"{lang}wiki"]["title"] for lang in LANGS if f"{lang}wiki" in links}
    return out


def search(http: Http, lang: str, name: str, city: str) -> str | None:
    url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=5"
        f"&srsearch={quote(name + ' ' + city)}"
    )
    data = http.get_json(url) or {}
    for hit in data.get("query", {}).get("search", []):
        if name_matches(name, hit["title"]):
            return hit["title"]
    return None


def search_titles(http: Http, tags: dict) -> dict[str, str]:
    """Russian name on ru.wiki first, then the (often Kazakh) name on kk.wiki."""
    if (ru := tags.get("name:ru")) and (t := search(http, "ru", ru, "Астана")):
        return {"ru": t}
    kk = tags.get("name:kk") or tags.get("name")
    if kk and (t := search(http, "kk", kk, "Астана")):
        return {"kk": t}
    name = tags.get("name")
    if name and name != ru and (t := search(http, "ru", name, "Астана")):
        return {"ru": t}
    return {}


def is_search_candidate(tags: dict) -> bool:
    if not tags.get("name"):
        return False
    if "historic" in tags:
        return True
    return any((k, tags.get(k)) in SEARCH_KINDS for k in ("tourism", "amenity"))


def build_item(http: Http, titles: dict[str, str], qid: str | None) -> dict | None:
    descriptions, urls = {}, {}
    for lang in LANGS:
        if lang in titles and (res := summary(http, lang, titles[lang])):
            descriptions[lang], urls[lang] = res
    if not descriptions:
        return None
    lang = next(l for l in LANGS if l in descriptions)
    return {
        "description": descriptions[lang],
        "lang": lang,
        "descriptions": descriptions,
        "source_url": urls[lang],
        "title": titles[lang],
        "wikidata": qid,
    }


def main() -> None:
    raw = json.loads(latest_raw("osm_").read_text(encoding="utf-8"))
    http = Http()
    items: dict[str, dict] = {}
    stats = {"candidates": 0, "via_wikidata": 0, "via_search": 0, "skipped": 0}
    elements = raw.get("elements", [])
    links = sitelinks_batch(http, [e["tags"]["wikidata"] for e in elements if e.get("tags", {}).get("wikidata")])

    for el in elements:
        tags = el.get("tags", {})
        qid = tags.get("wikidata")
        if not qid and not is_search_candidate(tags):
            continue
        stats["candidates"] += 1
        poi_id = f"osm_{el['type']}_{el['id']}"
        item = None
        if qid:
            item = build_item(http, links.get(qid, {}), qid)
            if item:
                stats["via_wikidata"] += 1
        if item is None and is_search_candidate(tags):
            if titles := search_titles(http, tags):
                item = build_item(http, titles, qid)
                if item:
                    stats["via_search"] += 1
        if item:
            items[poi_id] = item
        else:
            stats["skipped"] += 1

    now = datetime.now(timezone.utc)
    out = RAW_DIR / f"wiki_{now:%Y%m%d}.json"
    meta = {"collected_at": now.isoformat(timespec="seconds"), "requests": http.requests, **stats}
    out.write_text(json.dumps({"_meta": meta, "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[wiki] {stats} requests={http.requests} -> data/raw/{out.name}")


if __name__ == "__main__":
    main()
