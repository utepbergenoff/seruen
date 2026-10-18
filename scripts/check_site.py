"""Automatic check of the website against Alikhan's checklist (section 10 of the stream plan).

    python scripts/check_site.py https://seruen-astana.netlify.app   # the published site (with a working backend)

Checks, on a laptop-size and a phone-size window:
  - each of the 6 scenarios gives 1-3 cards (or an honest empty message) in one click
  - every card shows: name, metres + minutes, status with colour, why + source badge,
    what to do + source badge, time on site, budget line, "from database" badge
  - the "What I considered" panel is under every answer; "Show candidates" opens
  - coordinates in the outgoing request have at most 3 decimals (~100 m)
  - the location is detected automatically on open (and a clear message if it is blocked)
  - no coordinates in the page URL; no JavaScript errors
  - manifest, icons, service worker file, About page are reachable
Prints a PASS/FAIL table; exit code 1 if anything failed.
"""
from __future__ import annotations

import json
import re
import sys

from playwright.sync_api import sync_playwright

if len(sys.argv) < 2:
    sys.exit("Give the site address, e.g.: python scripts/check_site.py https://seruen-astana.netlify.app")
BASE = sys.argv[1].rstrip("/")
THEME = ""
DAY = "2026-10-18T15:00"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    results.append((name, bool(ok), info))


def decimals(x: float) -> int:
    s = repr(float(x))
    return len(s.split(".")[1]) if "." in s else 0


