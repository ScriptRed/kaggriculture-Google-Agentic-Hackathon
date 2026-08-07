#!/usr/bin/env python3
"""The fitness function.

Runs the candidate agent against a fixed opponent pool over a fixed seed set
and reports win rate plus diagnostics. This number is the only evidence that
counts for "did that change help".

    python arena/run.py                     # full run vs pool
    python arena/run.py --quick             # 3 seeds vs starter
    python arena/run.py --opponents starter random
    python arena/run.py --seeds 20 --json results.json

Seeds are fixed by default so runs are comparable. Do not change SEEDS
casually - if you do, every prior result in strategy-log.md is invalidated.
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arena.metrics import episode_metrics, format_summary  # noqa: E402

SEEDS = [11, 23, 37, 41, 59, 67, 73, 89, 97, 103, 113, 127]
DEFAULT_OPPONENTS = ["starter", "random"]


def _load_agent(spec):
    """spec is 'starter'/'random'/'pass', a frozen pool name, or a path."""
    if spec in ("starter", "random", "pass"):
        return spec
    p = Path(spec)
    if p.exists():
        return str(p)
    frozen = ROOT / "arena" / "opponents" / spec / "main.py"
    if frozen.exists():
        return str(frozen)
    raise SystemExit(f"unknown agent: {spec}")


def _play(args):
    candidate, opponent, seed, swap, episode_steps = args
    from kaggle_environments import make

    a = _load_agent(candidate)
    b = _load_agent(opponent)
    order = [b, a] if swap else [a, b]
    me = 1 if swap else 0

    env = make("kaggriculture",
               configuration={"episodeSteps": episode_steps, "seed": seed},
               debug=False)
    t0 = time.time()
    env.run(order)
    elapsed = time.time() - t0

    steps = env.steps
    banks = [steps[-1][0]["observation"]["farms"][i]["money"] for i in (0, 1)]
    my_bank, opp_bank = banks[me], banks[1 - me]
    result = 1 if my_bank > opp_bank else (0.5 if my_bank == opp_bank else 0)

    statuses = [steps[-1][i].get("status") for i in (0, 1)]
    errored = statuses[me] not in ("DONE", "ACTIVE", "INACTIVE")

    m = episode_metrics(steps, me)
    m.update(seed=seed, opponent=opponent, swap=swap, result=result,
             opp_bank=opp_bank, wall_s=round(elapsed, 1), errored=errored)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(ROOT / "agent" / "main.py"))
    ap.add_argument("--opponents", nargs="*", default=DEFAULT_OPPONENTS)
    ap.add_argument("--seeds", type=int, default=len(SEEDS))
    ap.add_argument("--steps", type=int, default=720)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    if args.quick:
        seeds, opponents = SEEDS[:3], ["starter"]
    else:
        seeds, opponents = SEEDS[:args.seeds], args.opponents

    # play both seats of every pairing - seat 0 spawns advantageously
    jobs = [(args.candidate, opp, s, swap, args.steps)
            for opp in opponents for s in seeds for swap in (False, True)]

    print(f"arena: {len(jobs)} episodes  "
          f"({len(seeds)} seeds x {len(opponents)} opponents x 2 seats)")

    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for i, m in enumerate(ex.map(_play, jobs), 1):
            rows.append(m)
            tag = "W" if m["result"] == 1 else ("D" if m["result"] == 0.5 else "L")
            print(f"  [{i:>3}/{len(jobs)}] {tag} vs {m['opponent']:<10} "
                  f"seed={m['seed']:<4} bank={m['final_bank']:>9.0f} "
                  f"opp={m['opp_bank']:>9.0f} ({m['wall_s']}s)"
                  + ("  ERRORED" if m["errored"] else ""))

    print()
    errs = sum(1 for r in rows if r["errored"])
    if errs:
        print(f"!! {errs} episodes errored - fix before trusting anything below")

    for opp in opponents:
        sub = [r for r in rows if r["opponent"] == opp]
        wr = 100 * sum(r["result"] for r in sub) / len(sub)
        print(f"vs {opp:<12} win rate {wr:>6.1f}%   "
              f"mean bank {sum(r['final_bank'] for r in sub)/len(sub):>10.0f}")

    overall = 100 * sum(r["result"] for r in rows) / len(rows)
    print(f"\nOVERALL WIN RATE  {overall:.1f}%   ({len(rows)} episodes)\n")
    print(format_summary(rows))

    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2, default=str))
        print(f"\nwrote {args.json}")

    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
