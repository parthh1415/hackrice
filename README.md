# Firebreak

**Reverse stress testing for your portfolio.** Not "what if NVDA drops 20%", but "what is
the smallest drop that pushes *my* portfolio past the loss I refuse to tolerate — and what
is the smallest change that buys me distance from it".

Most stress tests make you guess the scenario first, and the scenario is the part nobody
checks. Firebreak solves backwards: you name the failure, it finds the shock.

The loss is not just the shock. Crowded institutions hold the same names you do; when one
is forced to deleverage, its selling moves the price of everything else it holds, and that
reaches you. Firebreak models that feedback on the actual Q2 2026 13F filings of Citadel,
Millennium, Point72, Two Sigma and Renaissance, then shows you the cascade round by round.

Then it recommends the smallest position change that helps — and **tests whether the
recommendation actually helped**, by replaying the identical shock, recomputing the new
break point, and scoring both portfolios across hundreds of simulated stress scenarios.

```
Portfolio  →  Risk limit  →  Firebreak  →  Cascade  →  Fix  →  Validate
```

Two modes, one engine:

| | |
|---|---|
| **Portfolio Mode** (default) | Your holdings. Fails when *you* cross your loss limit. |
| **Risk Desk Mode** | Many leveraged books. Fails when *N funds* breach. The prime-brokerage question. |

HackRice 16 — Finance track, plus the Capital One and MathWorks challenges.
Full write-up in [`docs/devpost.md`](docs/devpost.md).

## Run it

```sh
git clone <this repo> && cd firebreak
python3 -m pip install numpy pytest      # the only dependencies
python3 -m pytest tests/ -q              # 305 passing
PYTHONPATH=src python3 -m firebreak.server
```

Then open <http://localhost:8765>.

`scripts/setup.sh` does the installs and the tests in one go, then prints the
server command.

Tested on Python 3.13; nothing here uses syntax newer than 3.8. numpy is the only
runtime dependency — the server is stdlib (`http.server`), because nothing should need
a pip install at 3am.

## The product loop

Everything below runs with no network and no account. `Try demo portfolio` is the path a
judge takes; CSV is the path a user takes.

```
$ curl -s localhost:8765/api/portfolio/full?limit=0.10
```

On the demo portfolio ($12,300 across five names), at a 10% loss limit:

| | |
|---|---|
| Break point | **NVDA −24.69%** |
| Direct loss | 7.23% |
| After cascade | **10.00%** |
| Amplification | 1.38× |
| Fix | reduce NVDA by **$478** (13.3% of the position, to cash) |
| Same shock, after | 10.00% FAIL → **9.00% PASS** |
| New break point | −24.69% → **−27.76%** (+3.07pp) |
| Worst of 400 simulated | 11.94% → **10.73%** |

The gap between 7.23% and 10.00% is the entire argument: the shock is the trigger, the
crowding is the damage.

### Why your fix does not change the cascade

Your portfolio is an **observer**. The institutions deleverage identically whether or not
you trim NVDA — a retail account does not move markets, and pretending otherwise would be
the most flattering lie this app could tell. What your change alters is how much of that
price path lands on you.

*Your position doesn't move the market. It decides how much of the market's move lands on
you.*

### What the validation does and does not claim

Three tests ship and one does not.

- **Same shock** — one cascade, both portfolios scored against it. Only the weights differ,
  and that is enforced by running the cascade once rather than promised in a caption.
- **New break point** — the same reverse search, re-run. Recomputed, never inferred from
  the size of the cut.
- **Simulated stress** — 400 sampled shocks, both portfolios on *identical* draws, seeded so
  it reproduces. "Stayed under your limit in 94% of our scenarios" is a fact about our
  scenarios. "94% chance you are safe" is a fact about the world, and we do not have one.
- **Historical replay** — **not available**, and says so. We ship one frozen quarter of
  holdings and no price history. Building it on invented returns would put a confident
  number with nothing beneath it on the screen that exists to show evidence. There is a
  test asserting the feature is absent.

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
python3 -m pytest tests/ -q      # 305, no network required
```

The frontend has its own jsdom harness. It needs one extra install, because
`tests/ui/node_modules/` is gitignored, **and a running server** — it walks all six
pages against the real endpoints, carrying sessionStorage forward the way a browser
does, and compares every number on screen against the payload that produced it:

```sh
npm --prefix tests/ui install                     # once
FIREBREAK_DEMO=1 PYTHONPATH=src python3 -m firebreak.server &
node tests/ui/pages.js
```

It catches the failure mode that matters most in a demo: a panel that renders a
plausible wrong number, or renders empty instead of throwing. With no server on 8765
every fetch fails and the output is noise, so check the server is up before believing
a red run.

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
