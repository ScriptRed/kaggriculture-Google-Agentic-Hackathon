# Kaggriculture agent

Kaggle simulation competition. Two bots each run a farm for 30 in-game days
(720 turns). Most coins in the bank at turn 720 wins. Ladder rating is
**win/loss only — margin is ignored.**

## Hard constraints (never violate)

- **No network at runtime.** Rules §2.12 forbids ingress/egress during an
  episode. No LLM calls, no HTTP, no file downloads inside `agent/`.
- Submission entrypoint is `agent/main.py`, packaged so `main.py` is at the
  archive root. Files land in `/kaggle_simulations/agent/` — imports must be
  relative-safe.
- Budget: 1.6 vCPU, 6.5 GiB RAM, 100 MiB submission, 8 GiB disk.
- Keep per-turn compute well under ~50ms. 720 turns × many episodes.
- Repo stays **private** until the competition closes (Rules §3.6a forbids
  private code sharing; a public repo shares with everyone).

## Commands

```bash
make arena          # candidate vs frozen pool, fixed seeds -> win rate + metrics
make quick          # 3 seeds vs starter, fast smoke test
make test           # pytest: constants match env, invariants hold
make freeze NAME=x  # snapshot agent/ into arena/opponents/x/
```

`make arena` is the fitness signal. **Never claim an improvement without it.**
Fixed seeds, same pool, every time. A change is real at >= +5pp win rate or a
clear bank delta across the full seed set; anything smaller is noise.

## Layout

- `agent/main.py` — the submission. Entry: `def agent(obs) -> dict`.
- `agent/constants.py` — game tables, transcribed from env source and
  verified by `tests/test_constants.py`. **Do not edit by hand without
  re-running the test.**
- `agent/policy/` — planner modules. Keep `main.py` thin.
- `arena/run.py` — the harness. `arena/metrics.py` — the diagnostics.
- `docs/rules.md` — competition text. `docs/economics.md` — derived analysis.
- `docs/strategy-log.md` — **append-only.** Every experiment: hypothesis,
  arena result, conclusion. Read it before proposing anything; a failed idea
  is recorded there so we don't retry it.

## Game facts that are easy to get wrong

- `consecutive_unwatered` starts at **1** on planting. Plant and don't water
  that same day → weed that night. No grace period.
- Weeding triggers at `>= 2`, so **alternate-day watering keeps a plant
  alive.** Daily watering is only needed inside the yield bonus window.
- One-time crops: watering during ages `(max_yield_day+1)//2 .. max_yield_day`
  adds +1 yield (+2 if fertilized). Outside that window watering adds nothing.
- Melon caps at 6 yield **without** fertilizer. Fertilizing melon is wasted.
  Wheat and carrot need fertilizer to reach their listed max.
- Land order is **fixed**: NE ($1000), SW ($2000), SE ($4000). No choice of
  quadrant.
- Hire cost is `fib(n)` for the n-th hire *that day*, resetting daily:
  1,1,2,3,5,8,13,21... Ten hands cost 143 coins for 240 extra actions.
  **Actions are the binding constraint, not money or land.**
- Every surviving animal yields 1 fertilizer/day whether fed or cared for or
  not. `COLLECT_FERTILIZER` is ~$60-100 for one action — best rate in the game.
- Shed cap is 100 non-seed items; overflow at end-of-day is **discarded**.
- Premium goods (melon, strawberry, milk, wool) hit the $1 floor within roughly
  one field's output. Dumping them destroys your own price. Wheat and eggs
  absorb volume.
- You can see the opponent's tiles. They share your market.

## Style

- Pure functions where possible; the policy should be testable without the env.
- No global mutable state — episodes run in-process and will leak between games.
- Defensive: never raise. A crash forfeits the episode. Wrap `agent()` in a
  try/except that falls back to `PASS`.
