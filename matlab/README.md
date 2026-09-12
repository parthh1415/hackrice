# Running the MATLAB solve

Five minutes, no install. Do this once and the app stops saying "Python"
and starts saying "MATLAB".

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

In MATLAB Online:

1. Upload `matlab/cascade.m`, `matlab/stabilise.m`, and `data/cache/solve_spec.json`
2. Run:

       result = stabilise('solve_spec.json', 'solve_out.json')

3. Download `solve_out.json` back into `data/cache/`

Reload the app. The engine readout now reads **MATLAB · patternsearch** with
the real evaluation count, exit flag and wall time.

## 4. Why it can't lie

`solve_out.json` is only used if its spec fingerprint matches the parameters
currently on screen. Move a slider and the offline result is ignored rather
than shown as though it were live — see `_spec_fingerprint` in
`src/firebreak/matlab_bridge.py`. A stale answer presented confidently is
worse than no answer.

## 5. If you have MATLAB installed locally

    pip install matlabengine

The bridge picks the Engine API up automatically and the file step disappears.
