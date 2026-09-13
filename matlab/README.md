# Running the MATLAB solve

Five minutes, no install. Until you do this, the Model page's "What computed the
institutional patch" card reads
**"SciPy-free Python · exhaustive position scan"** with a note saying MATLAB is
not available on this machine. Do this once and it reads
**"MATLAB · patternsearch"** instead.

## 1. Get MATLAB (free, you already have it)

Rice has a Total Academic Headcount licence. Two links, in this order:

1. **Rice's MATLAB portal** — sign in with your NetID@rice.edu:
   <https://www.mathworks.com/academia/tah-portal/rice-university-40580441.html>
2. **MATLAB Online**, which runs in the browser with nothing installed:
   <https://matlab.mathworks.com/>

(The marketing page this used to point at, `/products/matlab-online.html`, is
not a reliable entry point — go straight to `matlab.mathworks.com`.)

If the association doesn't work, MathWorks runs hackathon access directly:
<hackathon@mathworks.com>.

### Check which toolboxes you actually got

`patternsearch` is **Global Optimization Toolbox**. `fmincon` is
**Optimization Toolbox**. Rice's published TAH bundle lists Optimization
Toolbox and **does not list Global Optimization Toolbox**, so the likely
outcome is that `fmincon` runs and the card reads **MATLAB · fmincon**, not
`MATLAB · patternsearch`.

In MATLAB, before anything else:

    ver                              % everything you are licensed for
    exist('patternsearch', 'file')   % non-zero if you have GOT
    exist('fmincon', 'file')         % non-zero if you have Optimization Toolbox

`stabilise.m` handles either and reports which one ran — the readout is built
from the result, never from an assumption, so it cannot claim patternsearch
when fmincon did the work.

**But say the right thing on camera.** The argument for MATLAB here is that
the objective is a simulation: non-differentiable, piecewise constant across
breach events. That is the case for a *direct search* method, and it is an
argument `fmincon` does not get to make — a gradient method on a piecewise
constant landscape is exactly the mismatch `patternsearch` exists to avoid.
So:

* **With Global Optimization Toolbox** the pitch is the one in the next
  section, unchanged.
* **With only `fmincon`** the honest line is narrower: "we posed it to a
  constrained optimiser as a mixed-integer program and it landed on the same
  position our own search did" — the agreement is the result, not the method.
  Do not describe it as pattern search.

If you want the full argument, ask hackathon@mathworks.com for Global
Optimization Toolbox; hackathon licences routinely include everything.

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

`patternsearch` treats the reduction as continuous, which for most of this
project's life was the whole argument for the MATLAB path: the Python fallback
walked the reduction up a 5% grid and could not propose a cut smaller than 5%
of a position.

The Python scan now brackets on that grid and then bisects on depth against a
relative tolerance, so the gap has narrowed. On the golden-path spec
(leverage 5.0, gamma 0.20, band 1.05, breaches 3) the pure-grid search returns
a fix costing **4.4e-04** of gross assets and the current search returns
**4.2e-05** — about 10x finer. At band 1.30 the same comparison is
**1.5e-04** against **2.0e-06**, about 78x.

MATLAB's own recorded figure is **1.4e-06**. We are not going to tell you how
that compares, because we no longer know what it was measured on and this
machine has no licence to re-run it. If you have one, run it and write the
number down beside the spec it came from.

> An earlier version of this section did the comparison anyway and got it
> badly wrong. It read "1.99e-06 against 4.4e-04, within about 1.4x of MATLAB,
> from 300x" — but 4.4e-04 is the band 1.05 answer and 1.99e-06 is the band
> 1.30 answer, two different scenarios, and the ratio between them means
> nothing. It also said "the checked-in spec", and there is no checked-in
> spec: `data/cache/solve_spec.json` is untracked and the app overwrites it on
> every Stabilise press, which is how two bands got crossed in one paragraph.
> The section it corrupted was the one about a claim that had expired.

So the honest case for `stabilise.m` is not precision any more. It is that the
same problem, posed to a real optimiser as a constrained mixed-integer program
with a continuous third variable, lands on the same position our own search
does. That agreement is worth more than either number alone, and it is the
thing we can actually still verify.

## 3. Run it

The app writes a spec every time it asks the institutional question — which is
when you open the **Model** page (it is the only caller of `/api/stabilise`), or
when you hit that endpoint yourself:

    data/cache/solve_spec.json

(written by `write_spec` on every `/api/stabilise` call.)

In MATLAB Online:

1. Upload `matlab/cascade.m`, `matlab/stabilise.m`, and `data/cache/solve_spec.json`
2. Run:

       result = stabilise('solve_spec.json', 'solve_out.json')

3. Download `solve_out.json` back into `data/cache/`

Reload the app and press `8` for the Model page. The card now reads **MATLAB · patternsearch** with
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
