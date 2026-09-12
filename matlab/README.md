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

## 3. Run it

The app writes a spec every time you press **Stabilise**:

    data/cache/solve_spec.json

(written by `write_spec` on every `/api/stabilise` call — `api.py:294`.)

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

`solve_out.json` is only used if it still answers the question on screen.
Two guards, in order:

1. **Fingerprint.** `stabilise.m` echoes the spec's `fingerprint` into its
   result. The bridge compares it to the live request and refuses a mismatch.
2. **Freshness.** If a result carries no fingerprint (an older run), the bridge
   falls back to mtime: `solve_spec.json` is only rewritten when the question
   actually changes, so a `solve_out.json` older than it is stale by
   construction and is refused.

Either way a mismatch falls through to Python rather than being served. A
stale answer presented confidently is worse than no answer.

## 5. If you have MATLAB installed locally

    pip install matlabengine

The bridge picks the Engine API up automatically and the file step disappears.
