"""Screenshots of the 6 demo scenarios for the document (laptop + phone) and the text of each answer.

Run:
    python scripts/screenshots.py https://seruen-astana.netlify.app   # the published site (with a working backend)

Uses the Google Chrome installed on this computer (Playwright, channel="chrome").
Output: docs/screenshots/*.png and docs/screenshots/answers.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
if len(sys.argv) < 2:
    sys.exit("Give the site address, e.g.: python scripts/screenshots.py https://seruen-astana.netlify.app")
BASE = sys.argv[1].rstrip("/")
DAY = "2026-10-18T15:00"  # Sunday afternoon (S6 has its own 23:00 time inside the scenario)
SCENARIOS = ["S1", "S2", "S3", "S4", "S5", "S6"]


def wait_answer(page):
    page.wait_for_selector(".rec, .empty", timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(1200)  # map tiles fade in


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    answers = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        laptop = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1, locale="ru-RU")
        phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                    has_touch=True, locale="ru-RU")
        for sid in SCENARIOS:
            url = f"{BASE}/?scenario={sid}&at={DAY}&lang=ru"
            page = laptop.new_page()
            data = {}
            page.on("response", lambda r, d=data: d.update(json=r.json()) if r.url.endswith("/recommend") else None)
            page.goto(url)
            wait_answer(page)
            # right panel: show the request and the cards (presets block scrolled away)
            page.eval_on_selector("#askForm", "el => el.scrollIntoView({block: 'start'})")
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / f"{sid}_laptop.png")
            if data.get("json"):
                answers.append((sid, page.input_value("#query"), data["json"]))
            page.close()

            page = phone.new_page()
            page.goto(url)
            wait_answer(page)
            page.screenshot(path=OUT / f"{sid}_phone.png", full_page=True)
            page.close()
            print(f"[shots] {sid} done", flush=True)

        # extras for the document / slides
        page = laptop.new_page()
        page.goto(f"{BASE}/?scenario=S4&at={DAY}&lang=ru")
        wait_answer(page)
        page.click("#candBtn")
        page.wait_for_selector("table.cands")
        page.locator("#consideredBox").screenshot(path=OUT / "S4_candidates_panel.png")
        page.locator(".rec").first.screenshot(path=OUT / "S4_card.png")
        page.click("#routeBtn")
        page.wait_for_selector("#routeBox .route", timeout=15000)
        page.wait_for_timeout(1500)
        page.eval_on_selector("#routeBox", "el => el.scrollIntoView({block: 'center'})")
        page.wait_for_timeout(300)
        page.screenshot(path=OUT / "S4_route_laptop.png")
        page.close()

        page = laptop.new_page()
        page.goto(f"{BASE}/?scenario=S3&at={DAY}&lang=ru&pirate=1")
        wait_answer(page)
        page.eval_on_selector("#askForm", "el => el.scrollIntoView({block: 'start'})")
        page.wait_for_timeout(1500)  # pirate font
        page.screenshot(path=OUT / "extra_pirate_laptop.png")
        page.close()

        page = phone.new_page()
        page.goto(f"{BASE}/?chip=2&at={DAY}&lang=kk&preset=khan")
        wait_answer(page)
        page.screenshot(path=OUT / "extra_kazakh_phone.png", full_page=True)
        page.close()

        page = phone.new_page()
        page.goto(f"{BASE}/?at={DAY}&lang=ru")
        page.wait_for_selector("#chips button")
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / "start_phone.png")
        page.close()
        browser.close()

    lines = ["# Real answers of the 6 scenarios", "",
             f"Taken automatically from {BASE} with `python scripts/screenshots.py`; time simulated: {DAY} "
             "(S6: 23:00). Screenshots are in this folder: `S*_laptop.png`, `S*_phone.png`.", ""]
    for sid, q, d in answers:
        c = d.get("considered", {})
        lines += [f"## {sid} — «{q}»", "",
                  f"Mode: `{d.get('mode')}` · radius {c.get('radius_m')} m · budget {c.get('effective_budget_min')} min · "
                  f"candidates {c.get('candidates_found')} · time {c.get('time')}", ""]
        for i, r in enumerate(d.get("recommendations", []), 1):
            st = r.get("open_status", {})
            lines += [f"{i}. **{r['name']}** ({r.get('kind_label', r['category'])}) — {r['distance_m']} m, {r['walk_min']} min walk; "
                      f"status: {st.get('state')} ({st.get('source')}); on site ~{r['time_to_spend_min']} min",
                      f"   - Why: {r['why']}", f"   - What to do: {r['what_to_do']}"]
        for n in d.get("notes", []) + d.get("safety", []):
            lines.append(f"- _{n}_")
        lines.append("")
    (OUT / "answers.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "answers.json").write_text(json.dumps([{"id": s, "query": q, "answer": d} for s, q, d in answers],
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[shots] saved to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
