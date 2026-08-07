---
name: new-strategy
description: Run a disciplined strategy experiment on the Kaggriculture agent. Use whenever testing a policy change, tuning PARAMS, or evaluating whether a change to agent/ actually improved play. Enforces baseline-first measurement and logging to docs/strategy-log.md.
---

# Running a strategy experiment

Never claim an improvement without an arena run. The environment is noisy and
the ladder scores win/loss only, so intuition about "this should be better" is
unreliable here.

## Procedure

1. **Read `docs/strategy-log.md` first.** If this idea is already recorded as
   REJECTED, say so and stop rather than repeating it.
2. **Establish the baseline.** Run `make arena` on the current `main` and note
   the overall win rate. Do not reuse a number from an earlier session — the
   opponent pool may have changed.
3. **Branch.** `git checkout -b strat/<short-name>`.
4. **Make one change.** One hypothesis per branch. If you find yourself
   changing the planner and the market logic together, split it.
5. **Run `make test` first** — if `plants_weeded` or `animals_lost` is nonzero,
   or an invariant test is red, that's a bug. Fix it before measuring strategy.
6. **Run `make arena`** on the same seeds and same opponents as the baseline.
7. **Judge honestly.** +5pp overall or clear bank separation across every seed
   = real. Smaller = noise; either run more seeds or record INCONCLUSIVE.
   A change that wins on 2 seeds and loses on 4 is not an improvement.
8. **Append to `docs/strategy-log.md`** using the format at the top of that
   file. Record REJECTED results too — they are the most valuable entries.
9. If ADOPTED: merge, then `make freeze NAME=<version>` and add the snapshot to
   `DEFAULT_OPPONENTS` in `arena/run.py` so future versions must beat it.

## Anti-patterns

- Tuning `PARAMS` against a single seed. You will fit the seed.
- Dropping `pass`/`random`/`starter` from the pool because "we beat them
  easily". They are the only opponents that aren't our own lineage; without
  them, self-play overfitting is invisible.
- Editing `SEEDS` in `arena/run.py`. That invalidates every prior log entry.
- Reporting "it feels better" or reasoning from the code alone. Numbers or it
  didn't happen.
