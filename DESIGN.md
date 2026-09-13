# Minima — frontend design brief

This file is the source of truth for how the Minima UI looks and behaves.
Read it in full before touching anything in `web/`. Every prompt that touches the
frontend should be treated as "…following DESIGN.md".

If something here conflicts with what's already in the repo, stop and ask rather
than guessing. Do not redesign anything that is not explicitly listed in the work
order at the bottom.

---

## 0. Read before you write

Before generating any code, read these and work from what's actually there:

- `web/` — every file. Note the current page list, the ids and `data-*` hooks,
  and how each page reads from `sessionStorage`.
- `tests/ui/pages.js` — this harness walks the pages against live endpoints and
  compares on-screen numbers to the payload. **Every selector, id and data hook it
  depends on must survive this redesign unchanged.** If a rename is genuinely
  unavoidable, update the harness in the same commit and say so.
- `src/minima/api.py` — the real response shapes. Bind to real field names.
  Never invent a field, never hardcode a number that should come from a payload.
- `README.md` — the product argument and the voice. Both matter below.

Hard constraints that do not change:

- **No build step.** Plain HTML, CSS and ES modules served from `web/`. No bundler,
  no framework, no npm package in the served app.
- **No network at runtime.** No CDN fonts, no CDN scripts, no remote images.
  Fonts are vendored in `web/fonts/`, and that stays true.
- **No new runtime dependencies.** numpy stays the only one.
- Everything must still work under `MINIMA_DEMO=1`.
- Empty and error states render as states, not as blank panels. A panel that
  silently renders nothing is the failure mode this project cares most about.

---

## 1. The concept

Minima is a risk memo, not a dashboard.

The product's whole argument is a single line you refuse to cross, and the
discovery that the shock alone doesn't get you there — the crowding does. So the
interface is monochrome until something breaches. Ink on paper, disciplined,
dense, print-like. Red enters the page **only** where a limit is crossed, and
nowhere else. No red decoration, no red headings, no red buttons.

There is deliberately **no green.** "Safe" is not a color, it's the absence of red.
A PASS is set in ink like every other number on the page. This is the single most
important rule in this file — the moment green appears, the concept collapses into
a generic dashboard.

Reference vernacular: an annual report, an actuarial table, a broker's printed
risk note, an ordnance survey sheet. Not Bloomberg, not Stripe, not Linear.

---

## 2. Tokens

Write these to `web/tokens.css` first, before any page work. Nothing anywhere else
may introduce a raw hex value, a one-off font size, or a spacing number outside
this scale. If a page seems to need one, the page is wrong.

```css
:root {
  /* ground */
  --paper:        #E6E7E2;  /* page ground — cool grey-green stock */
  --paper-raised: #F1F2EE;  /* panels sit LIGHTER than the ground */
  --paper-sunk:   #DCDED8;  /* input wells, table zebra */

  /* ink */
  --ink:          #14181C;  /* all primary text and all figures */
  --ink-mid:      #5A6066;  /* labels, axis ticks, secondary prose */
  --ink-faint:    #8D9299;  /* disabled, placeholder, ghosted before-state */
  --rule:         #C6C9C2;  /* hairlines — 1px, never a shadow */

  /* the only color in the product */
  --loss:         #A61B14;  /* breach, and nothing else */
  --loss-wash:    rgba(166, 27, 20, 0.10);

  /* sequential ramp, boundary map only */
  --ramp-0: #E6E7E2;
  --ramp-1: #D3C3B8;
  --ramp-2: #C0937F;
  --ramp-3: #A8503C;
  --ramp-4: #A61B14;
  --ramp-5: #4A0D08;

  /* type */
  --font-prose: "Source Serif 4", Georgia, serif;
  --font-ui:    "IBM Plex Sans", system-ui, sans-serif;
  --font-num:   "IBM Plex Mono", ui-monospace, monospace;

  --t-micro: 12px;  /* axis ticks, footnotes */
  --t-label: 14px;  /* field labels, table headers */
  --t-body:  18px;  /* prose */
  --t-lead:  24px;  /* page lede */
  --t-head:  32px;  /* page title */
  --t-fig:   56px;  /* the one big figure per page */

  --lh-tight: 1.15;
  --lh-body:  1.55;

  /* space — 4px base, use only these */
  --s1: 4px; --s2: 8px; --s3: 12px; --s4: 16px;
  --s5: 24px; --s6: 32px; --s7: 48px; --s8: 72px;

  --radius: 0px;      /* everything. no exceptions. */
  --measure: 68ch;    /* max prose line length */
}
```

