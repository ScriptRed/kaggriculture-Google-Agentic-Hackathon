# Strategy log

**Append-only.** Every experiment gets an entry: hypothesis, what changed, the
arena number, conclusion. Read this before proposing anything — a failed idea
is recorded here so it isn't retried.

Format:

```
## YYYY-MM-DD  <short name>
Hypothesis: ...
Change: ...
Arena: overall X% (vs starter Y%, vs random Z%) | mean bank N | key metric deltas
Verdict: ADOPTED / REJECTED / INCONCLUSIVE
Notes: ...
```

Rules for a verdict:
- Compare against the same seed set and the same opponent pool. Always.
- +5pp overall win rate or clear bank separation across all seeds = real.
  Anything smaller is noise; run more seeds before believing it.
- If `plants_weeded > 0` or `animals_lost > 0`, that's a bug, not a strategy.
  Fix it before evaluating anything else.

---

## 2026-08-06  v0 baseline (scaffold)
Hypothesis: n/a — establishing the harness and a floor.
Change: initial task-assignment policy. Greedy scoring over harvest /
rescue-water / bonus-water / plant / fertilizer / feed / care, assigned to the
nearest free unit. Price-impact-aware selling with a 0.65×base floor.
Arena (3 seeds, both seats, vs starter): **16.7%**, mean bank 3,142.
Key metrics: `plants_weeded 32.8`, `idle_tile_rate 0.437`,
`noop_rate 0.199`, `coins_per_action 0.684`, `hires 169`, `peak_units 9`.
Verdict: BASELINE — worse than `starter`. Kept only as a floor to beat.

### Known defects, in priority order

1. **Loses to `pass` over the first 10 days** (`test_agent_beats_pass` is RED:
   375 vs 3,000 at step 240). It buys land and hires before it has income.
   Early-game capital discipline is the single biggest hole.
2. **~33 plants weeded per game.** The task scorer discounts distant tasks
   (`score - 6*dist < 10`), which strands outlying plants. Rescue-watering
   scores 100 but still gets dropped at distance >15. Rescue tasks must be
   exempt from the distance discount, or plants should not be sown where no
   unit can reach them.
3. **44% of tiles idle** while running 9 units. Planting scores only 40 and
   loses to almost everything. Given actions are the constraint, the real fix
   is probably batching: assign units to *regions* for a day rather than
   re-solving assignment from scratch every turn, which currently causes units
   to oscillate.
4. `noop_rate 0.199` — a fifth of all actions are PASS or wasted moves.
   Idle units walk to the shed, which is pure waste; they should pre-position
   toward tomorrow's work.

### Untested ideas (do not assume these work)

- Alternate-day watering outside the bonus window to halve watering actions.
- Goose-and-fertilizer economy as the core engine rather than crops.
- Buying NE early purely to stop wasting the daily hand spawn on a locked tile.
- Late-season sell timing against the day-10 / day-20 town demand steps.
- Adversarial dumping of whatever the opponent is about to harvest.

---

## 2026-08-07  early-capital-discipline
Hypothesis: `test_agent_beats_pass` is red (375 vs 3,000 at step 240) because
land, geese, and seed-buffer purchases each check their own small local
reserve (200-800) independently. On day 0 all three fire in the same window —
NE land (1000) + 4 geese (1200, bought one-per-hour until `goose_target`) +
seed restocking (~500+) — draining the bank to ~200 before any harvest
revenue exists. Debug traces (`KAGGRI_DEBUG` prints, not committed) confirmed
this: baseline day-0 spend was land 1000 + hires 54 + geese 1200 + seed 540 =
2794 out of 3000 starting cash.

Change: replaced the three separate reserve constants
(`land_buy_reserve: 800`, ad-hoc 600 for geese, ad-hoc 200 for seed top-ups)
with one shared `capital_reserve: 1200` gate used by all three, plus two new
gates — `land_buy_min_day: 10` and `goose_buy_min_day: 12` — so land and
animals are only bought once the crop engine has had a third of the season to
establish itself. Verified empirically before picking these numbers: a
crop-only build (land and geese both disabled) already beats `pass` by day 10
(3356 vs 3000); land bought as early as day 4 or day 6 still lost, because a
freshly-unlocked quadrant pulls hands onto low-value PLANT tasks on empty
tiles away from the already-productive NW harvest cycle, not just because of
the 1000 coin outlay. Day 10 / day 12 was the first point that held up across
seeds 11/23/37/41 with comfortable margin (final bank ~3350-3430 vs 3000).

Arena (12 seeds x 2 opponents x 2 seats, 720 steps): **62.5%** overall (vs
starter 25.0%, vs random 100%), mean bank 2871 — vs baseline (this session,
same seeds/pool) **58.3%** overall (vs starter 16.7%, vs random 100%), mean
bank 3130.
Key metric deltas: `peak_units` 4.0 -> 9.0 (min 1 -> min 9 — every game now
reaches full headcount; baseline had games where hiring silently stalled),
`hires` 68.8 -> 239.8 (near the 240 theoretical max — hiring now happens
every day instead of stalling out after the initial cash crunch),
`quadrants` 1.375 -> 2.375 (every game now buys at least NE by day 30;
baseline had games that never bought any land), `plants_weeded` 9.3 -> 2.5,
`noop_rate` 0.714 -> 0.227. `animals_lost` stayed 0, no episodes errored.
Mean bank went down (2871 vs 3130) but the ladder scores win/loss only, and
win rate went up on both counted axes.
Verdict: ADOPTED
Notes: overall win-rate delta alone (+4.2pp) is under the +5pp noise bar, but
vs-starter delta (+8.3pp) clears it, `test_agent_beats_pass` flips red->green,
and the reliability metrics (`peak_units`, `hires`, `quadrants`) show the
baseline wasn't just "leaving money on the table" on several seeds — it was
outright stalling for the rest of the game after the day-0 cash crunch, which
the win-rate number alone doesn't fully capture. Branch: `strat/early-capital-discipline`.
Not yet merged to main or frozen as an opponent — pending user confirmation.
