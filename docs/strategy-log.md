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

### 2026-08-07  Arena infrastructure: snapshot isolation + seeded random opponent

Two fixes to the ruler itself, in response to the determinism audit above.
No agent/PARAMS/strategy code changed.

**Snapshot isolation (commit `3ed8330`).** `arena/run.py` now copies
`agent/` into a fresh `tempfile.mkdtemp()` snapshot at the start of every
invocation; any candidate/opponent path resolving inside the live `agent/`
dir is transparently redirected to the snapshot. Verified adversarially,
not just by reasoning about the code: launched a real 72-episode run,
mutated `agent/main.py` mid-run to short-circuit to all-PASS (the exact
failure mode from the phantom-stall session), confirmed via `diff` that the
on-disk snapshot was untouched, and confirmed the run's actual results
(`hires` 239.9, healthy final banks ~2591) reflect the pre-mutation agent.
The run header now prints git SHA + dirty flag, the snapshot path, and the
opponent pool; the JSON output is now `{meta, episodes}` instead of a bare
list (breaking change to that format — anything reading the old flat array
needs updating, nothing in this repo currently does).

**Seeded random opponent (commit `4643057`).** Added
`arena/opponents/random_seeded/main.py`, replicating the built-in
`random_agent`'s action distribution but deriving its RNG from the episode
seed + turn + seat instead of OS entropy.
`configuration["seed"]` is cleared before any agent (built-in or custom)
ever sees it — confirmed empirically with a probe agent
(`config.get("seed")` returned `None`) — so `arena/run.py` now sets a
`KAGGRI_ARENA_SEED` env var immediately before each episode's `env.run()`,
which the opponent reads. Deliberately does not import from `agent/`
(self-contained, so it isn't affected by the snapshot mechanism or by
edits to the live agent code). Verified bit-for-bit reproducible both
standalone (100-turn per-action diff, 0 mismatches) and through the full
arena harness post-split (0 bank diffs across two independent runs, all
episodes, all metrics). Replaces `"random"` with `"random_seeded"` in
`DEFAULT_OPPONENTS`.

Net effect: every number produced by `arena/run.py` from this commit
forward is fully reproducible given the same seeds/pool/code state, and is
self-documenting about exactly which code state produced it. The
`+5pp`/noise-floor problem from the determinism audit above is unrelated to
this and still stands — this fixes the *reproducibility* of a given
measurement, not its *statistical power*.

### 2026-08-07  Paired bank differential as the primary development signal

Task: win rate's standard error was measured at ~10-13pp at n=12 seeds
(previous entry) — bigger than the +5pp acceptance bar. Add a
lower-variance estimator for development, keep win rate as the ladder-facing
check, and empirically re-derive what seed count and acceptance bar are
actually defensible.

**Implementation (`arena/metrics.py`, `arena/run.py`).** Added
`differential_report()`: paired t-test, Wilcoxon signed-rank (normal
approximation, tie-corrected), 95% CI, skewness, and excess kurtosis for a
list of per-episode `(my_bank - opp_bank)` values. No scipy: `.github/
workflows/arena.yml` only installs `kaggle-environments` and `pytest`, so a
scipy import in `arena/` would break CI, and `agent/` must never gain a
dependency beyond stdlib regardless. Implemented the regularized incomplete
beta function (Student's t CDF), the normal CDF/quantile (Acklam's rational
approximation), skewness/kurtosis, and the paired t and Wilcoxon tests
directly in pure Python. **Cross-validated against scipy locally (dev-only,
not a runtime dependency)** over 200 randomized trials spanning n=5..96 and
several distribution shapes (normal, skewed, tied, zero-inflated): t-statistic
matched to 1.8e-15, Wilcoxon p-value to 2.2e-16, 95% CI bounds to 1.6e-13,
skewness/kurtosis to ~1e-14, and `norm_quantile` to 1.8e-9 (within the stated
error bound of the Acklam approximation used). The manual implementation is
correct, not just plausible-looking.

Every opponent leg of a normal run now prints its differential report
alongside win rate, clearly labeled ladder-metric vs dev-signal. Added
`--compare <reference>` for a focused head-to-head report against one named
agent (frozen pool name or path) across the full seed set, both seats.

**Self-play null distribution.** `python arena/run.py --compare
v1-early-capital-discipline` with current `main` (byte-identical to that
frozen snapshot right now, confirmed by `diff`) is a true null: candidate
and reference are the same code, so the true effect is exactly zero. Ran it
on the original 12 canonical seeds (n=24 episodes) plus 50 additional
exploratory seeds (`random.Random(999999)`, not added to the canonical list,
used only for this analysis) for a more stable SD estimate — n=124 pooled.

