# Firebreak — Design Spec

**Date:** 2026-09-12
**Event:** HackRice 16 — Finance track (1 track) + Capital One, MathWorks, and any other challenges we qualify for
**Hard deadline:** Sunday 2026-09-13, 09:00 CDT (Devpost submission closes; hacking stops)

---

## 1. Thesis

Every stress test asks *"what if this happens?"* Firebreak asks the inverse:

> **What is the smallest shock that breaks this system, and what is the cheapest change that prevents it?**

Forward direction (the simulator) is a known model. The product is the two optimisations wrapped around it:
a search for the minimum-norm breaking shock, and a search for the minimum-cost stabilising intervention.

**Framing line (use this, not a novelty claim):** reverse stress testing is already *mandatory* for banks
under the UK PRA (ICAAP/SREP supervisory statement) and EBA stress-testing guidelines. Regulators require
firms to find the scenarios that break them. No interactive tool does this for overlapping portfolios.
We are building the missing instrument for a practice that is already law.

---

## 2. What has been verified (not assumed)

Everything in this section was checked live on 2026-09-12. This is the empirical core of the project.

### 2.1 SEC 13F ingest works

- `https://data.sec.gov/submissions/CIK{cik:010d}.json` → filing index. **Requires a `User-Agent`
  header containing contact info**, or SEC returns 403.
- Latest `13F-HR` accession → `https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json`
  → the information table is the non-`primary_doc` `.xml` file.
- Citadel's Q2 2026 table is **7.8 MB / 16,127 rows**. Parse time is negligible.

### 2.2 Three gotchas that would have cost hours

1. **Options contaminate the table.** Citadel's 16,127 rows are 8,500 shares / 4,014 calls / 3,613 puts.
   Naively summing `value` overstates equity exposure by ~half. **Filter out any row with a non-empty
   `putCall` element.**
2. **XML namespaces break `ElementTree`.** The table declares default, `n1:`, and `xsi:` namespaces.
   Regex extraction over `<infoTable>…</infoTable>` blocks is faster and more robust than namespace-
   stripping. Confirmed working in `spikes/13f_overlap_spike.py`.
3. **Rows duplicate per issuer** (one per internal manager). Aggregate by CUSIP before use.

Two smaller ones: responses may be gzip-encoded; and holdings are keyed by **CUSIP, not ticker**.
Since our universe is ~10 assets, we hardcode the CUSIP→ticker map. That single decision is what
makes this a 2-hour job instead of a 4-hour one.

### 2.3 The crowding is real — the cascade does not need to be rigged

Five firms, latest `13F-HR`, weights within a 10-name mega-cap universe. Note that five firms is
**six registrants**: Two Sigma Investments (CIK 1179392) and Two Sigma Advisers (CIK 1478735) file
separate 13Fs for the same quarter and both books belong to the same firm, so they are summed into
one row. See `data/universe.json`, where a manager may map to a list of CIKs.

Total book across the five: **$40.9B** (Citadel 14.6, Two Sigma 9.17, Millennium 7.69, Renaissance
6.33, Point72 3.09).

> **Corrected 2026-09-12** after external review. The first version of this table
> mapped only Alphabet Class C and used superseded filings. Both are fixed below;
> GOOGL weights move by up to 9×. See §2.4.
>
> **Re-verified 2026-09-12** against `data/cache/dataset.json` after the Two Sigma
> second-registrant fix. Every cell below matches the live matrix to 1 dp, and the
> overlap figures below match to 4 dp.

| Fund | NVDA | AAPL | MSFT | AMZN | GOOGL | META | AVGO | AMD | TSLA | JPM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Citadel | 16.2% | 14.5% | 9.6% | 17.8% | 15.3% | 4.3% | 7.5% | 6.4% | 3.5% | 5.0% |
| Millennium | 31.6% | 2.8% | 20.6% | 12.8% | 4.7% | 9.5% | 1.8% | 6.5% | 5.3% | 4.4% |
| Point72 | 2.8% | 0.0% | 0.4% | 34.3% | 12.2% | 10.3% | 12.5% | 25.0% | 0.0% | 2.5% |
| Two Sigma | 13.7% | 13.2% | 7.4% | 14.9% | 11.1% | 4.1% | 2.3% | 9.6% | 13.1% | 10.6% |
| Renaissance | 22.4% | 7.3% | 0.0% | 8.6% | 21.9% | 18.0% | 5.1% | 7.3% | 7.4% | 2.0% |