**Fonts.** Vendor Source Serif 4 (regular, semibold) and IBM Plex Sans + Plex Mono
(regular, medium) as woff2 into `web/fonts/`, subset to latin, `font-display: swap`,
declared with `@font-face` in `tokens.css`. All three are OFL. Do not add a fourth.

**Figures.** Every number on screen gets `font-variant-numeric: tabular-nums` and
`--font-num`. Numbers must not reflow or jitter when a value updates. Percentages
carry a sign only when the sign is meaningful (a shock is `−24.69%`, a loss is
`7.23%`). Use the real minus sign `−`, not a hyphen.

**Roles.** Serif for prose, ledes and page titles. Plex Sans for UI chrome, labels,
buttons and table headers. Plex Mono for figures only. Do not set body copy in mono.

---

## 3. Layout

A strict two-column page: a fixed 260px left rail, and a content column capped at
1040px, left-aligned within it. Never center the content column's text. Never
full-bleed.

```
┌──────────────┬──────────────────────────────────────────────┐
│ MINIMA    │  Break point                                 │
│              │  ─────────────────────────────────────────── │
│ 1 Portfolio ✓│  The smallest NVDA move that puts you past   │
│ 2 Limit     ✓│  the loss you said you would not accept.     │
│ 3 Break     ●│                                              │
│ 4 Cascade    │      −24.69%          ← one figure, --t-fig  │
│ 5 Fix        │      NVDA                                    │
│ 6 Validate   │                                              │
│ ─────────    │  ┌────────────────────────────────────────┐  │
│ Boundary     │  │ the page's one visual                  │  │
│ Model        │  │                                        │  │
│              │  └────────────────────────────────────────┘  │
│ demo · 14ms  │  direct 7.23%   after cascade 10.00%  1.38×  │
└──────────────┴──────────────────────────────────────────────┘
```

The rail is a **numbered stepper** because the product genuinely is a sequence
(Portfolio → Limit → Break → Cascade → Fix → Validate). Boundary and Model sit below
a rule as reference screens, unnumbered. Completed steps get a hairline tick, the
current step gets a filled square in ink. Do not number Boundary or Model.

Panels are separated by 1px `--rule` hairlines and whitespace. **No card shadows,
no border radius, no gradient anywhere in the product.** If a panel needs to read
as raised, it gets `--paper-raised` and a hairline, nothing else.

Tables are ledger tables: hairline above and below the header row, one hairline at
the foot, no vertical rules, no zebra unless a table runs past 8 rows. Figures
right-aligned, labels left-aligned.

The footer strip of the rail shows live/demo state and response time in
`--t-micro` `--ink-faint`. This is a judged demo — proving 11–20ms and
`cached: false` on screen is worth the pixels.

Responsive: below 900px the rail collapses to a horizontal stepper pinned to the
top, and the content column goes full width with `--s4` gutters. Everything must
be readable on a phone.

---

## 4. The hero: the cascade waterfall

This is where the entire budget goes. The gap between 7.23% and 10.00% is the
product's argument, and right now it's a number in a table. Make it the thing
people remember.

Hand-written SVG. No charting library, no d3.

- `viewBox="0 0 960 480"`, `preserveAspectRatio="xMidYMid meet"`, responsive width.
- Y axis is cumulative portfolio loss, **increasing downward from 0 at the top.**
  Loss falls. Domain 0 → max(limit, final) × 1.15.
- X axis is categorical bands: `Direct`, then `Round 1`, `Round 2`, … one band per
  cascade round in the payload. Never hardcode the round count.
- Each band is a waterfall segment: a filled rect starting at the previous
  cumulative value and ending at the new one, plus a 1px connector to the next band.
  Segments are `--ink` while cumulative is under the limit.
- The limit is a horizontal line across the full plot in `--loss`,
  `stroke-dasharray: 6 4`, labelled at the right edge: `your limit 10.00%`.
- **The crossing is the moment.** The segment in which cumulative crosses the limit
  is split at the crossing point: the portion above the line stays `--ink`, the
  portion below is `--loss`. Every subsequent segment is `--loss`. The area between
  the limit line and the final value gets `--loss-wash`.
- Below the plot, three figures in a row, hairline-separated:
  `direct 7.23%` · `after cascade 10.00%` · `amplification 1.38×`. Label above in
  `--t-label` `--ink-mid`, figure below in `--t-fig`-minus-one-step mono.

