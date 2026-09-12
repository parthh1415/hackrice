# Firebreak

**Reverse stress testing for overlapping portfolios.** Not "what if NVDA drops 20%", but
"what is the smallest drop that breaks this system, and what is the cheapest change that
prevents it". Built on the actual Q2 2026 13F filings of Citadel, Millennium, Point72,
Two Sigma and Renaissance.

HackRice 16 — Finance track, plus the Capital One and MathWorks challenges.
Full write-up in [`docs/devpost.md`](docs/devpost.md).

## Run it

```sh
git clone <this repo> && cd firebreak
python3 -m pip install numpy pytest      # the only dependencies
python3 -m pytest tests/ -q              # 281 passing
PYTHONPATH=src python3 -m firebreak.server
```

Then open <http://localhost:8765>.

`scripts/setup.sh` does the installs and the tests in one go, then prints the
server command.

Tested on Python 3.13; nothing here uses syntax newer than 3.8. numpy is the only
runtime dependency — the server is stdlib (`http.server`), because nothing should need
a pip install at 3am.

## Run it with no network

The holdings matrix (`data/cache/dataset.json`, one frozen quarter) is committed, and so
are 53 recorded answers in `data/cache/golden/` (420KB). The web fonts are vendored into
`web/fonts/` too, so not even the stylesheet reaches out. Nothing here touches the
internet unless you explicitly ask it to.

```sh
FIREBREAK_DEMO=1 PYTHONPATH=src python3 -m firebreak.server
```

Every `/api/` response then comes off disk, labelled `cached: true`, including for slider
positions that were never recorded — it serves the nearest recording and says which
settings it is actually of. `?demo=1` on any single request does the same thing for that
request.

You do not need the flag for this to save you. In live mode, an endpoint that throws —
EDGAR down, wifi gone — falls back to the recording on its own and puts the reason in
`fallback_reason`. The flag just skips the doomed attempt.

## Refreshing the data

The committed dataset is deliberately frozen. To move to a new quarter:

```sh
PYTHONPATH=src python3 scripts/refresh_dataset.py   # refetch from EDGAR, ~6s
PYTHONPATH=src python3 scripts/record_golden.py     # re-record, or the recordings lie
```

Do both or neither. The golden recordings are of specific numbers, and nothing will warn
you if the dataset moves out from under them.

## Tests

```sh
python3 -m pytest tests/ -q      # 281, no network required
```

The frontend has its own jsdom harnesses. They need one extra install, because
`tests/ui/node_modules/` is gitignored, **and a running server** — they drive the real
`web/app.js` against the real endpoints:

```sh
npm --prefix tests/ui install                     # once
FIREBREAK_DEMO=1 PYTHONPATH=src python3 -m firebreak.server &
node tests/ui/smoke.js           # the beats render
node tests/ui/provenance.js      # every number on screen traces to the payload
```

They catch the failure mode that matters most in a demo: a panel that renders empty
instead of throwing. With no server on 8765 every fetch fails and the output is noise,
so check the server is up before believing a red run.

## Layout

| | |
|---|---|
| `src/firebreak/engine.py` | the cascade — leverage breach, forced selling, price impact, repeat |
| `src/firebreak/search.py` | bisection for the smallest shock meeting a breach condition |
| `src/firebreak/stabilise.py` | the cheapest single position change that pushes the break point out |
| `src/firebreak/thirteenf.py` | EDGAR 13F-HR fetch, amendment handling, multi-CIK managers |
| `src/firebreak/api.py` | JSON endpoints and the golden-recording fallback |
| `src/firebreak/server.py` | stdlib dev server on 8765 |
| `web/` | the frontend, no build step |
| `matlab/` | optional `patternsearch` solver — see [`matlab/README.md`](matlab/README.md) |

MATLAB is optional. Without it the solver strip reads "SciPy-free Python · exhaustive
position scan" and everything still works; `matlab/README.md` covers wiring up the real
one.
