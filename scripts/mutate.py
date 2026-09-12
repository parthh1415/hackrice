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
        "while hi - lo > max(_DEPTH_FLOOR, _DEPTH_RTOL * hi):",
        "while hi - lo > 0.002:"),
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

    "cusip_jpm_typo": (
        "data/universe.json",
        '"46625H10": "JPM"',
        '"46625H20": "JPM"'),
    "restatement_ignored": (
        "src/firebreak/thirteenf.py",
        'if form not in ("13F-HR", "13F-HR/A"):',
        'if form != "13F-HR":'),

    # Frontend mutations. These need the UI harnesses, not pytest — run them
    # with --ui, which drives tests/ui/provenance.js against the mutated web/
    # and the real server. All five of these once scored 47/47 green while
    # rendering a visibly wrong number on screen.
    "amp_derived": (
        "web/app.js",
        "mult(m.amplification)",
        "mult(m.final_loss / m.shock_loss)"),
    "ring_always_zero": (
        "web/app.js",
        "shock: { assetIndex: body.asset_index ?? 0,",
        "shock: { assetIndex: 0,"),
    "split_round_off_by_one": (
        "web/app.js",
        "`round ${t} of ${longest - 1}`",
        "`round ${t} of ${longest}`"),
    "solver_evals_hardcoded": (
        "web/app.js",
        "${e.evaluations || 0} evals",
        "${999} evals"),
    "solver_exit_hardcoded": (
        "web/app.js",
        '` · <span>exit</span> ${e.exit_flag}`',
        '` · <span>exit</span> 0`'),
    "engine_name_literal": (
        "web/app.js",
        "$(\"solverName\").textContent = name;",
        "$(\"solverName\").textContent = \"MATLAB · patternsearch\";"),
    "bought_resolution_literal": (
        "web/app.js",
        "(search resolves to ±${b.resolution_pct.toFixed(3)}pp)",
        "(search resolves to ±0.005pp)"),
    "bought_before_is_after": (
        "web/app.js",
        "`critical distance <b>${b.before_pct.toFixed(2)}%</b> · <b>no measurable change</b>`",
        "`critical distance <b>${b.after_pct.toFixed(2)}%</b> · <b>no measurable change</b>`"),
}

UI_MUTATIONS = {"amp_derived", "ring_always_zero", "split_round_off_by_one",
                "solver_evals_hardcoded", "bought_before_is_after",
                "solver_exit_hardcoded", "engine_name_literal",
                "bought_resolution_literal"}


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
    # Without this, a mutation whose anchor has drifted applies nothing and
    # reports a green suite — a mutation harness with the exact bug it exists
    # to find. It has fired for real.
    assert old in text, f"anchor not found for {name} in {path}; it has drifted"
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
    for name in names:
        scratch = build(name)
        if name in UI_MUTATIONS:
            # Drives the real provenance harness against the mutated web/ and
            # the live server, so every payload is genuine and any failure is
            # the DOM disagreeing with it. Needs a server on 8765.
            run = subprocess.run(["node", "provenance.js"],
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

    if green:
        print(f"\n{len(green)} mutation(s) left the suite green: {', '.join(green)}")
        print("Each is either a hole in the suite or an inert edit. Re-run with --impact to tell them apart.")
        return 1
    print(f"\nall {len(names)} mutations caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
