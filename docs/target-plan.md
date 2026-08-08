# Target production plan

> **ENGINE VERSION NOTICE (2026-08-08, second update).** kaggle-environments
> 1.32.6 (PR #1394) removed the town-centre demand schedule this entire
> document - including the "superseded by real ladder data" update directly
> below, and the $115,664 ladder-median / $195-202k route figures throughout
> - was built against. Melon's season-long town demand alone dropped from
> ~140 units to 30 (see `docs/strategy-log.md` "ENGINE UPGRADE"), and melon
> has been removed from the production plan entirely as a result (not
> merely bounded, as this doc's own "12-tile burst" recommendation says
> below). **Every dollar figure and every crop/animal target number in this
> file is OLD ENGINE, HISTORICAL.** Do not calibrate against it or treat it
> as a current target - kept for its still-relevant methodology (evidence-
> quality grading, the gap-analysis structure) and as a record of what the
> pre-upgrade meta looked like. A new-engine equivalent does not exist yet
> (Task 2, `docs/strategy-log.md`, is the live-shop-reading response to
> this same engine change).

## 2026-08-08 update: superseded by real ladder data (notebooks/live-meta)

Everything below this note was built from a **single recorded route**
(barnyard-economist, itself unexecuted - see the evidence-quality table).
`notebooks/live-meta` turned out to contain more than the byte-identical
duplicate of `frontier-lab-high-score` flagged below - its "8.5 Daily Meta
Report" section (cell 28) is a **683-episode/1,366-player** real-ladder
snapshot, not a single route. Read the notebook in full (not just sampled,
as this doc originally did) and every specific claim checked against it
matched verbatim. What we could independently verify:

- **The engine-version calibration is real and confirmed.** The notebook's
  own four premium price cliffs (strawberry 62, wool 59, milk 76, melon
  158 units to the $1 floor) match our installed `kaggle-environments`
  1.32.5 exactly - now a permanent regression test
  (`tests/test_constants.py::test_premium_price_cliffs_match_notebook_reference`).
- **The "pure-animal farms" reading of its own data is wrong, and we can
  prove it from our own replays, not just the notebook's numbers**
  (Task 5a): `crops={}` in the notebook's own final-board tally is the
  state at turn 720, after early one-time crops (wheat, melon) have long
  since been harvested and ongoing crops (strawberry) have decayed past
  their 4-production cap - it does not mean crops were never grown. Direct
  proof from `replays/*.json`: "Ak", our single highest-scoring real
  opponent ($62,271, first flagged in this doc's original gap analysis
  below), bought 9 wheat + 7 melon seed in days 0-4 and still finished
  with `final_crops={}`. "dejavucry" (episode 90750259, $13,588) shows the
  identical pattern (6 wheat + 8 melon early, empty final board). Two for
  two among the real replay opponents that show any early crop activity at
  all.
- **The "5 hands, fib makes the 7th unaffordable" reading is also wrong**
  (Task 5b): 7 hires cost `fib(0)+...+fib(6) = 33` coins total, against a
  **$21,272 median day-15 bank** in the same dataset - not remotely a
  binding constraint. The notebook's own trend table shows the modal hand
  count going 12 -> 12 -> 5 across three consecutive days, which it
  flags itself as "a real meta shift or a data anomaly - verify with the
  next snapshot." `PARAMS["target_hands"]` was **not** retuned down on the
  strength of this reading.

**Corrected target, implemented on `strat/animal-first-meta`:** COW:8 +
SHEEP:6 (no geese - 1 of 1,366 players ever sold an egg), bought from day
0; wheat (~14) and melon (~12) as a bounded one-time early batch, not an
ongoing crop program (no carrot/tomato - 37 and 1 of 1,366 players
respectively, noise not meta); fertilizer sold aggressively from day ~2
as a first-mover revenue line (finite, non-regenerating, opponent-shared
pool - zero shop or town-centre demand, `docs/economics.md`); land NE
then SW, never the $4,000 SE quadrant; sales metered to
`sustainable_rate()`-derived town absorption instead of a flat batch cap.
No strawberry this round - the dominant modal composition (86% of the
notebook's own top-5 cluster) is pure animal with zero surviving crops;
strawberry only appears in the minority (~2.5%) compositions.

**Measured**: paired against `route-proxy` (the barnyard-economist-derived
yardstick this doc's original analysis was used to build), mean **+33,938**
coins/game (95% CI [+32,276, +35,601], t-test and Wilcoxon agree, **100%**
win rate, n=96). Full results, the feed-chain engineering this required,
and the residual `animals_lost` gap are in `docs/strategy-log.md`. The
original barnyard-economist-derived analysis below is kept for its
still-relevant methodology notes (evidence-quality grading, the PASS-slot
finding, the closed-loop cross-check) but its specific target numbers
(12 melon / 7 wheat / strawberry-ramp / land-timing-as-open-question) are
superseded by the above.

---

Extracted from `barnyard-economist`, cross-checked against `kaito-v18-closed-loop`,
`kaito-v21-conditional-memory`, `kaito-v22-price-impact`, `live-meta`, and our
own 7 real ladder replays in `replays/`. Read `docs/economics.md` first - the
gap analysis below leans on the corrected sustainable-revenue model.

## Evidence quality, up front

This matters more than usual here, because most of these sources turned out
to be weaker than their length suggests:

| Source | What it actually is | Executed evidence? |
|---|---|---|
| `barnyard-economist` | Day-by-day route table + a real experiment (PASS-slot filling) | **No.** Every code cell has `execution_count: None`, zero saved outputs. All numbers are prose/markdown claims, not reproducible from the file. |
| `kaito-v18-closed-loop` | Win-rate table from counterfactual replay | **No.** Same - zero saved outputs. Also: zero references to `kaggle_environments`/`make`/`env.run` anywhere in the file - it never executes a live episode, only replays recorded opponent trajectories that "cannot react to our counterfactual actions" (its own words). Same evidentiary category as v13-r3's numbers per the credibility weighting in the task brief: mechanism plausible, scoreline unverified. |
| `kaito-v21-conditional-memory`, `kaito-v22-price-impact` | Order-timing/mirror-detection papers bolted onto **someone else's** route | Discloses no production-plan numbers at all - see below. |
| `live-meta` | Claims to compute "top farm" stats from a live Kaggle dataset mount | **Byte-identical to `frontier-lab-high-score`** (`md5sum` confirms), which the task brief already flags as suspect (validation cell claims final bank 55 against a stated 2,000 starting money vs the real 3,000 default). We could not independently confirm that specific anomaly - neither copy has any saved cell outputs either - but structurally: it requires `/kaggle/input/datasets/...` which isn't present, its "8.5 Daily Meta Report" section is numbers typed into markdown prose rather than generated by code, and it is **not a second source**, it is the same file under two names. |
| `replays/*.json` (7 games) | **Real, executed ladder episodes**, `module_version 1.32.5` matching our installed engine exactly | **Yes.** The only source in this list with verified numbers. See `docs/ladder-observations.md`. |

None of this means the notebooks are worthless - the mechanisms they describe
are independently checkable against source (and mostly check out, per
`docs/meta-analysis.md`) - but **every specific number below from a notebook
is a claim, not a measurement**, except where our own replays confirm the
shape independently.

## The barnyard-economist route (verified against the notebook's own table, corrected)

The brief's summary was accurate but incomplete - the actual table has two
more rows and dollar figures for the "frozen" days that the summary dropped:

```
d00  $3,000                                                   25 empty, 75 locked
d03  $187      12 melon,  7 wheat,                2 cow, 2 sheep   (2 pens)
d06  $972      12 melon,  7 wheat,                4 cow, 2 sheep
d09  $2,848    12 melon,  7 wheat, 12 strawberry,  6 cow, 4 sheep
d12  $14,602   12 melon,  7 wheat, 39 strawberry,  8 cow, 6 sheep
d15  $26,964   12 melon,  7 wheat, 42 strawberry,  8 cow, 6 sheep   <- steady state reached
d21  $66,179   12 melon,  7 wheat, 42 strawberry,  8 cow, 6 sheep   <- unchanged, "frozen"
d24  $114,962             19 wheat, 37 strawberry, 8 cow, 6 sheep   <- melon gone
d27  $154,076             35 wheat, 23 strawberry, 8 cow, 6 sheep
final ~$195-202k (two run/seed figures given, both in that range)

hands: 1 (d05) -> 8 (d10) -> 13 (d15) -> 14 (d20-25) -> 6 (d29)
land: exactly two extra quadrants, never the $4,000 SE one
```

This is coherent with, and now explains the mechanism behind, `docs/
economics.md`'s corrected demand model: 12 melon tiles is a **bounded** early
burst (roughly what one field's initial batch supports before the
zero-shop-demand ceiling bites), wound down entirely by day 24 once the
window closes, with the freed capital and action budget redirected into
strawberry (top of the corrected sustainable-revenue ranking) and wheat
(also strong, and glut-resistant, so a good place to land once melon is
gone). The 8-cow/6-sheep herd is built once (by d12) and then never grows -
consistent with animal products also sitting near the top of the sustainable
ranking (`docs/economics.md`), reaching a level the town can actually absorb
and staying there rather than continuing to scale into a saturated market.

## Cross-check results

**Confirms barnyard-economist's PASS-slot finding, doesn't confirm its
route table.** The "recordings can't be locally improved" result (Task 3)
is stated with specific numbers in the notebook: 812 of ~6,000 worker-
actions are `PASS` (13%); filling them with any in-place action scored
116,113 vs the unmodified route's 124,798 (**-8,685**, brief said "~8,700",
confirmed close); the cause is opportunistic `HARVEST` destroying one-time
crops (melon) before max yield; dropping `HARVEST` and keeping
`WATER`/`FEED`/`CARE`/`COLLECT_FERTILIZER`/`DIG` produced a byte-identical
tie on every seed. All of this is *prose in an unexecuted notebook*, same
caveat as above.

**kaito-v18-closed-loop discloses no production numbers to compare.**
It reports win-rate splits (44/49 train -> 40/53 future holdout, vs v17's
5/49 -> 3/53), never a bank total or crop/animal census, so it cannot
confirm or contradict the melon-wind-down / strawberry-ramp / 8-cow-6-sheep
shape above. What it does confirm, structurally: **its own farmer/hand
build trajectory is a single fixed recording, identical across all four of
its market "experts" until turn 632**, and the board-route gate that could
have made it fully closed-loop ships *disabled*
(`board_distance_strength = 0.0`) in the published artifact. In other
words: even the one notebook the task brief called "closed-loop" runs the
same *kind* of fixed field-work recording as barnyard-economist underneath
- only its market/sell/buy/hire layer reacts live. See
`docs/architecture-notes.md` for what that buys.

**kaito-v21 and kaito-v22 are not production-plan sources at all.** Both
take someone else's recorded 719-action route as a black box and only
reorder its *already-decided* market orders - v21 by predicting an
opponent's sells via nearest-neighbor route-matching and moving colliding
sells earlier (never inventing new sells: an earlier prototype that did
invent early sells from the same prediction caused "performance collapse",
per its own ablation - see `docs/meta-analysis.md` follow-on and the Task 5
doc), v22 by ranking sell slots by self-price-impact. Neither states a tile
count, animal count, hand curve, or land day anywhere in its text. They
have nothing to agree or disagree with here.

**live-meta**, treated per the caveats above, claims a modal top farm of
"8 cow + 6 sheep [+ 6-7 strawberry], NE+SW land, no melon" (its own words,
unverifiable execution). The *shape* - not the specific numbers - matches
barnyard-economist's steady state (8 cow, 6 sheep, strawberry-heavy, two
land purchases) closely enough to be a real point of agreement between two
otherwise-independent claims, even though neither is independently
verifiable on its own.

**Our own replays are where a claim actually gets tested, and they partly
disagree.** From `docs/ladder-observations.md` (7 real games, our engine
version exactly):

- The single highest-scoring opponent we've faced (62,271 final bank) ran
  **13 animals (5 goose, 7 cow, 1 sheep) and bought zero extra land** -
  finished the game on the free NW quadrant only. This is a real,
  *measured* disagreement with barnyard-economist's "always buy exactly two
  quadrants" claim: at least one real, strong ladder agent wins big without
  buying any land at all. It's plausible both are locally optimal
  (barnyard-economist's own route needs the land to have the tile count to
  support 12+7+42 crop tiles and two pastures; a 13-animal-only farm might
  fit inside NW alone) rather than a contradiction, but it's a genuine
  open question, not something to resolve by assumption.
- Two of the three next-best opponents (42,673 and 34,248) ran
  melon-heavy, water-disciplined farms (17 and 25 melon tiles) - good, but
  well short of the animal-heavy leader and far short of
  barnyard-economist's claimed ~195-202k ceiling. This is consistent with
  Task 1's finding that melon has zero shop demand: an *unbounded* melon
  holding (17-25 tiles, uncapped) outperforms doing nothing, but
  underperforms a bounded melon burst redirected into animals/strawberry
  once the town-centre-only demand ceiling is reached - exactly what
  barnyard-economist's route does (12 tiles, wound down by day 24) and
  what these two real opponents don't.
- No opponent in our 7-game sample matches barnyard-economist's specific
  route closely enough to call it "the meta" rather than "a strong
  strategy among several" - the strongest real opponent we've actually
  played is animal-heavy-no-land, not melon-then-strawberry-with-land.

## Gap analysis against our current agent

Current `agent/main.py` (`PARAMS`, `_pick_crop`, `agent/constants.py`):

| Dimension | Current agent | Target-plan consensus | Real-replay evidence |
|---|---|---|---|
| Crops planted | `_pick_crop` only ever returns `WHEAT` or `CARROT` - **melon and strawberry are never planted, at all** | Melon early (bounded, ~12 tiles), strawberry ramping to ~40+ once shops open | Both the animal-heavy winner and the melon-heavy runners-up beat us; we run neither |
| Animals | `animal_target = {GOOSE: 4, COW: 2, SHEEP: 1}` (7 total), gated `day >= 10-12` | 8 cow + 6 sheep (14), reached by d12 | The 62,271 opponent ran 13 (5 goose/7 cow/1 sheep) - closer to the target-plan's animal count than we are, in a different mix |
| Hands | `target_hands = 8`, flat for the whole game | Ramps 1 -> 8 -> 13 -> 14 -> 6 (day-dependent) | Not directly measured in our replay sample, but every winning pattern we've seen assumes far more actions/day than a flat 8 |
| Land | `land_buy_min_day = 10`, gated by `capital_reserve = 1200`, no hard cap on quadrant count (up to all 3 if cash allows) | Exactly 2 quadrants, never the $4,000 SE one | Contradicted by our own strongest opponent (0 land, animal-only) - open question, not settled |
| Sell ordering | Sorted by `-qty` (largest quantity first) | Not specified by barnyard-economist; v22 and `structured-economic-policy` both independently argue for ranking by self-price-impact instead | Out of scope for this doc - tracked as an open item in `docs/meta-analysis.md`, addressed operationally in Task 4 |

**Ranked by what's actually measured, not intuition:**

1. **We plant neither melon nor strawberry, ever.** This is the largest,
   most certain gap: it's true by direct code inspection (`_pick_crop`
   never returns either), it's consistent across every source in this
   review regardless of credibility tier, and it's independently confirmed
   by real replay evidence (both winning patterns we've actually lost to
   use one or the other). Note the corrected economics: melon should be
   **bounded and wound down**, not season-long - planting it the way
   `melon-rush` (our own arena opponent) does, unboundedly, is *not* the
   target; barnyard-economist's 12-tile-then-pivot-to-strawberry shape is.
2. **Our animal target (7) is roughly half the real-replay winner's (13)
   and half barnyard-economist's (14).** Measured against a real opponent,
   not just a notebook claim.
3. **Land timing/quantity is a genuine open question, not a settled
   target.** barnyard-economist says "always exactly 2, never the $4,000
   one"; our own strongest real opponent says "0, and win anyway." This
   needs its own measured experiment (arena `--compare`, land-quantity as
   the sole variable) rather than adopting either claim by authority - it
   is explicitly flagged here as unresolved rather than folded into a
   branch plan.
4. **Hand count is flat where every source (claimed or measured) says it
   should ramp.** Lowest-confidence item in this list only because we have
   no real-replay hand-count data point to anchor it, but directionally
   unanimous across every source.

## What this doc does not do

Per the task ordering, this is analysis only - no `agent/` changes here.
The recommended next branch, given this gap analysis and Task 1's corrected
economics, is adding melon (bounded, wound down) and strawberry as
crop options with day-dependent selection, and lifting the animal target
toward the real-replay-confirmed range - each as its own measured branch,
one hypothesis at a time, per the standing rule.
