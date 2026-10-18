"""Record the laptop parts of the demo video automatically (task D6), plus title/end cards.

    python scripts/record_clips.py https://seruen-astana.netlify.app   # the published site (with a working backend)
    python scripts/record_clips.py --cards-only       # only the title / problem / end cards

Output in docs/video/clips/: 1080p MP4 clips with a visible cursor and click ripples,
silent (the voice-over is recorded separately), and title/end card PNGs.
Uses the Google Chrome installed on this computer.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "video" / "clips"
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
if not ARGS and "--cards-only" not in sys.argv:
    sys.exit("Give the site address, e.g.: python scripts/record_clips.py https://seruen-astana.netlify.app")
BASE = (ARGS[0] if ARGS else "").rstrip("/")
DAY = "2026-10-18T15:00"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

CURSOR_JS = """
(() => {
  const add = () => {
    if (document.getElementById('__cur')) return;
    const c = document.createElement('div'); c.id = '__cur';
    c.style.cssText = 'position:fixed;left:-50px;top:-50px;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;' +
      'background:rgba(255,255,255,.85);border:3px solid #111;box-shadow:0 1px 6px rgba(0,0,0,.4);z-index:2147483647;pointer-events:none;' +
      'transition:transform .12s';
    document.body.appendChild(c);
    addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', e => {
      c.style.transform = 'scale(.7)';
      const r = document.createElement('div');
      r.style.cssText = `position:fixed;left:${e.clientX - 25}px;top:${e.clientY - 25}px;width:50px;height:50px;border-radius:50%;` +
        'border:3px solid #f59e0b;z-index:2147483646;pointer-events:none;transition:all .5s ease-out;opacity:1';
      document.body.appendChild(r);
      requestAnimationFrame(() => { r.style.transform = 'scale(1.8)'; r.style.opacity = '0'; });
      setTimeout(() => r.remove(), 600);
    }, true);
    addEventListener('mouseup', () => { c.style.transform = 'scale(1)'; }, true);
  };
  if (document.body) add(); else addEventListener('DOMContentLoaded', add);
})();
"""


class Director:
    """Small helpers so the recorded actions look like a person using the site."""

    def __init__(self, page):
        self.page = page
        self.page.mouse.move(700, 400)

    def pause(self, s: float):
        self.page.wait_for_timeout(int(s * 1000))

    def show(self, selector: str, block: str = "center"):
        self.page.eval_on_selector(selector, f"el => el.scrollIntoView({{behavior: 'smooth', block: '{block}'}})")
        self.pause(0.9)

    def click(self, selector: str, pause: float = 0.6):
        loc = self.page.locator(selector).first
        loc.scroll_into_view_if_needed()
        box = loc.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.mouse.move(x, y, steps=22)
        self.pause(0.35)
        self.page.mouse.click(x, y)
        self.pause(pause)

    def hover(self, selector: str, pause: float = 1.0):
        loc = self.page.locator(selector).first
        box = loc.bounding_box()
        self.page.mouse.move(box["x"] + min(box["width"] / 2, 140), box["y"] + box["height"] / 2, steps=20)
        self.pause(pause)

    def wait_answer(self):
        self.page.wait_for_selector(".rec, .empty", timeout=20000)
        self.page.wait_for_load_state("networkidle", timeout=15000)
        self.pause(1.2)


def clip_child(d: Director):
    """1:15-1:50 — laptop: 'Я у Хан Шатыра' -> 'С ребёнком' -> map with numbered markers, 18+ excluded, budget."""
    d.pause(1.5)
    d.click('#presets button[data-id="khan"]', 1.2)
    d.click("#chips button >> nth=2")
    d.wait_answer()
    d.show("#results", "start")
    d.pause(1.5)
    d.hover(".note.safety", 2.0)
    d.click(".rec >> nth=0", 1.8)
    d.hover(".rec >> nth=0 >> .bar-cap", 2.5)
    d.show(".rec >> nth=1", "center")
    d.pause(2.0)


def clip_expo(d: Director):
    """1:50-2:25 — 'Я у Экспо' -> 'Необычное на 1–2 часа' -> 'Что я учёл' -> 'Показать кандидатов'."""
    d.pause(1.0)
    d.click('#presets button[data-id="expo"]', 1.0)
    d.click("#chips button >> nth=3")
    d.wait_answer()
    d.show("#results", "start")
    d.pause(2.0)
    d.hover(".rec >> nth=0 >> .field >> nth=1", 2.0)
    d.show("#consideredBox", "start")
    d.pause(2.5)
    d.click("#candBtn", 1.2)
    d.show("table.cands", "start")
    d.pause(3.5)
    d.page.mouse.wheel(0, 260)
    d.pause(2.5)


def clip_honesty_night(d: Director):
    """2:25-2:50 — a place with unknown hours; simulated 23:00 changes the answer, safety notes appear."""
    d.pause(1.0)
    d.click('#presets button[data-id="baiterek"]', 1.0)
    d.click("#chips button >> nth=3")
    d.wait_answer()
    d.show("#results", "start")
    unknown = d.page.locator(".status-pill.st-unknown")
    if unknown.count():
        d.hover(".status-pill.st-unknown", 2.5)
    d.show("#askForm", "start")
    d.click("#ctxBox summary", 0.8)
    d.click("#whenAt", 0.4)
    d.page.fill("#whenAt", "2026-10-18T23:00")
    d.pause(1.2)
    d.click("#goBtn")
    d.wait_answer()
    d.show("#results", "start")
    d.hover(".note.safety", 3.0)
    d.pause(1.5)


def clip_extras(d: Director):
    """2:50-3:15 — 'Собрать маршрут' -> line on the map; Kazakh request -> Kazakh answer; weather; pirate mode."""
    d.pause(1.0)
    d.click('#presets button[data-id="expo"]', 1.0)
    d.click("#chips button >> nth=3")
    d.wait_answer()
    d.click("#routeBtn")
    d.page.wait_for_selector("#routeBox .route", timeout=15000)
    d.show("#routeBox", "center")
    d.pause(3.0)
    d.click('.lang button[data-lang="kk"]', 1.0)
    d.click('#presets button[data-id="khan"]', 1.0)
    d.click("#chips button >> nth=2")
    d.wait_answer()
    d.show("#results", "start")
    d.pause(2.5)
    d.show("#consideredBox", "start")
    d.pause(2.0)
    d.click("#pirateBtn", 1.0)
    d.show("#results", "start")
    d.pause(3.0)


def clip_phone_backup(d: Director):
    """Backup for 0:35-1:15 if the real phone recording fails: phone layout, 'Кофе и розетка'."""
    d.pause(1.5)
    d.click('#presets button[data-id="expo"]', 1.0)
    d.click("#chips button >> nth=0")
    d.wait_answer()
    d.pause(1.0)
    d.show(".rec >> nth=0", "start")
    d.pause(2.5)
    d.hover(".rec >> nth=0 >> .status-pill", 2.0)
    d.show(".rec >> nth=0 >> .actions", "center")
    d.pause(2.0)
    d.click(".rec >> nth=0 >> [data-act=map]", 2.5)


CLIPS = [
    ("02_laptop_child_khan_shatyr", clip_child, "laptop", "ru"),
    ("03_laptop_expo_unusual_candidates", clip_expo, "laptop", "ru"),
    ("04_laptop_honesty_night", clip_honesty_night, "laptop", "ru"),
    ("05_laptop_extras_route_kazakh_pirate", clip_extras, "laptop", "ru"),
    ("01b_phone_backup_coffee", clip_phone_backup, "phone", "ru"),
]

CARD_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;width:1920px;height:1080px;display:grid;place-items:center;font-family:-apple-system,"Segoe UI",sans-serif;
background:radial-gradient(circle at 30% 30%,#14b8a6 0,#0f766e 45%,#0b3d39 100%);color:#fff}}
.box{{text-align:center}} .logo{{font-size:140px}} h1{{font-size:150px;margin:10px 0}} p{{font-size:46px;margin:14px 0;opacity:.95}}
small{{display:block;font-size:34px;opacity:.8;margin-top:40px}}
</style></head><body><div class="box"><div class="logo">🧭</div><h1>{title}</h1><p>{line1}</p><p>{line2}</p><small>{line3}</small></div></body></html>"""


