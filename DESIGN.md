# Серуен — design system: "Astana Line"

A working map app (Operate mode). The world lends type, palette, density and one signature move;
the layout and controls stay the ones every map app uses: work panel on the left, map on the right
(phone: map on top, panel as a sheet that slides over it).

**Scene:** people in Astana on a phone, mostly outdoors in bright cold daylight, deciding where to walk
in the next 15–120 minutes. Hence a light, high-contrast screen and big touch targets.

## Signature move

Walking time drawn as a line that starts where the person stands.
- **Time ruler** (`.ruler`) opens every answer: «Я здесь» (sun-gold dot) on the left, each pick as a
  numbered station at its walking minutes, the minutes in a sun-gold capsule. Picks only a minute or two
  apart are spread so labels never overlap; the labels always show the exact minutes.
- **Map:** the person is the gold dot, picks are numbered stations, a dotted sky line runs from the
  person to each pick. Other nearby places (2GIS) are small sky dots.
- **Card:** the same station number, and a capsule "N мин пешком · M м".
- Motion: only the ruler draws itself (line, then stations), plus the walker on the loading trail.
  Everything is visible without motion (`prefers-reduced-motion` turns it off).

## Tokens (`frontend/styles.css` `:root`)

| Role | Value |
|---|---|
| Sky (Kazakh flag blue): lines, ruler, focus ring, map lines | `--sky #00AFCA` |
| Shell bar, primary links, station rings | `--sky-deep #00708A` |
| Dark text on sky tints | `--sky-ink #0A4A5A`, tint `--sky-tint #E1F3F7` |
| Sun (flag gold): time capsules, the person, main button | `--sun #FFC20E`, hover `--sun-deep #F0AE00`, tint `--sun-tint #FFF4CF` |
| Text / secondary text | `--ink #0F2230` / `--muted #4E626D` |
| Ground / surface / lines | `--ground #F1F6F8` / `--surface #FFF` / `--line #D4E2E8`, `--line-soft #E6EEF1` |
| States (open, likely, unknown, closed) | `--ok`, `--maybe`, `--unk`, `--bad` with `-bg` tints |
| Radii | `--r-s 8px`, `--r 12px`, `--r-l 18px`; pills 999px |
| Motion easing | `--ease cubic-bezier(.16, 1, .3, 1)` |

No state emblems (eagle, sun from the flag): only the flag's colours.

## Type

- **Unbounded** 500/700 (display): brand, hero title, section titles, every number that is time or a
  station (ruler, card number, minutes).
- **Golos Text** 400–700 (UI and body): a wayfinding/UI face. Both ship Cyrillic-ext, so Kazakh letters
  (ә ғ қ ң ө ұ ү һ і) render in the same face.
- Minutes and counts use tabular numerals.

## Components

- Buttons: one shape, full pills. Secondary buttons are white with a 1px line; actions inside a card are soft
  filled pills (ground tone, no outline). The main action («Подобрать») is sun gold with ink text.
  Focus: 3px sky outline. On a phone every button and fold line is at least 44px tall.
- Icons: one drawn set (`<symbol id="i-…">` in `index.html`, 24px grid, 1.8 stroke, round caps), used via
  `icon(name)` in `app.js`. No emoji as icons.
- Cards: white, 18px radius, flat (no shadow at rest); hover and the active card change only the border to
  sky. Shadows are kept for what floats: menus and the map tools. No coloured side borders on cards or notes.
- Photos: a mosaic, one large frame and two small ones; facts as sky-tint chips with icons; credits under it.
- Notes from the server: plain small muted text, one line each; safety notes in amber text.
- Details the spec requires but people rarely need (what to do, time on site, budget, sources, accessibility)
  live in the «Подробнее» fold at the bottom of each card.

## Polish 19.10 (no control removed)

- The brand name in sentence case; header actions without outlines.
- Phone: the header is two compact rows; all actions sit in one row that scrolls sideways inside itself
  (the page never scrolls sideways). The welcome is shorter so «Чего хотите?» is on the first screen; the
  map tools hide their label and take less of the map. «О данных и приватности» is reachable on the phone.
- Fixed: the selected atmosphere chip («Любая атмосфера») was white text on white (an undefined `--bg`).
- Checked by replaying a recorded session on laptop and phone: same controls before and after (0 missing).