Period of report **2026-06-30** for all five (checked, not assumed).

Pairwise overlap (cosine similarity of weight vectors):

- **Mean off-diagonal: 0.712** (0.7117 live)
- **Max: 0.92** (Citadel ↔ Two Sigma — near-identical books; 0.9187 live)
- **Min: 0.44** (Millennium ↔ Point72; 0.4433 live)

### 2.4 What external review caught

Three reviewers went at this independently. Findings that changed the code:

1. **Insolvent funds vanished from the cascade.** `E < 0` ⟹ `A/E < 0` ⟹ `L > L_max`
   false, so the most distressed fund stopped breaching and stopped selling.
   Damage was non-monotone — AMZN −53% gave 5 breaches, −54% gave 4, on the real
   books at default sliders, in 30 of 32 (leverage, γ) combinations. Fixed:
   insolvency is +inf leverage, full liquidation, marked defaulted. Breach count
   is now monotone **at the demo settings** — checked in
   `tests/test_breach_count_is_monotone_on_the_real_books` over all 10 assets ×
   0–60% at λ=5.0, γ=0.2. It is **not** monotone everywhere: at λ=3.0, γ=0.5,
   MSFT −32% gives 5 breaches and −33% gives 4, with no fund insolvent. That
   residual is a VWAP/round-ordering effect, not the insolvency hole. Do not
   claim global monotonicity. (Final *loss* is separately non-monotone by
   design — see `test_loss_is_not_claimed_to_be_monotone`, ~6% of steps across
   12,200 runs, worst dip 16%.)
2. **Sales settled at book prices**, so a fund liquidating its whole book took
   *zero* fire-sale loss — the funds causing the crash were the only ones immune.
   Now settles at round VWAP.
3. **GOOGL CUSIP was Class C**; Class A was dropped. Heterogeneous undercount
   (48% Citadel, 15% Millennium, 100% Point72) which reweighted every other
   column per fund. The CUSIP map is many-to-one now.
4. **`13F-HR` never matched `13F-HR/A`**, so a Citadel RESTATEMENT of Q2-2026 was
   ignored and we read superseded data. Now follows Form 13F FAQ 58.
5. **The search asserted zero shock was safe** rather than testing it, so a
   configuration already in breach bisected to −0.0003% and reported it.
6. **One firm, two registrants.** Two Sigma files under two CIKs for the same
   quarter and we were reading only Investments (1179392), dropping Advisers
   (1478735). A manager now maps to a list of CIKs and the books are summed.
   The total book moved $38.4B → $40.9B.
7. **Citation correction.** Caccioli et al. (2014) has *no* partial deleveraging
   — portfolios are fixed until default, then fully liquidated — and uses
   exponential impact. **Greenwood, Landier & Thesmar (2015), JFE 115(3) 471–485**
   is the actual ancestor of our deleveraging rule; their `b_n = d/e` gives
   `q = (λ−1)·loss`, identical to ours. Cite Caccioli for overlapping-portfolio
   contagion and the critical-leverage boundary only.

**Why this matters:** the original plan's fallback for a weak cascade was "create synthetic portfolios
designed to demonstrate the mechanism." We do not need to. Real crowding at 0.70 mean overlap is more
than enough to propagate, and Point72's low overlap gives us a naturally *stable* node so the demo
shows a stable/unstable contrast rather than everything going red at once.

**This is also our headline empirical finding**, and it is defensible because anyone can reproduce it.

---

## 3. Model specification

### 3.1 State

- `N` assets, `M` funds. Prices normalised so `p_i(0) = 1`.
- `x[j,i]` — units of asset `i` held by fund `j`. Initialised from 13F dollar values (so `x = H` at t=0).
- `p_i(t)` — price of asset `i`.
- `D_j(t)` — debt of fund `j`.

Derived:

```
A_j(t) = Σ_i x[j,i](t) · p_i(t)        gross assets
E_j(t) = A_j(t) − D_j(t)               equity
L_j(t) = A_j(t) / E_j(t)               gross leverage
```

### 3.2 Initialisation

Leverage is **not** disclosed in 13F. It is a declared scenario parameter `λ_j`. Given `λ_j`:

```
D_j(0) = A_j(0) · (1 − 1/λ_j)
```