def to_mp4(src: Path, dst: Path, size: str) -> None:
    # Playwright records at the window's CSS size; scale up to the final size with a sharp filter
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={size}:flags=lanczos",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "18", "-r", "30", "-movflags", "+faststart", str(dst)], check=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_webm"
    tmp.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        # cards
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        cards = {
            "00_title_card.png": dict(title="Серуен", line1="ИИ-помощник по прогулкам в Астане",
                                      line2="Кейс НИЦ Smart City · Build with AI 2026",
                                      line3="Команда: Томирис · Ерлан · Алихан"),
            "00b_problem_card.png": dict(title="Что делать рядом?", line1="Карты знают, где что находится.",
                                         line2="Серуен отвечает: что делать рядом — сейчас, с моим временем,",
                                         line3="с ребёнком, в эту погоду — и честно говорит, в чём не уверен"),
            "99_end_card.png": dict(title="Спасибо!", line1="Сайт: seruen-astana.netlify.app",
                                    line2="Код: github.com/…/seruen", line3="Серуен — что делать рядом, сейчас и честно"),
        }
        for name, txt in cards.items():
            page.set_content(CARD_HTML.format(**txt))
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / name)
        page.close()

        for name, fn, kind, lang in ([] if "--cards-only" in sys.argv else CLIPS):
            if kind == "laptop":
                ctx = browser.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(tmp),
                                          record_video_size={"width": 1280, "height": 720})
                size = "1920:1080"
            else:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          record_video_dir=str(tmp), record_video_size={"width": 390, "height": 844})
                size = "780:1688"
            ctx.add_init_script(CURSOR_JS)
            page = ctx.new_page()
            page.goto(f"{BASE}/?at={DAY}&lang={lang}&preset=baiterek")
            page.wait_for_selector("#chips button")
            page.wait_for_load_state("networkidle", timeout=15000)
            fn(Director(page))
            video = page.video.path()
            ctx.close()
            to_mp4(Path(video), OUT / f"{name}.mp4", size)
            print(f"[clips] {name}.mp4", flush=True)
        browser.close()
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"[clips] saved to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
