# mut_parse.py: three parser mutants, each must turn test_ft_parse.py red (negative controls for the port tests).
# Usage: python -I -B mut_parse.py <worktree> <outdir>; writes outdir/mut-<k>/ and runs pytest in each.
import os
import shutil
import subprocess
import sys

W, OUT = sys.argv[1], sys.argv[2]
src = os.path.join(W, "tools", "frametime")
MUTS = [
    ("dispersion floor dropped", "return max(1.0, nu * phi_hat(ks, ns) / chi2_quantile(CHI_Q, nu))",
     "return nu * phi_hat(ks, ns) / chi2_quantile(CHI_Q, nu)"),
    ("FAIL on K_ON_max", "fail = rate_lb(on_min, n_on) - rate_ub(off_max, n_off) > 0",
     "fail = rate_lb(on_max, n_on) - rate_ub(off_max, n_off) > 0"),
    ("contrast point-weighted", None, None),
    ("e_C unit without f_hat", 'unit = cp[0] * fh[g] / 1e6', 'unit = cp[0]'),
    ("planted windows counted in B2", 'return r["arm"] if r.get("plant", 0) == 0 else None', 'return r["arm"]'),
    ("VR7 sides swapped off", 'return "ON" if r.get("plant", 0) else "OFF"', 'return r["arm"]'),
    ("K_up without its half-width", "return est, hw, est + hw", "return est, hw, est"),
    ("VR5 point zero dropped", 'if r["kind"] == "p" and "span_g" in r:', 'if False:'),
    ("D_up without its largest-value floor", 'return max(m + t_q(z, j - 1) * se, max(ds)), ds, rate',
     'return m + t_q(z, j - 1) * se, ds, rate'),
    ("cal kind overwrites the line kind", '            k = "ckind"', '            k = "kind"'),
    ("zero-state voids only the failing point",
     'return set((r["game"], r["round"]) for r in recs if r["kind"] == "p" and r.get("zs", 0) != 0)',
     'return set()'),
]
t0 = open(os.path.join(src, "ft_parse.py"), encoding="utf-8", newline="").read()
bad = 0
for k, (name, a, b) in enumerate(MUTS, 1):
    d = os.path.join(OUT, "mut-%d" % k)
    os.makedirs(d, exist_ok=False)
    shutil.copy(os.path.join(src, "test_ft_parse.py"), d)
    if a is not None:
        if t0.count(a) != 1:
            sys.exit("REFUSED: mutant %d anchor matched %d times" % (k, t0.count(a)))
        t = t0.replace(a, b)
    else:
        # replace contrast_c's body with the point-weighted mean difference
        i = t0.index("def contrast_c(points):")
        j = t0.index("\ndef ", i + 10)
        t = t0[:i] + ("def contrast_c(points):\n"
                      "    on = [p['sC'] / p['n'] for p in points if p['arm'] == 'ON' and p['n']]\n"
                      "    off = [p['sC'] / p['n'] for p in points if p['arm'] == 'OFF' and p['n']]\n"
                      "    return sum(on) / len(on) - sum(off) / len(off), sum(p['n'] for p in points)\n\n") + t0[j:]
    open(os.path.join(d, "ft_parse.py"), "w", encoding="utf-8", newline="").write(t)
    r = subprocess.run([sys.executable, "-I", "-B", "-m", "pytest", "test_ft_parse.py", "-q", "-p", "no:cacheprovider"],
                       cwd=d, capture_output=True, text=True, timeout=300)
    last = [ln for ln in r.stdout.splitlines() if ln.strip()][-1]
    red = r.returncode != 0
    print("mutant %d (%s): rc=%d %s -> %s" % (k, name, r.returncode, last, "RED" if red else "GREEN (control FAILED)"))
    bad += 0 if red else 1
print("PARSER MUTANTS %s" % ("PASS" if bad == 0 else "FAIL"))
sys.exit(0 if bad == 0 else 1)
