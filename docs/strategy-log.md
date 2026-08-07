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

Update 2026-08-07 (later same day): merged to main and frozen as
`v1-early-capital-discipline` per user confirmation. **The 58.3% baseline
number above is contaminated — see the "Failure modes" section below for the
corrected, clean comparison.** Short version: a properly isolated v0 actually
scores 68.8% overall / 37.5% vs starter, not 58.3%/16.7%. The relative
improvement claimed here does not hold up against the clean baseline; v1 may
be a regression on raw win rate despite fixing `test_agent_beats_pass` and
cutting `plants_weeded` and `noop_rate`. Do not cite the 58.3%/62.5% numbers
above as valid without reading that section first.

---

## Failure modes

### 2026-08-07  Testing-methodology contamination of the v1 baseline

**This corrects the "v0 baseline" arena numbers used in the
early-capital-discipline entry above. Read this before trusting any
comparison against that entry.**

Task: investigate a claim from the previous session that "several v0
baseline games silently stalled for the whole match after the day-0 cash
crunch" (observed as `bank=3000` exactly, both seats, on seeds 89/97/103/
113/127 vs `starter`, in that session's `make arena` baseline run).

**Finding: the stall does not reproduce.** A clean, isolated copy of v0
(`git show 1b11835:agent/main.py`, run via `arena/run.py --candidate
<isolated path>` so nothing could touch the file mid-run) was re-run on the
same 12-seed pool, both seats, vs `starter` and `random`:

- Clean v0: **68.8% overall** (37.5% vs starter, 100% vs random), mean bank
  3065, bank range 1875-3917. None of seeds 89/97/103/113/127 froze — e.g.
  seed 89 nets 3411, seed 97 nets 3445.
- This directly contradicts the previous session's reported 58.3% overall /
  16.7% vs starter / several games flatlined at exactly 3000.

**Root cause: I was editing `agent/main.py` in the working tree while a
background `make arena` job's subprocesses were still reading that same file
off disk.** In the previous session I launched the baseline arena run in the
background, then immediately started branching and editing `PARAMS` in
`agent/main.py` — including a throwaway experiment that set the effective
seed-purchase reserve to 999999 (to isolate crop-only economics), followed by
`git checkout -- agent/main.py` to revert, repeated several times, all while
the arena subprocesses were still spinning up and executing episodes. Since
`kaggle_environments` execs the agent file once when a given episode's
subprocess starts, different episodes captured different, sometimes broken,
transient states of the file — including at least one state where seed
purchases were fully blocked, which is structurally capable of producing the
observed flatline (see the mechanism below). I did not save any of the
intermediate states, so I cannot name the exact commit that ran; I can only
show that (a) genuine v0 does not do this, and (b) I was actively mutating
the file during the exact window those episodes ran in. This is a testing-
hygiene bug on my part, not a v0 defect. **Going forward: never run `make
arena` (or anything that reads `agent/main.py` from a background job) while
editing that file in the same working tree — use `--candidate` against an
isolated copy, or a worktree, when a background measurement is in flight.**

Consequence for the early-capital-discipline entry above: the "baseline"
58.3%/16.7% numbers were measured against a mix of genuine v0 and
contaminated episodes, not against v0 itself. The clean comparison is:

| | overall | vs starter | vs random | mean bank | plants_weeded | peak_units |
|---|---|---|---|---|---|---|
| v0 (clean) | 68.8% | 37.5% | 100% | 3065 | 31.8 | 9.0 |
| main (post-fix, clean) | 62.5%\* | 25.0% | 100% | 2591\*\* | 2.2 | 9.0 |