Check: `E = A − A(1 − 1/λ) = A/λ`, so `L = A/(A/λ) = λ`. ✔

### 3.3 Shock

`p_i → p_i · (1 + s_i)` with `s_i ≤ 0`. The shock vector `s` is what the reverse search optimises over.

### 3.4 Breach and forced sale

Fund `j` is breached when `L_j(t) > L_j^max`. It sells `q_j` dollars of assets and uses the proceeds
to repay debt. Because assets and debt fall by the same amount, **equity is unchanged by the sale itself**:

```
A' = A − q,  D' = D − q,  E' = A' − D' = E
L' = (A − q)/E  ⟹  set L' = L_target  ⟹  q = A − L_target·E
```

and since `E = A/L`:

```
q_j = A_j · (L_j − L_target) / L_j          [exact]
```

This is the plan's §5.4 proportional rule, derived rather than asserted. Optional aggressiveness
multiplier `κ_j ∈ (0,1]` for partial deleveraging within a round.

Liquidation is **pro rata across the book**:

```
Q[j,i] = q_j · (x[j,i]·p_i) / A_j
```

### 3.5 Market impact

```
V_i = Σ_j Q[j,i]                          total dollar selling in asset i
Δp_i / p_i = − γ_i · V_i / ADV_i          volume-normalised linear
```

`ADV_i` = average daily dollar volume (hardcoded from public data, shown in the assumptions panel).
`γ_i` = impact coefficient, **a slider, not a constant**. Square-root impact
(`−Y_i σ_i √(V_i/ADV_i)`) is a stretch alternative, not MVP.

### 3.6 Cascade loop

```
apply shock
repeat (max 24 rounds):
    recompute A, E, L for all funds
    breached = { j : L_j > L_j^max }
    if breached empty: break
    compute q_j, Q[j,i] for breached funds
    update x (reduce holdings), D (reduce debt)
    apply market impact to p
record per-round state for animation
```

### 3.7 Metrics

> **Corrected 2026-09-12 after executing the model.** The first draft defined amplification as
> `final loss / direct loss` with *different denominators* — direct loss as a fraction of gross
> assets, final loss as a fraction of equity. Verified result: that ratio equals the leverage ratio
> exactly, even with market impact switched off (`amp/λ = 1.000` at λ = 2, 4 and 6). It measured
> leverage, not contagion. A quant judge would have said "that's just your leverage." Both terms
> must be **equity-denominated**, and the baseline must be the shock *before* any forced selling.

| Metric | Definition |
|---|---|
| Gross shock | `Σ_j Σ_i x[j,i](0)·\|s_i\| / Σ_j A_j(0)` — asset-level, for reference only |
| Shock loss | `(Σ E_j(0) − Σ E_j^{shock}) / Σ E_j(0)` — equity loss from the shock **before** deleveraging |
| Final loss | `(Σ E_j(0) − Σ E_j(T)) / Σ E_j(0)` — equity loss after the cascade |
| **Amplification** | **final loss / shock loss** — must equal **exactly 1.0** when `γ = 0` |
| Breaches | count of distinct funds that breached at any round |
| Rounds | rounds until stabilisation |
| **Critical shock distance** | `min ‖s‖` such that the failure condition is met — **the hero number** |

GLT report an "aggregate vulnerability" instead — spillover loss as a *share of
total equity*, excluding the direct shock. The two map as `amp − 1 = AV / shock
loss`. Worth reporting AV alongside; a quant judge may ask for it by name.

Verified behaviour with the corrected definition: `γ=0 → amp = 1.000000`; disjoint books → 1.04
(self-impact only, no cross-fund contagion); high overlap + λ=6 → **1.96**. Amplification rises
smoothly 1.00 → 1.75 as leverage goes 2 → 7. These are credible magnitudes; the original definition
produced 11.8×, which was an artefact.

### 3.8 Failure conditions

- ≥ K funds breach leverage (default K=3) — **built and user-selectable** (2/3/4/5 in the UI)
- system loss > X% (default 15%) — `system_loss_above` exists in `search.py`, **not exposed in the UI**
- amplification > A× (default 1.5) — `amplification_above` exists in `search.py`, **not exposed in the UI**

### 3.9 Reverse stress search

MVP is **single-asset**: for each asset `k`, find the smallest `|s_k|` crossing the failure condition;
report the minimum across `k`.

