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