Result: **mean differential is exactly 0.0 in every sample**, not just
statistically indistinguishable from zero. This is mathematically forced,
not a coincidence: for identical deterministic code, `diff(seed, swap=False)
= -diff(seed, swap=True)` exactly (whichever code runs in seat 0 behaves
identically regardless of which "role" we call it), so every seed's
swap-pair cancels perfectly. This is a real, useful confirmation that the
harness and the byte-identity of `main.py`/the frozen snapshot both hold —
if it hadn't come out to exactly 0, that would itself have been a bug.
Excess kurtosis came out severe (3.6-4.1, `differential_report` correctly
flagged it as "SEVERE, trust wilcoxon") — expected for a distribution built
entirely from ± pairs, and the reason Wilcoxon is reported as a co-equal
check rather than a footnote.

Pooled SD = 73.3 coins/episode (both-seats-combined, n=124) / 73.4
(conservative: one observation per seed, swap=False only, n=62 — these
came out nearly identical here specifically *because* of the exact-cancellation
property above, which won't hold for a real, non-self-play comparison. Report
both bounds; treat the conservative one as the planning basis).

**This number is dramatically smaller than I expected going in** — head-to-
head paired play cancels almost all of the between-seed environmental noise
(market/weed RNG) that dominates the win-rate-vs-a-fixed-third-party design,
because both agents face the *identical* realized market in the *same*
episode, competing directly, rather than two separate episodes against an
independent opponent. That is the actual mechanism behind "lowest-variance
estimator available," not just a slogan.

**MDE at 80% power, alpha=0.05 two-sided** (`min_detectable_effect`, normal
approximation to the noncentral-t power calc — standard and adequate at
these n, exact would need noncentral t and isn't worth it for a planning
estimate):

| n_seeds | bank diff, optimistic (n=2×seeds) | bank diff, conservative (n=seeds) | win rate, optimistic | win rate, conservative |
|---|---|---|---|---|
| 12 | 41.9 coins | 59.4 coins | 28.6pp | 40.4pp |
| 24 | 29.6 coins | 42.0 coins | 20.2pp | 28.6pp |
| 48 | 21.0 coins | 29.7 coins | 14.3pp | 20.2pp |
| 96 | 14.8 coins | 21.0 coins | 10.1pp | 14.3pp |

Typical final banks in this repo's arena runs range roughly 1300-4700 coins.
A 30-60 coin MDE is under 2% of that range — the paired differential can
detect real effects the current strategy log's win-rate-only entries could
never have distinguished from noise (the v1-vs-v0 gap flagged as
"within noise" two entries back was ~700-900 coins in mean bank — this
design would have called that decisively, one way or the other).

**Wall-clock, measured directly** (not estimated): 24 episodes (4 seeds × 3
opponents × 2 seats) took 15.4s with 7 workers = 0.641s/episode. Extrapolated:

| n_seeds | full 3-opponent pool (`make arena`) | `--compare` (1 opponent) |
|---|---|---|
| 12 | 46s | 15s |
| 24 | 92s | 31s |
| 48 | 184s (~3.1 min) | 62s |
| 96 | 369s (~6.1 min) | 123s |

**Decision: raised `SEEDS` from 12 to 48** (original 12 preserved, 36 new
seeds appended, generated by `random.Random(20260807)`, deduped). This is
the one sanctioned exception to the skill's "don't edit `SEEDS` casually"
rule — it's being done deliberately, on the record, with the empirical
justification above, not casually. `.github/workflows/arena.yml`'s CI job
is unaffected (`--seeds 6` explicitly caps it regardless of list length).
Rationale: 48 seeds costs ~3 min for a full pool run and ~1 min for a
`--compare`, both fully tolerable for iteration, and gets conservative bank-
diff MDE to ~30 coins (excellent — most real strategy changes will clear
this easily) while conservative win-rate MDE improves to ~20pp (still coarse,
but win rate is being demoted to a secondary/ladder-facing check, not the
primary signal, specifically because it can't be made precise at any
seed count that's cheap enough to iterate against — 96 seeds only buys
14.3pp optimistic / still requires trusting the optimistic bound to get
under 15pp).

