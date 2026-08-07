"""Diagnostics extracted from a finished episode.

Win rate is the headline number but it is one bit per 720 turns. These are the
sub-signals that tell you *why* a version regressed. Every one of them is a
lever the policy can pull.
"""

import math
from collections import defaultdict


def _tiles(farm):
    for y, row in enumerate(farm["tiles"]):
        for x, t in enumerate(row):
            yield x, y, t


def episode_metrics(steps, seat):
    """steps: env.steps (list of per-turn [agent0_state, agent1_state]).

    Returns a dict of diagnostics for one seat.
    """
    m = {
        "final_bank": 0.0,
        "actions_taken": 0,
        "noop_actions": 0,
        "moves": 0,
        "idle_tile_days": 0,
        "plants_weeded": 0,
        "animals_lost": 0,
        "fertilizer_missed": 0,
        "units_sold": defaultdict(int),
        "revenue": defaultdict(float),
        "sold_below_base": 0.0,
        "hires": 0,
        "quadrants": 1,
        "peak_units": 0,
    }

    prev_farm = None
    prev_shed = None

    for i, step in enumerate(steps):
        obs = step[0]["observation"]
        farms = obs.get("farms") or []
        if seat >= len(farms):
            continue
        farm = farms[seat]
        priv = step[seat]["observation"].get("private", {}) or {}
        action = step[seat].get("action") or {}

        # --- action accounting
        acts = []
        if isinstance(action, dict):
            f = action.get("farmer")
            if f:
                acts.append(f)
            acts.extend(action.get("hands") or [])
        m["actions_taken"] += len(acts)
        m["peak_units"] = max(m["peak_units"], len(acts))
        for a in acts:
            if not isinstance(a, list) or not a:
                m["noop_actions"] += 1
            elif a[0] == "PASS":
                m["noop_actions"] += 1
            elif a[0] in ("NORTH", "SOUTH", "EAST", "WEST"):
                m["moves"] += 1

        if isinstance(action, dict):
            for o in action.get("market") or []:
                if isinstance(o, list) and o and o[0] == "HIRE":
                    m["hires"] += 1

        # --- board state
        empty = 0
        for x, y, t in _tiles(farm):
            if t is None:
                empty += 1
            elif isinstance(t, dict) and t.get("animal") and t.get("fertilizer_available"):
                # available at observation time and still available next turn
                # is counted once per turn; approximate signal only
                pass
        m["idle_tile_days"] += empty

        # --- transitions: what died
        if prev_farm is not None:
            for x, y, t in _tiles(farm):
                p = prev_farm["tiles"][y][x]
                if isinstance(p, dict) and p.get("kind") == "PLANT":
                    if isinstance(t, dict) and t.get("kind") == "WEED":
                        m["plants_weeded"] += 1
                if isinstance(p, dict) and p.get("animal"):
                    if isinstance(t, dict) and t.get("animal") is None:
                        m["animals_lost"] += 1

        # --- sales: shed shrink coinciding with money growth
        shed = priv.get("shed", {}) or {}
        if prev_shed is not None and prev_farm is not None:
            gained = farm["money"] - prev_farm["money"]
            if gained > 0:
                for item, qty in prev_shed.items():
                    delta = qty - shed.get(item, 0)
                    if delta > 0:
                        m["units_sold"][item] += delta

        prev_farm = {"tiles": [row[:] for row in farm["tiles"]],
                     "money": farm["money"]}
        prev_shed = dict(shed)

    final = steps[-1][0]["observation"]["farms"][seat]
    m["final_bank"] = final["money"]
    m["quadrants"] = len(final.get("unlocked_quadrants", ["NW"]))
    m["units_sold"] = dict(m["units_sold"])
    m["revenue"] = dict(m["revenue"])

    acted = m["actions_taken"] or 1
    m["coins_per_action"] = m["final_bank"] / acted
    m["noop_rate"] = m["noop_actions"] / acted
    m["idle_tile_rate"] = m["idle_tile_days"] / max(1, len(steps) * 25)
    return m


HEADLINE = [
    "final_bank", "coins_per_action", "noop_rate", "idle_tile_rate",
    "plants_weeded", "animals_lost", "hires", "quadrants", "peak_units",
]