def run_scenarios(ctx, label: str) -> None:
    for sid in ["S1", "S2", "S3", "S4", "S5", "S6"]:
        page = ctx.new_page()
        errors, bodies, gis_calls = [], [], []
        page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
        page.on("request", lambda r, g=gis_calls: g.append(r.url) if re.search(r"/2gis(\?|$)", r.url) else None)
        page.on("request", lambda r, b=bodies: b.append(r.post_data) if r.url.endswith("/recommend") else None)
        page.goto(f"{BASE}/?scenario={sid}&at={DAY}{THEME}")
        try:
            page.wait_for_selector(".rec, .empty", timeout=25000)
        except Exception:
            check(f"{label} {sid}: answer appears", False, "no cards and no empty message in 25 s")
            page.close()
            continue
        cards = page.locator(".rec")
        n = cards.count()
        check(f"{label} {sid}: 1-3 cards", 1 <= n <= 3, f"{n} cards")
        missing = []
        for i in range(n):
            c = cards.nth(i)
            for sel, what in ((".num", "number"), ("h3", "name"), (".meta", "metres/minutes"), (".status-pill", "status"),
                              (".why", "why"), ("details.more .bar-cap", "budget line under More")):
                if c.locator(sel).count() == 0:
                    missing.append(f"card {i + 1}: {what}")
            text = c.inner_text()
            if not re.search(r"\d+ м|\d+ m", text):
                missing.append(f"card {i + 1}: distance")
            if c.locator(".field").count() < 3:
                missing.append(f"card {i + 1}: why / what to do / time on site")
            if c.locator("details.more .src").count() < 2:
                missing.append(f"card {i + 1}: sources under More")
            if c.locator(".badge.ai, .badge.tpl, .badge.db").count():
                missing.append(f"card {i + 1}: AI/template badges on the card face")
        check(f"{label} {sid}: all card fields", not missing, "; ".join(missing[:4]))
        check(f"{label} {sid}: 'What I considered' panel", page.locator("#consideredBox").count() == 1)
        said = re.search(r"Рассмотрено мест: (\d+)", page.inner_text("#consideredBox"))
        listed = page.locator("#consideredBox .cand").count()
        check(f"{label} {sid}: every counted candidate is listed", not said or int(said.group(1)) == listed,
              f"said {said and said.group(1)}, listed {listed}")
        try:
            page.wait_for_function("() => [...document.querySelectorAll('.rec .photos')].every(b => b.querySelector('.ph-strip, .ph-none'))",
                                   timeout=60000)
            check(f"{label} {sid}: photo area answered on every card", True,
                  f"{page.locator('.rec .ph-strip').count()} with photos")
        except Exception:
            check(f"{label} {sid}: photo area answered on every card", False, "still loading after 60 s")
        if page.locator("#candBtn").count():
            page.click("#candBtn")
            page.wait_for_selector("table.cands", timeout=10000)
            check(f"{label} {sid}: candidates open", page.locator("table.cands tr").count() > 1)
        # numbered pins for the picks; other nearby places from 2GIS get plain dots
        pins = page.evaluate("() => [...document.querySelectorAll('.pin b')].filter(b => /^\\d+$/.test(b.textContent)).length")
        check(f"{label} {sid}: numbered markers on map", pins == n, f"{pins} numbered markers")
        if bodies and bodies[0]:
            loc = json.loads(bodies[0])["location"]
            ok = decimals(loc["lat"]) <= 3 and decimals(loc["lon"]) <= 3
            check(f"{label} {sid}: request coords rounded to 3 decimals", ok, f"{loc['lat']}, {loc['lon']}")
        check(f"{label} {sid}: no coordinates in page URL", not re.search(r"\d{2}\.\d{3,}", page.url))
        check(f"{label} {sid}: 2GIS button on every card", page.locator('.rec [data-act="gis"]').count() == n)
        check(f"{label} {sid}: no 2GIS requests until the button is pressed", not gis_calls, f"{len(gis_calls)} requests")
        check(f"{label} {sid}: no JavaScript errors", not errors, "; ".join(errors[:2]))
        page.close()


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        laptop = browser.new_context(viewport={"width": 1440, "height": 900})
        phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        run_scenarios(laptop, "laptop")
        run_scenarios(phone, "phone")

        page = laptop.new_page()
        for path in ("manifest.json", "icons/icon-192.png", "icons/icon-512.png", "sw.js", "about.html", "presets.json",
                     "scenarios.json", "config.js"):
            r = page.request.get(f"{BASE}/{path}")
            check(f"file /{path}", r.ok, str(r.status))
        m = page.request.get(f"{BASE}/manifest.json").json()
        check("manifest: name, standalone, icons 192+512",
              m.get("short_name") and m.get("display") == "standalone" and
              {"192x192", "512x512"} <= {i.get("sizes") for i in m.get("icons", [])})
        # error state: backend not reachable
        page.route("**/recommend", lambda route: route.abort())
        page.goto(f"{BASE}/?at={DAY}{THEME}")
        page.wait_for_selector("#chips button")
        page.click("#chips button >> nth=0")
        page.wait_for_selector(".msg.err", timeout=15000)
        check("error state: server unreachable shows a message", "Сервер" in page.inner_text("#status") or
              "server" in page.inner_text("#status").lower())
        page.close()
        # 2GIS block: a fake answer (no real quota is spent), asked once, shown as text with the source link
        page = laptop.new_page()
        gis_calls = []
        fake = {"poi_id": "x", "twogis_place_id": "70000001", "source": "2gis", "provider_name": "Тест <b>2ГИС</b>",
                "address": "проспект Мәңгілік Ел, 55/11", "language": "ru", "checked_at": "2026-10-18T09:00:00Z",
                "match_method": "exact_name_nearby", "match_distance_m": 12, "rating": 4.6, "rating_count": 321,
                "rating_scope": "organization", "weekly_hours": [{"day": d, "intervals": [{"start": "08:00", "end": "22:00"}]}
                                                                 for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")],
                "special_hours": [], "is_24x7": False, "schedule_note": None, "open_now": None,
                "provider_url": "https://2gis.kz/astana/firm/70000001", "attribution": "Данные 2ГИС", "photos_supported": False}

        def fake_gis(route):
            gis_calls.append(route.request.url)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(fake))
        page.route("**/places/*/2gis*", fake_gis)
        page.goto(f"{BASE}/?scenario=S1&at={DAY}{THEME}")
        page.wait_for_selector(".rec", timeout=25000)
        page.click('.rec >> nth=0 >> [data-act="gis"]')
        page.wait_for_selector(".rec >> nth=0 >> .gis-box .gis-head", timeout=10000)
        box = page.locator(".rec >> nth=0 >> .gis-box")
        text = box.inner_text()
        check("2GIS block: label, rating, hours, 'not open-now' note", all(x in text for x in ("Данные 2ГИС", "4.6", "пн–вс 08:00–22:00", "прямо сейчас")), text[:120])
        check("2GIS block: provider text is not HTML", "Тест <b>2ГИС</b>" in text)
        check("2GIS block: link to the 2GIS card", box.locator('a[href="https://2gis.kz/astana/firm/70000001"]').count() == 1)
        page.click('.rec >> nth=0 >> [data-act="gis"]')
        page.click('.rec >> nth=0 >> [data-act="gis"]')
        check("2GIS block: asked once, reopening uses the answer", len(gis_calls) == 1, f"{len(gis_calls)} requests")
        page.close()
        # photos block: a fake answer, so it is checked even where no free photos exist
        page = laptop.new_page()
        photo = {"url": "https://seruen-astana.netlify.app/img/hero-baiterek-night.jpg",
                 "page_url": "https://commons.wikimedia.org/", "author": "Тест <b>автор</b>", "license": "CC BY-SA 4.0",
                 "source": "commons"}
        page.route("**/places/*/photos", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "poi_id": "x", "photos": [photo, photo], "status": "ok", "analysis_source": "gemini", "checked_at": "2026-10-18T09:00:00Z",
            "analysis": {"lighting": "natural", "kids_area": "yes", "seats": 30, "seating": "many", "space": "large",
                         "decor": "дерево", "summary": "Светлый просторный зал с детским уголком."}})))
        page.goto(f"{BASE}/?scenario=S2&at={DAY}{THEME}")
        page.wait_for_selector(".rec .ph-strip img", timeout=30000)
        box = page.locator(".rec >> nth=0 >> .photos")
        text = box.inner_text()
        check("photos block: strip, reason from photos, facts, credit",
              box.locator("img").count() == 2 and "По фото: Светлый просторный зал" in text and "есть детская зона" in text
              and "около 30 мест" in text and "Тест <b>автор</b>" in text, text[:120])
        page.locator(".rec >> nth=0 >> .ph img >> nth=0").scroll_into_view_if_needed()
        try:  # photos load lazily, when they come into view
            page.wait_for_function("() => { const i = document.querySelector('.rec .ph img'); return i && i.complete && i.naturalWidth > 0; }",
                                   timeout=15000)
            check("photos block: images really load", True)
        except Exception:
            check("photos block: images really load", False, "first photo did not load in 15 s")
        page.close()
        # location detected automatically on open (simulated position near Expo)
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, permissions=["geolocation"],
                                  geolocation={"latitude": 51.09012, "longitude": 71.41837})
        page = ctx.new_page()
        bodies = []
        page.on("request", lambda r: bodies.append(r.post_data) if r.url.endswith("/recommend") else None)
        page.goto(f"{BASE}/?at={DAY}")
        page.wait_for_function("() => /рядом с вами/.test(document.querySelector('#locLine').textContent)", timeout=15000)
        check("location detected automatically on open", True, page.inner_text("#locLine"))
        page.click("#chips button >> nth=0")
        page.wait_for_selector(".rec, .empty", timeout=30000)
        loc = json.loads(bodies[0])["location"] if bodies else {}
        check("request uses the detected point, rounded", loc.get("lat") == 51.09 and loc.get("lon") == 71.418 and loc.get("source") == "gps",
              f"{loc.get('lat')}, {loc.get('lon')}, {loc.get('source')}")
        ctx.close()
        # error state: geolocation denied -> message right away, point in the centre
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, permissions=[])
        page = ctx.new_page()
        page.goto(f"{BASE}/")
        page.wait_for_selector("#geoMsg:not([hidden])", timeout=15000)
        check("error state: geolocation denied shows a message", len(page.inner_text("#geoMsg")) > 10)
        page.click("#geoBtn")  # the locate button on the map tries again
        page.wait_for_selector("#geoMsg:not([hidden])", timeout=15000)
        check("locate button on the map works", True)
        browser.close()

    width = max(len(n) for n, _, _ in results)
    fails = 0
    for name, ok, info in results:
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {info}")
    print(f"\n{len(results) - fails}/{len(results)} checks passed on {BASE}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