**Important:** the damage function is a *step function* (breaches are discrete). It is monotone
non-decreasing in `|s_k|` at the demo settings — a larger price decline essentially never causes
fewer breaches — so a threshold exists in practice. It is **not** provably monotone at every
(λ, γ); see §2.4. `find_weakest_shock` therefore reports the smallest crossing the grid scan
found, not a proven threshold. But pure bisection can stall on flat regions. **Use a coarse grid scan
to bracket, then bisect inside the bracket.** Robust and still fast. As built
(`search.py`): 1% steps out to `_MAX_DROP = 0.60`, then bisection to a tolerance of 5e-4.

Stretch: sparse multi-asset search minimising `‖s‖₁` (encourages few assets shocked) or `‖s‖₂`.

### 3.10 Stabilisation search

Find the minimum intervention `δ` such that the *same* shock no longer triggers failure. MVP is
one-dimensional: reduce one fund's exposure to one asset, or reduce one fund's `λ_j`. Report the
intervention **and its cost** in expected-return terms.

---

## 4. Architecture

Four units, each independently testable:

| Unit | Responsibility | Depends on |
|---|---|---|
| `ingest` | 13F → holdings matrix `H`, CUSIP→ticker, ADV table | SEC EDGAR |
| `engine` | forward cascade, metrics | `ingest` output only |
| `search` | reverse stress + stabilisation (MATLAB) | `engine` as a black box |
| `ui` | 4 scenes, network animation, phase diagram | JSON from `search`/`engine` |

**The engine must be callable as a pure function** `(H, λ, γ, s) → trajectory`. Everything else
treats it as a black box. This is what lets the optimiser and the UI be built in parallel.

**Interface contract** (freeze this early, hand it to everyone):

As shipped (`CascadeResult.as_dict()` in `engine.py`, merged with the dataset by `api.py`):

```json
{
  "tickers": ["NVDA", "..."],
  "funds": ["Citadel", "..."],
  "fund_indices": [0, 1, 2, 3, 4],
  "holdings": [[...]],
  "trajectory": [
    {"t": 0, "prices": [...], "leverage": [...], "breached": [1, 4],
     "insolvent": [false, ...], "defaulted": [], "sold": [[...]], "equity": [...]}
  ],
  "metrics": {"shock_loss": 0.0, "final_loss": 0.0, "amplification": 0.0},
  "rounds": 0, "breached": [0, 1, 3, 4], "defaulted": [], "converged": true,
  "adv": [...], "adv_units": "USD", "quarter": "06-30-2026", "source": "SEC 13F-HR"
}
```

Two things to hold onto: `breached` is a list of fund **indices**, not a boolean mask — both at the
top level (anyone who breached at any round) and per trajectory frame (who breached in that round).
And `rounds`/`breached` live at the top level, not inside `metrics`.

---

## 5. The four scenes

| Scene | Question | Output |
|---|---|---|
| **1 — Break** | "What's the smallest thing that kills us?" | `NVDA −X%`, then the cascade animates round by round |
| **2 — Boundary** | "Bad luck, or is our structure the problem?" | leverage × overlap phase diagram with "you are here" |
| **3 — Firebreak** | "What's the cheapest way out?" | a priced instruction; same shock re-run; before/after |
| **4 — Exposure** *(planned, not built)* | "What does this mean for me?" | user's CSV portfolio as an unlevered node that cannot breach but still loses |

**Scene 4 was cut and is not in the shipped app** — there is no CSV import and no bystander node;
it is a Devpost "what's next" bullet. The rest of this paragraph is the original rationale.

Scene 4 is a **thin fourth act** — ~15% of build, ~20s of video. It is the first thing cut if the
core loop is late. A retail holder is not a participant in the cascade (no leverage, no forced selling,
no market impact); they are a **bystander**. The claim is *exposure*, never prediction.

---

## 6. Build order

| # | Item | Hours | Owner |
|---|---|---:|---|
| 1 | 13F ingest → `H` (spike already works — productionise it) | 2 | Data |
| 2 | Freeze the JSON interface contract | 0.5 | All |
| 3 | Forward cascade engine + unit tests | 4 | Engine |
| 4 | Single-asset critical shock search | 2 | Optimisation |
| 5 | Network view + round animation | 4 | Frontend |
| 6 | One-variable stabilisation | 2.5 | Optimisation |
| 7 | Leverage × overlap heatmap | 2 | Frontend |
| 8 | CSV import | 1 | Data |
| 9 | Bystander exposure view | 2 | Frontend |
| 10 | Assumptions panel + citations | 1 | All |
| 11 | **Cache golden-path run** | 1 | All |
| 12 | Record video | 1.5 | All |