Motion — this is the product's **one** orchestrated moment, and the only non-user-
triggered animation in the whole app:

- On load, segments draw in left to right, 160ms each, 60ms stagger, ease-out.
  Total under 1s. The limit line is already drawn before the first segment moves.
- Nothing else in the product animates on entrance. No fade-and-slide-up on
  sections, no hover transitions on panels.
- Wrap the whole sequence in `@media (prefers-reduced-motion: reduce)` and render
  the final state instantly.

On the **Fix** page, the same component renders twice over each other: the
before-state as a 1px `--ink-faint` outline with no fill, the after-state filled on
top. One shock, two books — which is exactly the claim the README makes, so let the
picture make it.

---

## 5. Boundary map

Canvas, not SVG — it's a dense sweep and rects in 2D context are the right tool.
Sequential ramp `--ramp-0` → `--ramp-5`, no rainbow, no viridis, no diverging scale
unless the data actually diverges around a meaningful zero. Axis ticks in
`--t-micro` `--ink-mid` outside the plot. Crosshair readout on hover showing the
exact knob values and the value under the cursor, in mono, in a fixed-position
readout that does not follow the cursor around (it must not jitter).

Mark the current portfolio's configuration on the map with a small ink cross and a
label. Being able to point at "you are here" in the configuration space is worth
more than any legend.

---

## 6. Copy

The README is better written than anything generated fresh. Pull the argument onto
the screens:

- Break page lede: the shock is the trigger, the crowding is the damage.
- Fix page, above the fold: your position doesn't move the market, it decides how
  much of the market's move lands on you.
- Validate page: "stayed under your limit in 94% of our scenarios" — exactly that
  phrasing. Never render it as a probability of safety. The distinction is the
  point of the page.
- Historical replay: render the absent feature as a stated absence with the reason,
  not as a disabled button or a "coming soon". It's a credibility asset. Say what
  isn't there and why.

Rules: sentence case everywhere. **No ALL-CAPS labels, no tracked-out eyebrow text
above headings, no `A · B · C` middot strings, no `→` appended to button text.**
Buttons name what happens: `Find my break point`, not `Submit`. An action keeps the
same name through the flow. Errors say what broke and what to do, in the product's
voice, and never apologize.

---

## 7. Do not

- No green. No amber. No third color of any kind.
- No border radius, no box-shadow, no gradient.
- No emoji, no icon font, no icon library. If an icon is needed, inline a 1px-stroke
  SVG drawn to the same hairline weight as `--rule`.
- No Inter, no Roboto, no system-ui as a primary face.
- No mono for body copy or headings.
- No "cards". Panels are regions bounded by rules and space.
- No skeleton shimmer. A pending panel shows a hairline frame and the word `computing`
  in `--ink-faint`.
- No raw hex or ad-hoc px values outside `tokens.css`.
- No renaming of ids, classes or `data-*` hooks that `tests/ui/pages.js` reads.

---

## 8. Work order

One item per session. After each, run the harness and confirm green before moving on:

```
npm --prefix tests/ui install
MINIMA_DEMO=1 PYTHONPATH=src python3 -m minima.server &
node tests/ui/pages.js
```

1. `web/tokens.css` + vendored fonts + `@font-face`. No page changes yet.
2. Shell: the rail, the stepper, the content column, the live/demo footer strip.
   Applied to one page only, as the reference.
3. The cascade waterfall component, standalone, bound to the real `/api/cascade`
   payload. This is the largest single piece — build it before the remaining pages.
4. Break page, using the shell and the waterfall.
5. Portfolio, Limit, Fix, Validate — in that order, each reusing the shell.
6. Boundary map canvas.
7. Model page.
8. Responsive pass, then a keyboard and focus pass: every interactive element gets a
   visible 2px `--ink` focus ring, tab order follows reading order.

For each page, work to the geometry, not to a vibe. Before writing, state the grid
you're about to use in one sentence and what the page's single largest figure is.
Every page has exactly one hero figure — if you can't name it, the page isn't
designed yet.

## 9. Before you call a page done

- Does any number on screen come from anywhere other than the payload that produced it?
- Is there green on the page? Is there a second color?
- Does anything have a radius or a shadow?
- Would this page look the same if the subject were a project tracker? If yes, it's
  not designed for this brief yet — say what you're changing and change it.
- Does `node tests/ui/pages.js` pass?