# Running the MATLAB solve

Five minutes, no install. Until you do this, the solver strip reads
**"SciPy-free Python · exhaustive position scan"** with a note saying MATLAB is
not available on this machine. Do this once and it reads
**"MATLAB · patternsearch"** instead.

## 1. Get MATLAB (free, you already have it)

Rice has a campus-wide licence. Go to **mathworks.com**, create an account
with your **@rice.edu** address, and it associates automatically. Then open
**MATLAB Online** — it runs in the browser, nothing to install.

<https://www.mathworks.com/products/matlab-online.html>

If the association doesn't work, MathWorks runs hackathon access directly:
<hackathon@mathworks.com>.

## 2. What MATLAB is actually doing here

Only the stabilisation solve. That is deliberate, and it's the honest answer
if a judge asks "why MATLAB?":

> The objective is a simulation. It can't be differentiated, the feasible set
> is "does a cascade cross a discrete failure threshold", and breach events
> make the landscape piecewise constant. That's the problem class
> `patternsearch` exists for. The forward cascade is linear algebra and stays
> in Python where it has a test suite.

`cascade.m` mirrors `src/firebreak/engine.py` so the optimiser has an
objective to evaluate. `stabilise.m` is the solve.

It is not decoration. The Python fallback walks the reduction up a 5% grid
(`_STEPS = 20` in `stabilise.py`), so the smallest cut it can ever propose is
5% of a position. `patternsearch` treats the reduction as continuous and
routinely lands two or three orders of magnitude below that — on the checked-in
spec it finds a fix costing **1.4e-06** of gross assets against the Python
scan's **4.4e-04**. Same failure condition, same engine, same answer to
"which position"; MATLAB just gets to say *how little* far more precisely.

## 3. Run it

The app writes a spec every time you press **Stabilise**:

    data/cache/solve_spec.json

(written by `write_spec` on every `/api/stabilise` call — `api.py:345`.)

In MATLAB Online:

1. Upload `matlab/cascade.m`, `matlab/stabilise.m`, and `data/cache/solve_spec.json`
2. Run:

       result = stabilise('solve_spec.json', 'solve_out.json')

3. Download `solve_out.json` back into `data/cache/`

Reload the app. The engine readout now reads **MATLAB · patternsearch** with
the real evaluation count, exit flag and wall time. (`engine_label` and
`solve_stabilisation` in `src/firebreak/matlab_bridge.py` pick between three
paths — `matlab`, `matlab-offline`, `python` — and the UI is told which one
actually ran.)

## 4. Why it can't lie

The breach band reaches MATLAB baked into `spec.max_leverage` (which is
`leverage * band`), so `cascade.m` needs no extra argument and moving the band
changes the fingerprint like any other knob.

`solve_out.json` is only used if it still answers the question on screen.
Three guards, in order:

1. **Fingerprint.** `stabilise.m` echoes the spec's `fingerprint` into its
   result. The bridge compares it to the live request and refuses a mismatch.
2. **Freshness.** If a result carries no fingerprint (an older run), the bridge
   falls back to mtime: `solve_spec.json` is only rewritten when the question
   actually changes, so a `solve_out.json` older than it is stale by
   construction and is refused.
3. **Re-simulation.** `_usable` in the bridge re-runs the proposed fix through
   the *Python* engine and throws it away unless the patched system really does
   stay under the breach count. This is the one that matters most: both solvers
   can exit on an infeasible point and still hand back an `x`, and the offline
   path is a file a human downloaded and dropped in a folder. A fix that
   MATLAB believes in but Python cannot reproduce never reaches the screen.

Any of the three failing falls through to Python rather than being served. A
stale answer presented confidently is worse than no answer.

`stabilise.m` checks feasibility itself before reporting, so a correct MATLAB
answer passes guard 3 rather than being caught by it.

## 5. Two things about the solve that are not obvious

**It starts from a grid, not from one point.** `patternsearch` halves its mesh
on a failed poll, and `stabilise.m` rounds `x(1)`/`x(2)` into fund and asset
indices — so once the mesh drops below 0.5 those two coordinates are frozen and
the discrete half of the search is over while the mesh is still coarse. From a
single `x0 = [1 1 0.25]`, a problem whose answer sits away from fund 1 / asset 1
came back **14.7x more expensive than the optimum**. `startGrid` spreads three
starts per dimension and keeps the cheapest feasible result; the extra polls
cost a few thousand cascades, which on a book this size is milliseconds.

**`MeshTolerance` is 1e-6, not the more usual 1e-3.** The reduction is the one
coordinate genuinely worth refining, and at 1e-3 the search stops about a factor
of 2.7 short of the cheapest fix.

Toolboxes: `patternsearch` is Global Optimization Toolbox, `fmincon` is
Optimization Toolbox. Neither is base MATLAB, so the `fmincon` path is a
fallback for "no Global Optimization Toolbox", not for "no toolboxes at all" —
which is fine, because Global Optimization Toolbox requires Optimization
Toolbox anyway. With neither present, `stabilise.m` says so and stops.

## 6. If you have MATLAB installed locally

    pip install matlabengine

The bridge picks the Engine API up automatically and the file step disappears.