Stretch only if ahead: sparse multi-asset search (+2), asset systemic-importance ranking (+1),
Plaid Trial brokerage connect (+3).

**Do not build:** CVaR comparison, historical replay, robust multi-scenario defence. These are
Devpost "what's next" bullets.

---

## 7. Sanity tests (must pass before the demo)

All seven pass as of 2026-09-12 — see `spikes/verify_engine_math.py`, re-run and confirmed
(`PYTHONPATH=src python3 spikes/verify_engine_math.py` → `ALL CHECKS PASSED`). The pytest suite was
**107 tests, all passing** when this was last reconciled; it is still growing, so read the count off
`python3 -m pytest tests/ -q | tail -1` rather than quoting this line.

1. **Zero shock** → zero breaches, zero loss, zero rounds.
2. **Zero impact (γ=0)** → at most one round of breaches **and `amp == 1.0` exactly**.
   The second assertion is the one that catches the metric bug above. Do not drop it.
3. **Zero leverage (λ=1)** → no breaches at any shock size (`D=0`, so `L=1` always).
4. **No overlap** → use **genuinely disjoint books** (one fund per asset). Only the directly
   exposed fund may breach. Note it can still run 2 rounds from *self*-impact — that is correct
   and is not cross-fund contagion.
5. **High overlap + high leverage** → multi-round cascade, amplification > 1.
6. **Monotonicity** → breach count non-decreasing in shock size. Verified over 31 shock levels on
   the toy fixture and over 10 assets × 61 shock levels on the real books at λ=5.0, γ=0.2. Final
   *loss* is deliberately **not** asserted monotone — see §2.4.
7. **Three regimes reachable** → sweeping λ from 2 to 7 must produce stable (0 breaches),
   contained (1 round) and cascade (≥2 rounds) outcomes. Guards against the demo looking rigged
   in either direction.

Tests 2 and 6 protect the headline claim. Test 7 protects the demo.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| MATLAB↔backend bridge eats hours | Engine is pure Python; MATLAB does search only. If the bridge fails, fall back to `scipy` and say so — MathWorks fit weakens, project survives. |
| Demo runs slowly on stage | Cache the golden-path JSON at first green checkpoint (item 11). Demo the cache. |
| Everything breaches / nothing breaches | Calibrate `λ` and `γ` so all three regimes are reachable by slider. Tests 2, 3, 5 cover this. |
| Scope overrun | Scene 4 cut first, then heatmap, then stabilisation. Scenes 1 + cascade animation are the irreducible core. |
| Non-monotone damage breaks bisection | Grid-bracket then bisect (§3.9). Test 6. |

---

## 9. What we do not claim

State these on the assumptions panel, out loud, before a judge asks:

- We do **not** predict market moves. We compute a stability property of a declared configuration.
- Leverage is **not** in 13F. It is our parameter, visible and adjustable.
- 13F is long-only US equity, quarterly, 45-day lag, and excludes shorts and derivatives.
  Our universe is the 10 names above; options rows are filtered out.
- Price impact is unknowable. `γ` is a slider with a stated functional form. The finding is that the
  boundary *exists and moves predictably*, not any single point estimate.
- No number in the UI is presented to more precision than the model supports.

---

## 10. Open questions for the team

1. **Do we have MATLAB licences?** MathWorks usually issues hackathon licences — confirm before
   committing item 4 to MATLAB. If not, `scipy.optimize` and the MathWorks challenge is out.
2. **Frontend stack?** D3 for the network gives the most control; a canvas force layout is faster to
   get running. Decide before item 5 starts.
3. **How many funds?** Five (as validated) is good. More funds = richer network but slower search.
4. **Who owns the video?** It needs a named owner by hour 20 or it gets written at 08:40.

---

## Appendix — reproduce the finding

`spikes/13f_overlap_spike.py` and `spikes/verify_engine_math.py` (both verified working 2026-09-12) fetches five funds' latest 13F-HR,
filters options, aggregates by CUSIP, and prints the weight and overlap matrices in §2.3.