def format_summary(rows):
    """rows: list of metric dicts. Returns a printable block."""
    if not rows:
        return "(no episodes)"
    out = []
    for k in HEADLINE:
        vals = [r.get(k, 0) for r in rows]
        mean = sum(vals) / len(vals)
        out.append(f"  {k:<20} {mean:>12.3f}   (min {min(vals):.1f} max {max(vals):.1f})")
    return "\n".join(out)


# --- paired-differential statistics -----------------------------------------
#
# Win rate discards magnitude: a 1-coin win and a 2000-coin win are the same
# bit. For *development* (not the final ladder check, which is win/loss only
# by the competition's own rules) the bank differential is the lower-variance
# signal. Implemented without scipy: arena/ is dev tooling but CI
# (.github/workflows/arena.yml) only installs kaggle-environments and pytest,
# and agent/ must never gain a dependency beyond the stdlib. The t and
# Wilcoxon implementations below were cross-checked against scipy.stats
# locally during development (not a runtime dependency) - see
# docs/strategy-log.md.

def _mean(xs):
    return sum(xs) / len(xs)


def _sample_sd(xs):
    """Sample (n-1) standard deviation."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _population_sd(xs):
    n = len(xs)
    if n == 0:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / n)


def skewness(xs):
    """Fisher-Pearson standardized moment coefficient (population moments).

    A simple descriptive estimator, not bias-corrected - it's a diagnostic
    signal for "is a normal-theory test appropriate here", not a published
    statistic.
    """
    n = len(xs)
    sd = _population_sd(xs)
    if n == 0 or sd == 0:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 3 for x in xs) / n) / sd ** 3


def excess_kurtosis(xs):
    """Excess kurtosis (population moments); 0 for a normal distribution."""
    n = len(xs)
    sd = _population_sd(xs)
    if n == 0 or sd == 0:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 4 for x in xs) / n) / sd ** 4 - 3.0


def _betacf(a, b, x):
    """Continued-fraction evaluation for the incomplete beta function.
    Numerical Recipes' betacf, standard and well-tested."""
    MAXIT, EPS, FPMIN = 200, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def _betai(a, b, x):
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                   + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_sf(t, df):
    """Upper-tail (survival) probability P(T > t) for Student's t, df dof."""
    t = abs(t)
    x = df / (df + t * t)
    return 0.5 * _betai(df / 2.0, 0.5, x)


def norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def norm_quantile(p):
    """Inverse standard normal CDF (Acklam's rational approximation,
    |error| < 1.15e-9). No scipy - see module docstring."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p_low, p_high = 0.02425, 1 - 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > p_high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def paired_ttest(diffs):
    """One-sample (paired) t-test of diffs against a null mean of 0."""
    n = len(diffs)
    if n < 2:
        return {"n": n, "mean": _mean(diffs) if diffs else 0.0, "sd": 0.0,
                "se": 0.0, "t_stat": float("nan"), "df": 0, "p_value": float("nan")}
    mean = _mean(diffs)
    sd = _sample_sd(diffs)
    se = sd / math.sqrt(n)
    df = n - 1
    if se == 0:
        t_stat = 0.0 if mean == 0 else math.inf
        p = 1.0 if mean == 0 else 0.0
    else:
        t_stat = mean / se
        p = 2 * t_sf(t_stat, df)
    return {"n": n, "mean": mean, "sd": sd, "se": se, "t_stat": t_stat, "df": df, "p_value": p}


def ci95_mean(diffs):
    """95% CI for the mean via the t distribution (matches paired_ttest)."""
    n = len(diffs)
    if n < 2:
        m = _mean(diffs) if diffs else 0.0
        return (m, m)
    stats = paired_ttest(diffs)
    mean, se, df = stats["mean"], stats["se"], stats["df"]
    # two-sided 97.5th percentile t critical value: invert t_sf via bisection
    # (no closed form; df is small (<=100 for our seed counts) so this is cheap)
    lo, hi = 0.0, 1000.0
    target = 0.025
    for _ in range(100):
        mid = (lo + hi) / 2
        if t_sf(mid, df) > target:
            lo = mid
        else:
            hi = mid
    t_crit = (lo + hi) / 2
    margin = t_crit * se
    return (mean - margin, mean + margin)


def wilcoxon_signed_rank(diffs):
    """Wilcoxon signed-rank test of diffs against a null median of 0.

    Normal approximation with continuity and tie correction - standard
    practice once n is not tiny (all our seed counts are >=12).
    """
    nz = [d for d in diffs if d != 0]
    n = len(nz)
    if n == 0:
        return {"n": 0, "n_zero": len(diffs), "w_plus": 0.0, "z": 0.0, "p_value": float("nan")}
    order = sorted(range(n), key=lambda i: abs(nz[i]))
    ranks = [0.0] * n
    tie_correction = 0.0
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(nz[order[j + 1]]) == abs(nz[order[i]]):
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        t = j - i + 1
        tie_correction += t ** 3 - t
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    w_plus = sum(r for r, d in zip(ranks, nz) if d > 0)
    mean_w = n * (n + 1) / 4.0
    var_w = n * (n + 1) * (2 * n + 1) / 24.0 - tie_correction / 48.0
    sd_w = math.sqrt(var_w) if var_w > 0 else 0.0
    if sd_w == 0:
        z = 0.0
    else:
        delta = w_plus - mean_w
        cc = 0.5 if delta > 0 else (-0.5 if delta < 0 else 0.0)
        z = (delta - cc) / sd_w
    p = 2 * (1 - norm_cdf(abs(z)))
    return {"n": n, "n_zero": len(diffs) - n, "w_plus": w_plus, "z": z, "p_value": p}


def differential_report(diffs):
    """Full paired-differential report for a list of (my - opponent) values.

    Tests the null hypothesis that the true mean/median differential is 0.
    """
    t = paired_ttest(diffs)
    w = wilcoxon_signed_rank(diffs)
    ci = ci95_mean(diffs)
    skew = skewness(diffs)
    kurt = excess_kurtosis(diffs)
    t_sig = t["p_value"] < 0.05 if not math.isnan(t["p_value"]) else None
    w_sig = w["p_value"] < 0.05 if not math.isnan(w["p_value"]) else None
    disagree = t_sig is not None and w_sig is not None and t_sig != w_sig
    return {
        "n": len(diffs), "mean": t["mean"], "sd": t["sd"], "se": t["se"],
        "ci95": ci, "skewness": skew, "excess_kurtosis": kurt,
        "ttest": t, "wilcoxon": w, "disagree": disagree,
    }


def format_differential(report, label="differential"):
    t, w = report["ttest"], report["wilcoxon"]
    lo, hi = report["ci95"]
    lines = [
        f"  {label}: n={report['n']}  mean={report['mean']:+.1f}  sd={report['sd']:.1f}  "
        f"se={report['se']:.2f}",
        f"    95% CI: [{lo:+.1f}, {hi:+.1f}]",
        f"    paired t-test:  t={t['t_stat']:+.3f}  df={t['df']}  p={t['p_value']:.4f}",
        f"    wilcoxon:       z={w['z']:+.3f}  n_pairs={w['n']}  p={w['p_value']:.4f}"
        + (f"  ({w['n_zero']} zero diffs excluded)" if w['n_zero'] else ""),
        f"    skewness={report['skewness']:+.2f}  excess_kurtosis={report['excess_kurtosis']:+.2f}"
        + ("  -- SEVERE, t-test's normality assumption is questionable, trust wilcoxon"
           if abs(report['skewness']) > 1.0 or abs(report['excess_kurtosis']) > 3.0 else ""),
    ]
    if report["disagree"]:
        lines.append("    !! t-test and wilcoxon disagree at alpha=0.05 - trust wilcoxon")
    return "\n".join(lines)


def min_detectable_effect(sd, n, power=0.80, alpha=0.05):
    """Minimum detectable effect (raw units) for a one-sample/paired test,
    normal approximation to the noncentral-t power calculation. Standard
    and adequate for n>=~10; exact would need the noncentral t distribution,
    which is overkill for a seed-count planning estimate.
    """
    z_alpha = norm_quantile(1 - alpha / 2)
    z_power = norm_quantile(power)
    return (z_alpha + z_power) * sd / math.sqrt(n)