\*main's 12-seed pool now includes `v1-early-capital-discipline` itself
(added to `DEFAULT_OPPONENTS` when frozen), which is a mirror match against
an identical agent and contributes a meaningless ~50% to the blended
average; the starter/random-only overall (comparable to v0's number) is
**62.5%** as well since random is 100% either way — recomputed directly:
(25.0×24 + 100×24)/48 = 62.5%. \*\*mean bank across the starter+random legs
only (72-episode run's blended mean was 2591 including the v1 mirror leg).

**On a clean footing, v1 is worse than v0 on win rate** (62.5% vs 68.8%
overall, 25.0% vs 37.5% vs starter) despite fixing the red test and cutting
`plants_weeded` (31.8 → 2.2) and stabilizing `hires`/`peak_units`. This is
the opposite conclusion from what got merged. I am not reverting unilaterally
per standing instructions, but this needs a decision — see the note appended
to the early-capital-discipline entry above, and task 3 (seed-variance audit)
is now more consequential than originally scoped, since it's comparing
against a baseline I have to re-derive, not one already on record.

### The stall mechanism itself is real, and current main is *more* exposed to it than v0

Independent of the contamination above, I stress-tested the causal chain
predicted in this investigation: private `seeds` start at 0 for every crop
with no free stock (env source, `kaggriculture.py:158`). If `BUY_SEED` never
fires, `_pick_crop` still returns a crop name but `seeds.get(crop, 0)` is 0,
so `_build_tasks`'s `if crop and seeds.get(crop, 0) > 0` is always false, no
`PLANT` task is ever generated, and — once any already-planted crop has been
harvested and cleared — `_build_tasks` returns `[]`. Every unit then falls
into `_assign`'s "walk to shed" branch; since the farmer's default spawn and
new hands both spawn at/near a shed tile, `_step_toward` returns `None`
immediately and the action resolves to `PASS`. Money never moves again
because hiring is the only other thing gated on cash, and it's now spent on
units with nothing to do.

Verified directly with `configuration={"startingMoney": ...}` overrides
(seed 11 vs `pass`, 240 steps):

| startingMoney | v0 worst 48-turn PASS% | v0 final bank | main worst 48-turn PASS% | main final bank |
|---|---|---|---|---|
| 50 | 100% | 50 (frozen from turn 0) | 100% | 50 (frozen from turn 0) |
| 1000 | 61.5% | 514 (recovers) | **100%** | 670 (declining, not frozen at exactly start, but stuck for the full window I checked — day 0 through day 9) |
| 1300 | 61.1% | 712 (recovers) | **100%** | 865 (same pattern) |
| 3000 (normal) | 54.9% worst window | n/a | 65.5% worst window | n/a |

At $50 both versions are fully and permanently dead (hire budget's
`money - 50` floor blocks hiring, and money never grows). That's an extreme,
not something the real game triggers (`startingMoney` is fixed at 3000 by
configuration).

The $1000-1300 rows are the important ones: **v0's seed-purchase reserve is
an ad-hoc 200, but main's unified `capital_reserve` is 1200** (set in the
early-capital-discipline fix). At $1000-1300 starting cash, v0 clears its
$200+seed-cost bar comfortably and keeps buying seeds/planting/harvesting
throughout — it recovers. Main never clears its $1200+seed-cost bar (money
only goes down from there, since it keeps hiring 7 hands/day at ~$33/day
using the *separate* `hand_budget_frac` gate, which is not tied to
`capital_reserve`), so it never plants a single seed and burns what little
cash it has on hands that have nothing to do. Traced turn-by-turn: main's
money declines monotonically and mechanically by exactly the daily hire
cost (1000 → 967 → 934 → ... → 670 by day 9), while every one of its 8
units outputs literal `PASS` every single turn of every single day.

**This did not trigger in either arena run this session** — v0's clean-run
minimum bank was 1875, main's was 1380, both comfortably above the ~1320
trap line — so it has not cost a game yet. But it is a real, not-yet-
triggered latent fragility that the early-capital-discipline fix made
*worse*, not better: it raised the seed-purchase reserve from 200 to 1200
without also pausing hire spend when cash is scarce, narrowing the recovery
margin roughly 6x. A mid-game cash squeeze (bad market timing, an
aggressive opponent undercutting sale prices, a run of weeds) that would
have been survivable on v0 is not guaranteed to be survivable on main.

Answering the four original questions directly:

- **(a) What did "stalled" mean?** It doesn't reproduce on v0 — see above.
  The genuine mechanism (constructed via `startingMoney` stress test, not
  observed in real arena play) is: every unit outputs literal `PASS` every
  turn, farmer and hands alike, from the first turn cash-starvation begins.
- **(b) Causal chain:** cash stuck below `capital_reserve` (main) or the
  200 ad-hoc reserve (v0) with no crop already in the ground → `BUY_SEED`
  never fires → `seeds[crop]` stays 0 → no `PLANT` tasks → (once existing
  crops are cleared) `_build_tasks` returns `[]` → every unit's nearest
  free-task search finds nothing → falls to the shed-walk branch → already
  at the shed → `PASS` forever. Confirmed by direct per-turn trace, not
  inferred from reading the code.
- **(c) Impossible on main, or merely not triggered?** Neither, precisely —
  **not triggered under the 3000-starting-money conditions we actually
  play, and structurally *more* reachable on main than on v0** because of
  the reserve increase. Be suspicious of any future PARAMS change that
  raises `capital_reserve` further, or that decouples hire spend from
  available cash even more.
- **(d) Other routes into the same state?** Bank-near-zero mid-game is
  confirmed real (above) and is the only one that produces a *permanent*
  lock. The other three candidates were checked against the env source and
  do not, on their own, cause a full stall: shed-at-cap just discards
  overflow at end of day (`_drop_inventories_to_shed`) rather than blocking
  earning; `HARVEST` has no shed-capacity check at the point of harvest
  (`kaggriculture.py:432-459`) so "unharvestable because full" isn't a real
  state; `animals_lost` reaching nonzero only removes tasks for that one
  animal tile and doesn't touch crop income. Late-season `_pick_crop`
  returning `None` (`days_left < 4`) is intentional and doesn't cause a
  stall because already-planted crops still generate `WATER`/`HARVEST`
  tasks normally in that window — it's expected reduced activity, not a
  bug, and is why the regression test below runs the full 720 turns rather
  than checking the tail in isolation.

**Regression test added:** `tests/test_no_extended_stall` in
`tests/test_invariants.py` — asserts no 48-turn (2-day) window in a normal
720-turn, seed-11-vs-starter, $3000-starting episode is more than 90% PASS.
Currently passes on both v0 (worst window 54.9%) and main (worst window
65.5%) — it is a forward-looking guard, not a demonstration that either
version currently fails it. I deliberately did *not* encode the $1000-1300
stress scenario as a hard assertion in the test suite: doing so would fail
on main right now and block task 2 under the user's stated ordering, and
the fix for it (decouple hire spend from cash scarcity, or lower
`capital_reserve`, or both) is a PARAMS/planner change that belongs in its
own experiment, not folded into a diagnostic task. Flagging it here for a
decision on priority rather than fixing it unasked.

### 2026-08-07  Arena determinism and noise-floor audit

Prompted by the previous entry: v0 scored 58.3%/16.7% last session and
68.8%/37.5% this session on the nominally same 12-seed, 2-opponent pool.
Before trusting any number in this file, checked whether the arena is
reproducible at all.

**(c) Opponent pool drift, checked first as requested — ruled out.** Both
conflicting runs used `arena: 48 episodes (12 seeds x 2 opponents x 2
seats)` per their own log headers (still on disk), and `arena/run.py` at
commit `b24133f` (current at the time of both runs) has
`DEFAULT_OPPONENTS = ["starter", "random"]`, identical to v0's. `v1-early-
capital-discipline` was not added to the pool until commit `c341f3f`, after
both of those runs. Pool composition is not the explanation for that
specific discrepancy — the testing-methodology contamination described in
the entry above is.

**(a) Same command twice, same commit (`cf51ee3`, current main), same
seeds/pool, no code changes between — do NOT match bit-for-bit.**
`vs starter`: all 24 episodes identical across both runs (same
`final_bank`, `plants_weeded`, `hires`, `quadrants`, `idle_tile_rate`, down
to the last unit). `vs random`: **all 24 episodes differ** — different
`final_bank`, different `plants_weeded`, different `idle_tile_rate`, every
single one. Win-rate summary happened to match this pair of runs (25.0% /
100% / 62.5%) but that's not guaranteed — the per-episode banks are
genuinely different runs, not the same run reported twice.

**(b) Root cause, isolated and confirmed:**
`kaggle_environments/envs/kaggriculture/kaggriculture.py:1014` —
`random_agent`'s `rng = random.Random()` is constructed fresh, with no
seed, on *every call* (every turn, not once per episode). Per the stdlib
docs, `Random()` with no argument seeds itself from OS entropy, and does
not consult the episode's configured seed or the global `random` module's
seed state at all. This is in the installed `kaggle_environments` package,
not our code — we cannot fix it without monkeypatching a third-party
dependency.
  - Confirmed the env's own seeded RNG (weed spawns, shop unlocks) is fine:
    printed the `unlocked_shops` sequence for seed 11 across two full
    720-turn runs — identical, turn for turn.
  - Confirmed it isn't `ProcessPoolExecutor` / shared mutable state: reran
    `vs random` with `--workers 1` (fully serial, no parallelism at all)
    twice — still diverges (mean bank 3620 vs 3111 across 4 seeds). Given
    `vs starter` is bit-identical *even when run via the same parallel
    executor as vs random*, shared-state-across-workers is ruled out
    directly — if it were real we'd see it on the starter leg too.
  - So: **everything under our control (env RNG, `starter`, `pass`, our own
    candidate agent) is fully, bit-for-bit deterministic given a fixed
    seed. Only the built-in `random` opponent is not**, and by construction
    (fresh entropy every turn), not just "not seeded once."
  - This has not yet flipped a single win/loss outcome — `vs random` has
    been 100% in every rerun across both sessions — so it hasn't corrupted
    the ladder-relevant win/loss signal so far. But it does mean `vs
    random`'s bank/diagnostic numbers are not reproducible, and — more
    importantly — that `random` contributes **zero variance and zero
    discriminating information** to the "overall" win-rate metric. It's a
    constant 50%-of-the-pool ceiling that any competent agent clears every
    time.

**Structural consequence for the acceptance bar:** because `random` is
statistically inert, blending it into "overall" mechanically halves the
visible size of any real effect that exists in the `vs starter` leg (a
-12.5pp swing vs starter shows up as only -6.25pp in "overall" purely
because half the pool contributes zero variance either way). The skill's
+5pp-on-overall bar was already too small relative to noise before this;
diluting the signal with an uninformative opponent makes it worse.

**Standard error, computed from real per-seed data (not assumed):**
using the empirical variance of per-seed `vs starter` scores (each seed's
result averaged across both seat-swapped episodes, so seed-level not
episode-level, correcting for the swap-pair correlation the naive
i.i.d.-episode calculation ignores):

| | vs-starter win rate | seed-level SE | naive episode-level SE (n=24, ignores swap correlation) |
|---|---|---|---|
| main (post-fix) | 25.0% (6/24) | **9.7pp** | 8.8pp |
| v0 (clean) | 37.5% (9/24) | **12.5pp** | 9.9pp |

On the blended "overall" metric (random contributes ~0 variance, exactly
half the episode weight): SE(overall) ≈ SE(vs-starter)/2 ≈ **4.8-6.3pp**.

**Direct answers:**
- **Is the arena deterministic given fixed seeds and a fixed pool? No** —
  specifically because of the built-in `random` opponent's per-turn
  unseeded RNG. Everything else (env, `starter`, `pass`, our own agent) is
  fully deterministic, confirmed directly, not assumed.
- **Can it be made deterministic?** Not without patching vendored code we
  don't own. Recommendation instead: stop treating `vs random` as a
  contributor to the headline number. Keep it only as a sanity floor (it
  should always be ~100%; if it's ever not, that's a real bug worth
  investigating), and judge strategy changes on `vs starter` (and future
  genuinely-distinct, deterministic opponents) instead of the blended
  "overall" figure.
- **Is the noise floor bigger than the +5pp bar? Yes**, on both the
  vs-starter leg (9.7-12.5pp SE) and the diluted overall metric it's
  supposed to gate (4.8-6.3pp SE, i.e. the bar is roughly *one* standard
  error, not several). A +5pp "overall" result is not distinguishable from
  noise at any reasonable confidence level as currently measured.
- **Seed count needed:** to get SE down to 5pp (still only ~68% one-sided
  confidence — weak parity with the *existing* bar, not a fix) needs
  **~75 seeds** on the vs-starter leg. To get the bar to mean roughly what
  "+5pp = real" implies it means (SE ≈ 2.5pp, bar ≈ 2×SE) needs **~300
  seeds**. Neither number is currently in `arena/run.py`'s `SEEDS` list
  (12 seeds). Not changed here — the skill explicitly forbids editing
  `SEEDS` without invalidating every prior entry, and that decision belongs
  to the user, not to me mid-audit.

**Retroactive implication:** the -6.3pp (overall) / -12.5pp (vs starter)
gap between v1 and clean v0 reported in the previous entry is *larger* than
1 SE on vs-starter (12.5pp) but not by much, and well under the ~2×SE a
normal significance bar would want. **I should not have called it "v1 is
worse than v0" as confidently as I did — the honest statement is "the two
are not distinguishable from this sample; the point estimate favors v0 but
the gap is within noise."** That correction applies to my own prior report,
not just to the original merge decision.

**No code, PARAMS, or agent logic changed in this entry** — diagnostic
only, per instruction.
