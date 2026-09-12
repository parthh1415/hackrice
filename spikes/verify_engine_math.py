"""THROWAWAY verification spike. Checks the spec's math before anyone builds on it."""
import numpy as np

def run(H, lam, lam_max, lam_tgt, gamma, adv, s, max_rounds=12, kappa=1.0):
    """H: (M,N) dollar holdings at t0. Returns trajectory dict."""
    M, N = H.shape
    p = np.ones(N)
    x = H.astype(float).copy()          # units; p0=1 so units==dollars at t0
    A0 = x.sum(1)
    D = A0 * (1 - 1/lam)
    E0 = A0 - D
    p = p * (1 + s)                      # apply shock
    E_shock = (x * p).sum(1) - D         # equity after shock, BEFORE any forced selling
    breached_ever, rounds = set(), 0
    for t in range(max_rounds):
        A = (x * p).sum(1)
        E = A - D
        L = np.divide(A, E, out=np.full(M, np.inf), where=E > 1e-12)
        br = [j for j in range(M) if E[j] > 1e-12 and L[j] > lam_max[j] + 1e-12]
        if not br:
            break
        rounds = t + 1
        breached_ever |= set(br)
        V = np.zeros(N)
        for j in br:
            q = kappa * A[j] * (L[j] - lam_tgt[j]) / L[j]
            q = min(q, A[j])
            w = (x[j] * p) / A[j]
            Q = q * w
            V += Q
            x[j] -= np.divide(Q, p, out=np.zeros(N), where=p > 1e-12)
            D[j] -= q
        p = p * np.maximum(1 - gamma * V / adv, 1e-6)
    A = (x * p).sum(1); E = A - D
    gross = float((H * np.abs(s)).sum() / H.sum())        # asset-level first-order loss
    shock_loss = float((E0.sum() - E_shock.sum()) / E0.sum())  # equity loss from shock alone
    final = float((E0.sum() - E.sum()) / E0.sum())             # equity loss after cascade
    return dict(gross=gross, shock_loss=shock_loss, final=final,
                amp=(final / shock_loss if shock_loss > 1e-12 else 1.0),
                breaches=len(breached_ever), rounds=rounds)

# ---- fixtures ----
np.random.seed(0)
OVER = np.array([[40.,30,20,10,0],[38,32,18,12,0],[35,30,25,10,0],[42,28,20,10,0]])  # high overlap
DISJ = np.array([[100.,0,0,0,0],[0,100.,0,0,0],[0,0,100.,0,0],[0,0,0,50.,50]])
ADV  = np.full(5, 500.0)

def cfg(M, lev): return (np.full(M,lev), np.full(M,lev*1.05), np.full(M,lev*0.95))

ok = True
def check(name, cond, detail=""):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    ok &= cond

print("TEST 1 — zero shock")
l,lm,lt = cfg(4,4.0)
r = run(OVER,l,lm,lt,0.3,ADV,np.zeros(5))
check("no breaches / no loss / 0 rounds", r['breaches']==0 and abs(r['final'])<1e-9 and r['rounds']==0, str(r))

print("TEST 2 — zero market impact (gamma=0)")
s = np.array([-0.12,0,0,0,0])
r = run(OVER,l,lm,lt,0.0,ADV,s)
check("cascade halts after 1 round", r['rounds']<=1, str(r))
check("amplification == 1.0 with no market impact", abs(r['amp']-1.0)<1e-9, f"amp={r['amp']:.6f}")

print("TEST 3 — zero leverage (lambda=1)")
l1,lm1,lt1 = np.full(4,1.0), np.full(4,1.0), np.full(4,1.0)
r = run(OVER,l1,lm1,lt1,0.5,ADV,np.array([-0.40,0,0,0,0]))
check("no breaches at any shock", r['breaches']==0, str(r))

print("TEST 4 — no overlap")
# shock asset 0: held by fund0 (and fund3). fund1 holds only assets 2,3 -> must not breach.
l4,lm4,lt4 = cfg(4,4.0)
r = run(DISJ,l4,lm4,lt4,0.35,ADV,np.array([-0.20,0,0,0,0]))
check("only the directly-exposed fund breaches", r['breaches']<=1, str(r))

print("TEST 5 — high overlap + high leverage")
l5,lm5,lt5 = cfg(4,6.0)
r5 = run(OVER,l5,lm5,lt5,0.6,ADV,np.array([-0.08,0,0,0,0]))
check("multi-round cascade, amplification > 1", r5['rounds']>=2 and r5['amp']>1.0, str(r5))

print("TEST 6 — monotonicity of damage in shock size")
l6,lm6,lt6 = cfg(4,5.0)
prev_f, prev_b, bad = -1e9, -1, []
for pct in range(0,31):
    r = run(OVER,l6,lm6,lt6,0.5,ADV,np.array([-pct/100,0,0,0,0]))
    if r['final'] < prev_f - 1e-9: bad.append((pct, r['final'], prev_f))
    if r['breaches'] < prev_b:     bad.append((pct,'breaches',r['breaches'],prev_b))
    prev_f, prev_b = r['final'], r['breaches']
check("final loss and breach count non-decreasing", not bad, f"{len(bad)} violations" if bad else "31 shock levels")

print("\nTEST 7 — three regimes reachable by leverage slider (gamma=0.5)")
seen=[]
for lev in [2.0,3.0,4.0,5.0,6.0,7.0]:
    a,b,c = cfg(4,lev)
    r = run(OVER,a,b,c,0.5,ADV,np.array([-0.10,0,0,0,0]))
    seen.append((lev,r['breaches'],r['rounds'],round(r['amp'],2)))
    print(f"        lev={lev:<4} breaches={r['breaches']} rounds={r['rounds']} amp={r['amp']:.2f}")
regimes = {('stable' if b==0 else 'contained' if ro<=1 else 'cascade') for _,b,ro,_ in seen}
check("stable, contained and cascade regimes all reachable", len(regimes)>=3, str(sorted(regimes)))

print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
