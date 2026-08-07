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
2. **Never run `make arena` (or anything using `agent/run.py`) in the
   background while editing `agent/`** in the same working tree in the
   foreground — `arena/run.py` snapshots `agent/` per invocation specifically
   so this can't corrupt a result, but a stale snapshot from a run you forgot
   about is still a trap. When in doubt, check the run header's git SHA.
3. **Establish the baseline.** Run
   `python arena/run.py --compare <current-best-frozen-version>` on current
   `main` and note the paired bank differential (mean, 95% CI, t-test,
   Wilcoxon). This is the primary signal — see CLAUDE.md for why. Also note
   the plain `make arena` win rate; it's the ladder-facing number but not
   what you judge the change by. Do not reuse a number from an earlier
   session — the opponent pool may have changed.
4. **Branch.** `git checkout -b strat/<short-name>`.
5. **Make one change.** One hypothesis per branch. If you find yourself
   changing the planner and the market logic together, split it.
6. **Run `make test` first** — if `plants_weeded` or `animals_lost` is nonzero,
   or an invariant test is red, that's a bug. Fix it before measuring strategy.
7. **Run `python arena/run.py --compare <current-best-frozen-version>`** on
   the same seeds/reference as the baseline, then `make arena` for the
   win-rate cross-check.
8. **Judge by the paired differential, not win rate.** ADOPTED needs: the
   95% CI excludes zero, the paired t-test and Wilcoxon signed-rank agree
   (trust Wilcoxon if they don't — final-bank distributions run heavy-tailed;
   `differential_report` in `arena/metrics.py` flags this for you), and the
   point estimate clears ~50 coins (headroom over the measured n=48
   conservative MDE, not a hair over zero). A win-rate swing with no matching
   bank-diff swing is suspicious, not confirmatory — look for a bug, not a
   deeper effect. Smaller/ambiguous results are INCONCLUSIVE, not REJECTED;
   consider a bigger `--seeds` before spending a verdict.
9. **Append to `docs/strategy-log.md`** using the format at the top of that
   file. Record REJECTED results too — they are the most valuable entries.
10. If ADOPTED: merge, then `make freeze NAME=<version>` and add the snapshot
    to `DEFAULT_OPPONENTS` in `arena/run.py` so future versions must beat it.
11. **Push to `origin main`** as part of every merge to `main`. Local commits
    that never leave the machine aren't a shared record of anything.

## Anti-patterns

- Tuning `PARAMS` against a single seed. You will fit the seed.
- Dropping `pass`/`random_seeded`/`starter` from the pool because "we beat
  them easily". They are the only opponents that aren't our own lineage;
  without them, self-play overfitting is invisible.
- Judging a change by win rate alone. Its standard error at realistic seed
  counts (measured: ~10-13pp at n=12, still ~5-8pp at n=48) is often bigger
  than the effect you're trying to detect. Use `--compare`.
- Editing `SEEDS` in `arena/run.py` without a dated `docs/strategy-log.md`
  entry justifying it — it invalidates every prior log entry's exact
  reproducibility, so the reason has to be on the record. (The 2026-08-07
  12->48 expansion is the one sanctioned instance; see that entry for the
  empirical justification. Don't cite it as precedent for a casual future
  change — write a new entry.)
- Reporting "it feels better" or reasoning from the code alone. Numbers or it
  didn't happen.
