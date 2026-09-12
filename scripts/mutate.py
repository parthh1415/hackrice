#!/usr/bin/env python3
"""Break the code on purpose and see whether the suite notices.

A green suite tells you nothing until you have watched it go red. This ran
once as a throwaway and found eight corruptions of production code that all
left 151 tests passing — four of which changed a number on screen, and the
worst of which (reverting the position-pruning fix) returned a fix 303x too
expensive at reachable settings while every test stayed green.

    PYTHONPATH=src python3 scripts/mutate.py            # every mutation
    PYTHONPATH=src python3 scripts/mutate.py prune      # one, by name prefix

Each run copies the WORKING TREE into a scratch directory, applies exactly
one anchored replacement, and runs pytest there. Nothing touches the repo.

A mutation that stays GREEN is a hole in the suite — but only if it changes
an answer. Use --impact to print the demo-path payload from the mutant so
you can tell "nothing covers this" from "this edit is inert". Two of the
original eight were inert at the demo point and only bared their teeth off
it, which is the whole reason the flag exists.

The natural cadence: after any commit that changes a number, add a mutation
that reverts exactly that change, and confirm it goes red.
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Everything a test might read. The first version of this copied four paths
# and every mutation reported the same two failures from tests that read
# README.md — a fake red, masking the real signal.
COPY = ["src", "tests", "data", "web", "matlab", "docs", "scripts",
        "pytest.ini", "README.md"]

# name -> (path, exact text to find, what to put there)
MUTATIONS = {
    "prune_unsound": (
        "src/firebreak/stabilise.py",
        "floor_cost = position * (step - 1) / _STEPS / total",
        "floor_cost = position * step / _STEPS / total"),
    "depth_absolute": (
        "src/firebreak/stabilise.py",
        "while hi - lo > max(floor, _DEPTH_RTOL * hi):",
        "while hi - lo > 0.002:"),
    # the floor taking over from the relative bound: 1e-7 as a fraction of a
    # position is what silently overstated the cut by 5.1% at settings the
    # sliders ship with.
    "depth_floor_is_a_fraction_again": (
        "src/firebreak/stabilise.py",
        "                floor = _DEPTH_FLOOR_USD / position if position > 0 else _DEPTH_RTOL",
        "                floor = 1e-7"),
    "report_grid_point": (
        "src/firebreak/stabilise.py",
        "candidate = Fix(fund, asset, hi, position * hi / total)",
        "candidate = Fix(fund, asset, reduction, position * reduction / total)"),
    "vwap_to_book": (
        "src/firebreak/engine.py",
        "execution = (before + after) / 2.0  # round VWAP",
        "execution = before"),
    "insolvent_false": (
        "src/firebreak/engine.py",
        '"insolvent": [bool(np.isinf(x)) for x in lev]',
        '"insolvent": [False for x in lev]'),
    "measurable_never": (
        "src/firebreak/api.py",
        "measurable = delta is not None and abs(delta) > resolution",
        "measurable = False"),
    "measurable_always": (
        "src/firebreak/api.py",
        "measurable = delta is not None and abs(delta) > resolution",
        "measurable = delta is not None"),
    "resolution_halved": (
        "src/firebreak/api.py",
        "resolution = 2.0 * _SEARCH_TOLERANCE * 100.0",
        "resolution = _SEARCH_TOLERANCE * 100.0"),
    "search_tol_loose": (
        "src/firebreak/search.py",
        "DEFAULT_TOLERANCE = 0.00005",
        "DEFAULT_TOLERANCE = 0.0005"),
    "sell_usd_wrong": (
        "src/firebreak/api.py",
        'sell_usd=float(scenario["holdings"][fix.fund, fix.asset] * fix.reduction)',
        'sell_usd=float(scenario["holdings"][fix.fund, fix.asset] * fix.reduction * 1.01)'),
    "gross_usd_wrong": (
        "src/firebreak/api.py",
        'gross_usd=float(scenario["holdings"].sum())',
        'gross_usd=float(scenario["holdings"].sum() * 1.02)'),

    # Ingest mutations. The layer every number on screen is derived from, so a
    # bug here is wrong in a way no engine test can see. A review agent found
    # all three of these holes; each left 198 tests green while moving the
    # demo-path answer.
    "cusip_googl_class_a_dropped": (
        "data/universe.json",
        '"02079K10": "GOOGL",',
        '"02079K10": "GOOG_C",'),
    "cusip_prefix_truncated": (
        "data/universe.json",
        '"02079K30": "GOOGL",',
        '"02079K3": "GOOGL",'),
    "adv_units_thousands": (
        "src/firebreak/dataset.py",
        "_MILLION = 1_000_000.0",
        "_MILLION = 1_000.0"),

    "ds_missing_manager_ok": (
        "src/firebreak/dataset.py",
        "    if missing:\n        raise RuntimeError(",
        "    if False:\n        raise RuntimeError("),
    "ds_mixed_periods_ok": (
        "src/firebreak/dataset.py",
        "    if len(distinct) > 1:",
        "    if False:"),
    "near_enough_wide": (
        "src/firebreak/api.py",
        "_NEAR_ENOUGH = 0.25 ** 2",
        "_NEAR_ENOUGH = 16.0"),
    "near_enough_110": (
        "src/firebreak/api.py",
        "_NEAR_ENOUGH = 0.25 ** 2",
        "_NEAR_ENOUGH = 110.0"),
    "cusip_jpm_typo": (
        "data/universe.json",
        '"46625H10": "JPM"',
        '"46625H20": "JPM"'),
    "restatement_ignored": (
        "src/firebreak/thirteenf.py",
        'if form not in ("13F-HR", "13F-HR/A"):',
        'if form != "13F-HR":'),

    # Portfolio Mode. Every number the new product puts on screen, with a
    # mutation that changes it — because a test that has never been red is a
    # test nobody has checked.
    "pm_observer_ignores_weights": (
        "src/firebreak/portfolio.py",
        "    return float(1.0 - (float(np.dot(vector, prices)) + cash))",
        "    return float(1.0 - (float(np.dot(vector, prices)) * 1.05 + cash))"),
    "pm_predicate_is_strict": (
        "src/firebreak/portfolio.py",
        "    return lambda result: portfolio_loss(vector, cash, result.prices) >= limit",
        "    return lambda result: portfolio_loss(vector, cash, result.prices) > limit * 1.5"),
    "pm_fix_has_no_margin": (
        "src/firebreak/portfolio.py",
        "    target = limit * (1.0 - margin)",
        "    target = limit"),
    "pm_cut_loses_the_money": (
        "src/firebreak/portfolio.py",
        "    return out, cash + moved",
        "    return out, cash"),
    "pm_validation_uses_two_cascades": (
        "src/firebreak/validate.py",
        '    after_loss = portfolio_loss(after["vector"], after["cash"], result.prices)',
        '    after_loss = portfolio_loss(after["vector"], after["cash"], result.prices) * 0.5'),
    "pm_synthetic_draws_differ": (
        "src/firebreak/validate.py",
        "    rng = np.random.default_rng(seed)",
        "    rng = np.random.default_rng()"),
    "pm_historical_invents_a_number": (
        "src/firebreak/validate.py",
        '        "available": False,',
        '        "available": True, "worst_loss": 0.182,'),

    "pm_fix_dollars_inflated": (
        "src/firebreak/api.py",
        '"dollars": fix["weight_moved"] * total,',
        '"dollars": fix["weight_moved"] * total * 1.35,'),
    "pm_direct_is_scaled_cascade": (
        "src/firebreak/api.py",
        "    direct = portfolio_loss(vector, cash, 1.0 + found.shock)",
        "    direct = portfolio_loss(vector, cash, result.prices) * 0.5"),
    "pm_newbreak_derived": (
        "src/firebreak/validate.py",
        '    now = find_portfolio_firebreak(after["vector"], after["cash"], limit,\n                                   holdings=holdings, **cascade_kwargs)',
        '    now = find_portfolio_firebreak(before["vector"], before["cash"], limit,\n                                   holdings=holdings, **cascade_kwargs)'),
    "pm_after_scored_with_before": (
        "src/firebreak/validate.py",
        '        after_losses.append(portfolio_loss(after["vector"], after["cash"], result.prices))',
        '        after_losses.append(portfolio_loss(before["vector"], before["cash"], result.prices))'),
    "pm_p95_is_p50": (
        "src/firebreak/validate.py",
        '        "p95_loss": float(np.percentile(a, 95)),',
        '        "p95_loss": float(np.percentile(a, 50)),'),
    "pm_worst_is_mean": (
        "src/firebreak/validate.py",
        '        "worst_loss": float(a.max()),',
        '        "worst_loss": float(a.mean()),'),
    "pm_empty_upload_is_demo": (
        "src/firebreak/api.py",
        '    if "holdings" not in body or body["holdings"] is None:',
        "    if not body.get('holdings'):"),

    "pm_fix_first_feasible": (
        "src/firebreak/portfolio.py",
        "        if best is None or moved < best[0]:",
        "        if best is None:"),

    "pm_unknown_symbol_dropped": (
        "src/firebreak/portfolio.py",
        "    if unknown:\n        raise UnknownSymbol(unknown, tickers)",
        "    if False:\n        raise UnknownSymbol(unknown, tickers)"),
    # The anchor here used to be bare "    if total <= 0:", which str.replace
    # matched inside the eight-space copy of that line in Portfolio.weights()
    # — so for its whole life this mutation removed a different guard from the
    # one it is named after, found nothing, and reported GREEN as if the
    # weight_vector check were untested. Anchor on the line above it.
    "pm_zero_value_scored": (
        "src/firebreak/portfolio.py",
        "    total = portfolio.total_value\n    if total <= 0:",
        "    total = portfolio.total_value\n    if False:"),
    "pm_zero_weights_divide": (
        "src/firebreak/portfolio.py",
        "        total = self.total_value\n        if total <= 0:\n            return {}",
        "        total = self.total_value\n        if False:\n            return {}"),
    # NB: the first version of this commented out a line that had a
    # continuation on the next one, so the mutant did not parse and every
    # mutation "caught" it with 12 collection errors. A mutation that breaks
    # the build proves nothing about the suite.
    "pm_limit_clamped_silently": (
        "src/firebreak/api.py",
        "    used = min(max(value, lo), hi)\n    if used != value:",
        "    used = min(max(value, lo), hi)\n    if False:"),
    "pm_settles_at_the_close": (
        "src/firebreak/engine.py",
        "        execution = (before + after) / 2.0  # round VWAP",
        "        execution = after  # round VWAP"),
    "pm_deleverages_too_far": (
        "src/firebreak/engine.py",
        "            raise_ = float(np.clip(assets[j] - target_leverage[j] * equity[j], 0.0, assets[j]))",
        "            raise_ = float(np.clip(assets[j] - target_leverage[j] * equity[j] * 1.1, 0.0, assets[j]))"),
    "pm_hero_pct_inflated": (
        "src/firebreak/search.py",
        "        return abs(self.magnitude) * 100.0",
        "        return abs(self.magnitude) * 100.0 * 1.2"),
    "pm_moved_ratio_inverted": (
        "src/firebreak/validate.py",
        'out["moved_ratio"] = now.pct / was.pct if was.pct else None',
        'out["moved_ratio"] = was.pct / now.pct if now.pct else None'),
    "pm_shock_range_is_a_literal": (
        "src/firebreak/validate.py",
        '        "shock_range_pct": [lo * 100.0, hi * 100.0],',
        '        "shock_range_pct": [1.0, 30.0],'),
    "pm_demo_serves_a_neighbours_answer": (
        "src/firebreak/api.py",
        '        if cached is not None and cached["cached_exact"]:',
        '        if cached is not None and cached["cached_near"]:'),
    # The whole parse, reverted to the state the bug was in. Mutating either
    # guard alone is inert — the finite check and OverflowError in the except
    # each cover the other — so a mutation of one proves nothing about whether
    # the other exists. Defence in depth is good; a mutation that cannot see it
    # is not. (A "pm_overflow_is_not_a_valueerror" entry lived here briefly and
    # reported GREEN for exactly that reason; a permanently-green mutation is
    # noise in every future run, so it is gone rather than annotated.)
    "pm_inf_breaches_escapes_the_guard": (
        "src/firebreak/api.py",
        """            value = float(raw)
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("not a finite number")
            wanted = int(value)
            # int() truncates. breaches=2.999999999 became 2 and said nothing,
            # which is where a slider readout carrying float error lands —
            # and 2 vs 3 is 4.598% vs 5.273% on screen.
            if wanted != value:
                clamped.append({"name": "breaches", "given": value, "used": wanted,
                                "reason": "whole funds only"})
        except (TypeError, ValueError, OverflowError):""",
        """            wanted = int(float(raw))
        except (TypeError, ValueError):"""),
    "pm_magnitude_unbounded": (
        "src/firebreak/api.py",
        "    used = min(abs(wanted), 1.0)",
        "    used = abs(wanted)"),
    "pm_refusal_looks_like_a_null_result": (
        "src/firebreak/api.py",
        '            "found": False,\n            "refused": True,',
        '            "found": False,\n            "refused": False,'),

    # Frontend mutations. These need the UI harness, not pytest — run them with
    # --ui, which drives tests/ui/pages.js against the mutated web/ and the real
    # server.
    #
    # There used to be eight of these, all anchored in web/app.js. When the
    # single-page app became six pages nothing loaded app.js any more, so all
    # eight went on scoring CAUGHT against a file no user could reach — the
    # suite reporting frontend coverage it did not have. Five of them described
    # UI that the redesign dropped outright (the MATLAB solver's evaluation
    # count, its exit flag, the engine name, the bought-side resolution). Those
    # are gone rather than moved; a mutation cannot guard a screen that no
    # longer exists.
    # The obvious mutation here — deriving amplification on screen instead of
    # reading the engine's field — is INERT: server-side `amplification` is
    # defined as cascade_loss / direct_loss, so the page prints the same digits
    # either way. This one is the real hazard: the after-cascade loss presented
    # as the direct loss, which understates nothing and overstates the shock.
    "direct_loss_is_really_the_cascade": (
        "web/analysis.html",
        '["Direct loss", pct(body.direct_loss), "the shock alone", ""],',
        '["Direct loss", pct(body.cascade_loss), "the shock alone", ""],'),
    "weight_as_fraction": (
        "web/index.html",
        "${pct(h.weight, 1)}",
        "${h.weight.toFixed(1)}%"),
    "negative_zero_returns": (
        "web/cascade.html",
        'val.textContent = hot ? `−${(drop * 100).toFixed(2)}%` : "";',
        'val.textContent = `−${(drop * 100).toFixed(2)}%`;'),
    "state_narrated_as_transition": (
        "web/cascade.html",
        "    const prev = new Set(t > 1 ? (frames[t - 1].breached || []) : []);",
        "    const prev = new Set();"),
    "model_link_locked": (
        "web/shared.js",
        "                assumptions: true };",
        "                assumptions: undefined };"),
    "stale_result_survives_a_new_book": (
        "web/index.html",
        "  invalidateStaleResult();\n  document.getElementById(\"pfCard\").hidden = false;",
        "  document.getElementById(\"pfCard\").hidden = false;"),
    "unbreakable_renders_nothing": (
        "web/verify.html",
        "  const safe = !!n.after_unbreakable || n.after_pct === null || n.after_pct === undefined;",
        "  const safe = false;"),
    "proceeds_vanish_without_a_cash_row": (
        "web/defend.html",
        '              if (!rows.some(h => h.symbol === "CASH")) rows.push({ symbol: "CASH", market_value: 0 });',
        '              if (false) rows.push({ symbol: "CASH", market_value: 0 });'),
    "stepping_does_not_stop_the_timer": (
        "web/cascade.html",
        '  document.getElementById("prevBtn").onclick = () => step(at - 1);\n  document.getElementById("nextBtn").onclick = () => step(at + 1);',
        '  document.getElementById("prevBtn").onclick = () => { at = Math.max(0, at - 1); draw(at); };\n  document.getElementById("nextBtn").onclick = () => { at = Math.min(frames.length - 1, at + 1); draw(at); };'),
    "one_frame_cascade_pretends_to_play": (
        "web/cascade.html",
        "    if (frames.length <= 1) { playBtn.textContent = \"Replay\"; return; }",
        "    if (false) { playBtn.textContent = \"Replay\"; return; }"),
    "attribution_uses_direct_not_cascade": (
        "web/analysis.html",
        "      const costs = weight * total;",
        "      const costs = weight * direct;"),
    "contagion_column_is_the_whole_fall": (
        "web/analysis.html",
        "      const contagion = total - direct;",
        "      const contagion = total;"),
    # the original bug: edges drawn from static positions, identical every frame
    "flow_is_static_positions": (
        "web/cascade.html",
        "    (f.sold || []).forEach((row, j) => row.forEach((usd, i) => {",
        "    (body.holdings || []).forEach((row, j) => row.forEach((usd, i) => {"),
    "flow_scaled_per_frame": (
        "web/cascade.html",
        "      const share = usd / maxSold;",
        "      const share = usd / Math.max(1, ...(f.sold || []).flat());"),
    "crowding_is_dollars_not_days": (
        "web/index.html",
        "      if (d.adv[i] > 0) days[t] = held / d.adv[i];",
        "      if (d.adv[i] > 0) days[t] = held / 1e9;"),
    "next_skips_a_round": (
        "web/cascade.html",
        'document.getElementById("nextBtn").onclick = () => step(at + 1);',
        'document.getElementById("nextBtn").onclick = () => step(at + 2);'),
    "loss_tile_is_the_final_loss": (
        "web/cascade.html",
        '      ["Your loss so far", pct(cum), cum >= (r.params.limit) ? "bad" : ""],',
        '      ["Your loss so far", pct(r.cascade_loss), cum >= (r.params.limit) ? "bad" : ""],'),
    "value_column_matched_loosely": (
        "web/index.html",
        '  const at = (names) => head.findIndex(h => names.includes(h));',
        '  const at = (names) => head.findIndex(h => names.some(n => h.includes(n)));'),
    "ragged_row_accepted": (
        "web/index.html",
        "    if (c.length !== head.length) {",
        "    if (false) {"),
    "value_and_qty_price_not_reconciled": (
        "web/index.html",
        "      if (Math.abs(implied - v) > Math.max(1, 0.01 * Math.abs(v))) {",
        "      if (false) {"),
    "negative_holding_accepted": (
        "web/index.html",
        "    if (v !== null && v < 0) {",
        "    if (false) {"),
    "pct_forgets_the_hundred": (
        "web/shared.js",
        "const pct = (x, dp = 2) => `${(x * 100).toFixed(dp)}%`;",
        "const pct = (x, dp = 2) => `${x.toFixed(dp)}%`;"),
    "cold_page_renders_anyway": (
        "web/shared.js",
        "  if (!s.result || !s.result.found) {",
        "  if (false) {"),
}

UI_MUTATIONS = {"direct_loss_is_really_the_cascade", "weight_as_fraction", "negative_zero_returns",
                "pct_forgets_the_hundred", "cold_page_renders_anyway",
                "state_narrated_as_transition", "model_link_locked",
                "stale_result_survives_a_new_book", "unbreakable_renders_nothing",
                "proceeds_vanish_without_a_cash_row", "next_skips_a_round",
                "loss_tile_is_the_final_loss", "value_column_matched_loosely",
                "ragged_row_accepted", "value_and_qty_price_not_reconciled",
                "negative_holding_accepted", "stepping_does_not_stop_the_timer",
                "one_frame_cascade_pretends_to_play",
                "attribution_uses_direct_not_cascade",
                "contagion_column_is_the_whole_fall", "flow_is_static_positions",
                "flow_scaled_per_frame", "crowding_is_dollars_not_days"}


def build(name):
    path, old, new = MUTATIONS[name]
    scratch = pathlib.Path(tempfile.mkdtemp(prefix=f"mutate-{name}-"))
    for item in COPY:
        src = ROOT / item
        if not src.exists():
            continue
        dst = scratch / item
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
        else:
            shutil.copy2(src, dst)

    # jsdom is large and identical in every copy; link rather than duplicate it.
    mods = ROOT / "tests" / "ui" / "node_modules"
    link = scratch / "tests" / "ui" / "node_modules"
    if mods.exists() and not link.exists():
        link.symlink_to(mods, target_is_directory=True)

    target = scratch / path
    text = target.read_text()
    # A mutation whose anchor has drifted applies nothing and reports a green
    # suite — a mutation harness with the exact bug it exists to find. It has
    # fired for real, more than once.
    #
    # It used to raise here, which is loud but total: one stale anchor aborted
    # the run and took the other seventy mutations' results with it, so a
    # refactor that moved one line left the whole suite unmeasured until
    # somebody noticed the traceback. Drift is now a reported FAILURE for that
    # mutation and the run continues.
    if old not in text:
        shutil.rmtree(scratch, ignore_errors=True)
        return None
    target.write_text(text.replace(old, new, 1))
    return scratch


def demo_payload(scratch):
    """The demo-path numbers, so an inert edit is distinguishable from a gap."""
    code = (
        "import json;from firebreak import api;"
        "b=api.handle('/api/break?leverage=5&gamma=0.2&breaches=3',{});"
        "s=api.handle('/api/stabilise?leverage=5&gamma=0.2&breaches=3',{});"
        "print(json.dumps({'pct':b['pct'],'metrics':b['metrics'],'rounds':b['rounds'],"
        "'breached':b['breached'],'fix':s['fix'],'bought':s['bought']},sort_keys=True))")
    out = subprocess.run([sys.executable, "-c", code], cwd=scratch, text=True,
                         capture_output=True, env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"})
    return (out.stdout or out.stderr).strip()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    impact = "--impact" in sys.argv
    names = [n for n in MUTATIONS if not args or any(n.startswith(a) for a in args)]
    if not names:
        print(f"no mutation matches {args}; known: {', '.join(sorted(MUTATIONS))}")
        return 2

    base = demo_payload(ROOT) if impact else None
    green = []
    drifted = []
    for name in names:
        scratch = build(name)
        if scratch is None:
            drifted.append(name)
            path = MUTATIONS[name][0]
            print(f"DRIFTED {name:<20} anchor no longer in {path}")
            continue
        if name in UI_MUTATIONS:
            # Drives the real page harness against the mutated web/ and
            # the live server, so every payload is genuine and any failure is
            # the DOM disagreeing with it. Needs a server on 8765.
            run = subprocess.run(["node", "pages.js"],
                                 cwd=scratch / "tests" / "ui", text=True, capture_output=True,
                                 env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"})
            tail = [l for l in run.stdout.splitlines() if "[FAIL]" in l]
            summary = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else "no output"
            caught = run.returncode != 0
        else:
            run = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "--no-header",
                                  "-p", "no:cacheprovider"],
                                 cwd=scratch, text=True, capture_output=True,
                                 env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"})
            tail = [l for l in run.stdout.splitlines() if l.startswith("FAILED")]
            summary = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else "no output"
            caught = run.returncode != 0
        print(f"{'CAUGHT ' if caught else 'GREEN  '} {name:<20} {summary}")
        for line in tail[:3]:
            print(f"           {line}")
        if not caught:
            green.append(name)
            if impact:
                after = demo_payload(scratch)
                print(f"           demo path {'UNCHANGED — edit may be inert' if after == base else 'MOVED — a real gap'}")
        shutil.rmtree(scratch, ignore_errors=True)

    if drifted:
        print(f"\n{len(drifted)} mutation(s) could not be applied — the code moved under "
              f"them: {', '.join(drifted)}")
        print("These measured NOTHING. Re-anchor them before trusting this run.")
    if green:
        print(f"\n{len(green)} mutation(s) left the suite green: {', '.join(green)}")
        print("Each is either a hole in the suite or an inert edit. Re-run with --impact to tell them apart.")
    if drifted or green:
        return 1
    print(f"\nall {len(names)} mutations caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