**New acceptance bar** (replaces the flat "+5pp win rate" rule): ADOPTED
requires the paired differential's 95% CI to exclude zero, the t-test and
Wilcoxon to agree in significance (trust Wilcoxon if they don't), and the
point estimate to clear ~50 coins — comfortably above the n=48 conservative
MDE of ~30 coins, so a bare "technically significant" result isn't enough on
its own. Win rate is still reported and is the actual ladder metric, but a
win-rate swing unaccompanied by a matching bank-differential swing should be
treated as a signal to look for a bug in the measurement, not as
independent confirmation.

Updated `CLAUDE.md` and `.claude/skills/new-strategy/SKILL.md` to reflect
this. Not yet exercised on a real (non-self-play) comparison — Task D will
be the first real use of `--compare` against a genuinely different
candidate, which will be a useful check that the self-play-derived MDE
estimates hold up against actual strategic divergence and not just seat-
order noise.

No agent/PARAMS logic changed in this entry.

### 2026-08-07  Fix the capital_reserve stall trap

Hypothesis: at startingMoney $1000-1300, main locks into permanent PASS -
`capital_reserve=1200` never clears while hiring keeps draining cash, and
the observed real-game minimum bank (1380) was only a 4% margin above the
trap line (1320). Fix it: hiring must not be able to spend below what the
crop engine needs, the reserve must yield when no productive assets exist,
and reconsider whether a flat 1200 is the right shape at all.

**This took three attempts to get right, and the first two were real
regressions, not just smaller-than-hoped wins. Recording all three because
the failure modes are the useful part.**

**Attempt 1 - reserve yields to a much smaller flat value once we hold any
asset.** Fixed the deadlock (all 8 stress values passed). But
`--compare v1-early-capital-discipline` (identical starting code, so this
should be near zero) came back **mean -231.3, 95% CI [-298,-222], t and
Wilcoxon both p<0.0001, win rate 6.2%.** `plants_weeded` had jumped 2 -> 18.
Root cause, confirmed by comparing plant counts turn-by-turn against v1: a
smaller cash reserve let seed-buying refill the whole `seed_buffer` (6)
far more often than the fixed hand count could water/harvest, so the extra
plants died as weeds. The reserve *value* was never the actual problem -
nothing was capping *how many tiles get planted relative to hand count*,
and the original flat 1200 threshold had only ever prevented overplanting
as an accidental side effect of being too strict to trigger often.

**Attempt 2 - keep the reserve back at capital_reserve, but buy only 1 seed
at a time ("trickle") whenever the full-buffer purchase isn't affordable.**
`plants_weeded` dropped to near zero (0.05) - confirmed that piece of the
diagnosis. But `--compare` still came back **mean -156.1, 95% CI
[-209,-103], both tests p<0.0001, win rate 36.5%.** Turn-by-turn trace
(seed 89, the worst pair) showed money bleeding from 2393 (day 10) to 282
(day 19) - hand count fell from 8 to 5 over the same stretch as the hire
budget (`money * 0.05`) shrank along with it. Instrumented `_market_orders`
directly (temporary debug print, not committed) and confirmed: the trickle
condition was `want > 0`, and `_market_orders` runs every hour: as tiles
finish and clear, `want` goes positive again and the trickle can fire
several times a day, at $20/seed (CARROT). That's a real, uncapped
recurring cost the hire budget then has to compete with every single
morning - a much larger and more sustained drain than "one seed's worth,"
even though no single purchase looked wrong in isolation.

**Attempt 3 (adopted) - two independent mechanisms, not one shared reserve
value:**
1. `tiles_per_unit: 4` - cap `want` at `(1 + hands) * tiles_per_unit -
   (held seeds + planted tiles)`, independent of cash. This is what
   actually prevents overplanting; nothing about it depends on how strict
   the cash gate is.
2. Cash gate reverted to *exactly* the original all-or-nothing
   `capital_reserve` check for the normal case (unchanged from before this
   whole investigation). The only new branch: if we hold **zero** seed of
   the active crop (not "below buffer" - *zero*) and can afford one, buy
   exactly one. Rate-limited by construction: buying immediately makes the
   held-count nonzero, so it can't refire until that one seed is consumed.

Verification:
- `make test`: 95/95 green, including the new parametrized stress test
  (below) and the existing `test_no_extended_stall`.
- New trap line: **$20** (CARROT's seed cost - `_pick_crop` defaults to
  `crop_main` when neither crop has stock, so that's the true minimum
  purchase needed to ever escape). Confirmed by direct scan: $19 stalls
  (100% PASS the whole 240-turn episode), $20 works (64.6% worst window).
  Comfortably under the requested "well under $500."
- `--compare v1-early-capital-discipline` (48 seeds, 96 episodes): **mean
  +171.9, sd 63.2, se 6.45, 95% CI [+159.1, +184.7], paired t-test
  t=+26.657 p<0.0001, Wilcoxon z=+8.509 p<0.0001, win rate 100.0%,
  plants_weeded 0.000.** This isn't "does not regress" - v1 loses every
  single one of the 96 episodes. Clears the Task C acceptance bar (95% CI
  excludes zero, both tests agree, point estimate far past the ~50-coin
  floor) by a wide margin.

Verdict: ADOPTED.

Notes: this is the first real (non-self-play) use of the Task C paired-
differential tooling, and it earned its keep immediately - both failed
attempts would have looked like plausible, mergeable fixes under the old
"run make test, glance at win rate" workflow (test suite was green in both
cases; win rate alone would have been the headline number). The `--compare`
tool caught a -231 and a -156 coin regression that a win-rate-only check
at n=12 could easily have missed or misread as noise. Also: a comment
thread in `agent/main.py` now carries the history of what didn't work and
why for this exact code path - worth checking before touching
`_market_orders` step 3 again.
