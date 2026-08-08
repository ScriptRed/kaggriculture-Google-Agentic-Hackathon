# Economics

All figures below were derived from the environment source
(`kaggle_environments/envs/kaggriculture/kaggriculture.py`), not from the
competition page. Where the two disagree, the source wins.
`tests/test_constants.py` pins our tables to it.

> **ENGINE VERSION NOTICE (2026-08-08).** kaggle-environments 1.32.6
> (PR #1394) removed the town-centre demand schedule this whole
> "Correction (2026-08-07)" section was derived against - it used to
> double at day 10 and again at day 20 (1x -> 2x -> 4x); it is now a flat
> 1 unit/day, forever. Every dollar figure below that includes a town-
> centre component (marked inline) is **OLD ENGINE, HISTORICAL** - do not
> calibrate against it. The shop-only figures (the "shop component only"
> table) are unaffected - `townShopSellInterval`/`townShopUnlockInterval`
> did not change. See `docs/strategy-log.md` "ENGINE UPGRADE" for the
> full diff and verification, and `docs/target-plan.md` for the same
> caveat applied to the barnyard-census target plan.

## Correction (2026-08-07): sustainable revenue replaces yield x price

The previous version of this document ranked crops by
`yield/tile/day x base price` and put melon first at ~$137/tile/day, with
strawberry fifth at ~$29. **That ranking is wrong.** It modelled the price
penalty from *our own selling* but ignored the mechanism that makes selling
sustainable at all: the town **removes** stock every tick, which is what
regenerates the room to sell into. A crop nobody is buying has a `$/tile/day`
number that only exists for the first sale.

The corrected question is not "what does one unit sell for" but "how many
units/day can the market absorb before the price crashes" - i.e. sustainable
revenue = **town demand rate x base price**. `sustainable_rate(item, day)` in
`agent/constants.py` computes the demand side directly from the source.

### Where town demand comes from

Two independent consumers pull market inventory down (`_town_consume` in
kaggriculture.py):

- **Shops.** Every `townShopSellInterval` turns (default 4 -> 6 ticks/day),
  every *unlocked* shop consumes 1 of each product it sells (2 if it's a
  single-product shop). One new shop unlocks every `townShopUnlockInterval`
  days (default 3), chosen **uniformly at random** from the 8 shops in
  `SHOPS`, so by day 24 (8 x 3) all of them are open.
- **Town centre.** Every `townCenterSellInterval` turns (default 24 -> 1
  tick/day as of kaggle-environments 1.32.6; was 12 -> 2 ticks/day, see the
  notice above), it consumes 1 of *every* product except fertilizer - flat,
  no day-dependent multiplier anymore (`TOWN_CENTER_DEMAND_SCHEDULE`, which
  used to hold that multiplier, was removed from the engine and no longer
  exists in `agent/constants.py` either).

Both are transcribed verbatim (`SHOP_UNLOCK_INTERVAL`,
`SHOP_SELL_TICKS_PER_DAY`, `CENTER_SELL_TICKS_PER_DAY`,
`TOWN_CENTER_PRODUCTS`) and asserted equal to the source in
`test_town_center_products_match_env` /
`test_town_center_is_flat_one_per_day`.

**Which** shop unlocks on which day is random per episode, so a pure
`(item, day)` function can't know it exactly. But the unlock order is a
uniformly random permutation of the 8 shops (the source does sequential
`rng.choice` from the remaining set), so the probability a specific shop is
open by `day` is exactly `shops_unlocked_by_day(day) / 8` - an unbiased
expectation, not a guess. This was checked against a faithful re-simulation
of the env's own RNG-driven unlock code at 20,000 trials per data point and
matched to within Monte Carlo noise (see
`test_sustainable_rate_expected_mode_matches_monte_carlo_of_env_rng`); when
an actual episode is running, `sustainable_rate(item, day, unlocked_shops=
obs["town"]["unlocked_shops"])` uses the real set instead and is exact.

### Sustainable demand, shop component only (steady state, day >= 24)

This table matches the priors in `prompts/next.md` exactly - independently
re-derived here, not copied:

| Item | Shop demand/day | Base | Sustainable $/day |
|---|---:|---:|---:|
| **STRAWBERRY** | 24 | 120 | **2,880** |
| **MILK** | 18 | 160 | **2,880** |
| WOOL | 12 | 200 | 2,400 |
| WHEAT | 30 | 25 | 750 |
| TOMATO | 12 | 60 | 720 |
| CARROT | 18 | 35 | 630 |
| EGG | 12 | 50 | 600 |
| **MELON** | **0** | 250 | **0** |

No `SHOPS` entry lists melon (`test_melon_has_no_shop_demand`). Melon has
*zero* shop demand at any day, at any shop-unlock draw. This is the load-
bearing fact the old ranking missed entirely: it is not that melon's price
crashes fast (true, but secondary - see the `sq` glut shape below), it's
that **nothing in the shop layer ever buys melon**, so a melon harvest can
only be absorbed by the town centre.

### The town centre floor (applies to every item, including melon)

**OLD ENGINE, HISTORICAL - see the notice at the top of this file.** Prior
to 1.32.6, the centre added `2 -> 4 -> 8` units/day (day <10 / 10-19 /
>=20) of demand for every product except fertilizer:

| Day range | Melon centre demand/day (old) | Melon sustainable $/day (old) |
|---|---:|---:|
| 0-9 | 2 | 500 |
| 10-19 | 4 | 1,000 |
| 20-29 | 8 | 2,000 |

**Current (1.32.6+): flat 1 unit/day, every day** - melon sustainable
$/day is a flat **$250** (1 x base $250), season total 30 units vs the
old 140 (an 88.6% cut - see `docs/strategy-log.md` "ENGINE UPGRADE" and
"Task 1 (new engine): melon..."). Removed from the production plan
entirely as a result (`agent/main.py PARAMS["early_crop_target"]`), not
just repriced downward.

Two things made this worse than the headline dollar figure suggests, and
still do:

1. **It's shared with the opponent.** Both farms sell into the same market,
   so this is the *combined* sustainable rate, not per-player.
2. **Melon can't be harvested before day 10** (`first_yield_day: 10`), and a
   worked field produces far more than a day's demand at once - a batch of
   several tiles landing in the shed the same day floods the melon market
   instantly: `above_target` for melon is `3.60` with a **quadratic**
   (`sq`) shape, the steepest crash curve of any product. The old doc's
   "melon trap" observation was directionally right but underpriced even
   before the engine change - melon isn't merely glut-prone, its buyer
   base is one thin, shared, day-gated channel, now four times thinner
   again on top of that.

Wheat and eggs sit at the other extreme: high shop demand (30/day, 12/day)
*and* the gentlest glut curve (`log`, target 0.20) - they're the only two
items designed to absorb volume, matching the old doc's observation, now on
firmer ground because it's derived from removal-rate rather than curve shape
alone.

### Reading the ranking

Strawberry and milk are tied for the top sustainable rate ($2,880/day
combined-market), wool close behind at $2,400. All three are still
`sq`/`linear` glut-prone at the per-sale level (see `MARKET_PARAMS`) - the
sustainable rate is the ceiling the town's removal supports, not a
guarantee that dumping a whole harvest at once is free. The practical
reading is: **strawberry and milk are the highest-value crops that also
have a real buyer base**, wool is a strong third, and melon's paper yield
value is close to fictional once its actual buyer (town centre only, ramps
by day, shared with the opponent) is priced in.

## Cross-check against public notebooks

Per `prompts/next.md`, checked against three independent sources.

- **`what-every-crop-pays`** (Georgy Mamarin) reaches the same qualitative
  conclusion by a different route: "no shop ever buys melon or fertilizer,
  and the town center skips fertilizer too - so fertilizer has no town
  demand at all, while melon hangs on the town center alone, which makes
  its price the most fragile in the game." It also independently confirms
  melon's oversupply curve is quadratic, wheat/egg "absorb hundreds of
  units and barely move," and sales at the $1 floor don't add to market
  inventory (all already reflected in `constants.sale_proceeds`). This
  notebook doesn't compute a demand-rate table, but every qualitative claim
  it makes agrees with the derivation above. **Corroborates.**
- **`structured-economic-policy`** contains a working agent with a
  `_town_demand_per_day(obs, item)` function. Transcribed (**OLD ENGINE,
  HISTORICAL** - the `center` term below used the pre-1.32.6 day-10/day-20
  doubling and is now wrong; the `shop` term is unaffected and still
  correct today):
  `center = 0 if item=="FERTILIZER" else 2*(4 if day>=20 else 2 if day>=10
  else 1)`, `shop = sum(12 if single-product else 6 for unlocked shops
  selling item)`. This was **the same formula** as ours at the time,
  derived independently, down to the per-tick constants (their 12/6 = our
  `SHOP_SELL_TICKS_PER_DAY (6) x _shop_unit_rate (2 or 1)`). It reads
  `obs["town"]["unlocked_shops"]` live rather than modelling the
  unlock-day expectation, which is exactly the distinction
  `sustainable_rate`'s `unlocked_shops` parameter captures.
  **Corroborated at the time** (matched at the code level, not just the
  conclusion) - this notebook's own published agent is now stale in the
  same way our pre-upgrade code was, for the same reason.
- **`moon-counts-melons`**: despite the name, this notebook is **not** about
  crop economics. It's a mirror/opponent-detection routing scheme (delay a
  market counterfactual until 4 shops are visible, branch on the visible
  shop profile and money gap). It contains no crop-ranking or demand-rate
  content to check against Task 1. Flagging this rather than silently
  skipping it, per "if any instruction here rests on a mistaken premise, say
  so." It *is* relevant to Task 5 (mirror opportunity) and is cited there
  instead.

No disagreement surfaced between the three sources or the source code on
any economics point in this section.

## Watering: the alternate-day discovery

From `_daily_refresh_plants`: a plant weeds when `consecutive_unwatered >= 2`,
and watering resets it to 0. A new plant starts at **1**, so it must be watered
on its planting day or it dies that night.

After that, watering every *other* day keeps it alive. Watering only adds yield
inside the bonus window - ages `(max_yield_day+1)//2` through `max_yield_day`
for one-time crops. Outside that window watering is pure survival overhead and
can be halved.

| Crop | First yield | Bonus window (age) | Max unfert | Max fert |
|---|---|---|---|---|
| Wheat | 2 | 2-4 | 4 | 6 |
| Carrot | 2 | 2-3 | 3 | 4 |
| Melon | 10 | 6-12 | **6 (capped)** | 6 |
| Tomato | 8 | n/a (ongoing) | 4 productions | 2x on watered+fert days |
| Strawberry | 10 | n/a (ongoing) | 4 productions | 2x on watered+fert days |

**Fertilizer on melon is wasted** - it reaches the cap of 6 unfertilized (at
age 10; fertilized just gets there by age 8). Wheat and carrot genuinely need
it to hit their listed maximum. Pinned by
`test_melon_needs_no_fertilizer`.

## Fertilizer is the best action in the game

From `_daily_refresh_animals`: every surviving animal sets
`fertilizer_available = True` at end of day **regardless of whether it was fed
or cared for**. `COLLECT_FERTILIZER` is one action for one unit worth $100 base
- and now we can say precisely how sustainable that $100 is: fertilizer has
**zero** town demand (`TOWN_CENTER_PRODUCTS` excludes it and no shop lists
it), so it lives entirely on its own glut curve (`linear`, 0.40 - mild, but
with no removal mechanism at all, every unit sold permanently uses up glut
room until the opponent or a purchase buys it back).

Nothing else pays that per action, but "the best action in the game" claim
in the old doc should be read as *marginal-action-value*, not
*infinitely sustainable* - fertilizer's price has no demand-side floor.

## Land

Order is **fixed** in the source: `LAND_ORDER = ["NE", "SW", "SE"]` at
$1,000 / $2,000 / $4,000. You do not choose which quadrant. Note the first hand
of each day spawns at (5,4), which sits in NE and is locked until you buy it -
passable, but a wasted move every morning until then.

Against a $3,000 start, buying NE immediately is a real capital decision, and
the current baseline gets this wrong (see strategy-log).

## Actions are the binding constraint

Not money, not land. One farmer gets 24 actions/day. A full 10x10 board is 100
tiles, each needing watering and harvesting.

Hire cost is `fib(n)` for the n-th hire *that day*, reset daily:

| Hands | Cumulative cost | Extra actions/day | Cost per action |
|---|---|---|---|
| 5 | 12 | 120 | 0.10 |
| 8 | 54 | 192 | 0.28 |
| 10 | 143 | 240 | 0.60 |
| 12 | 375 | 288 | 1.30 |
| 15 | 1,596 | 360 | 4.43 |

Against sustainable revenue of $600-2,880/day per crop (see above), hands are
close to free up to ~10/day and still cheap at 12. Any agent not hiring hard
is leaving most of the board idle. Watch `idle_tile_rate` in the arena output.

## Adversarial angle

Ratings are win/loss only, margin ignored. You share a market with your
opponent and can see their tiles. Dumping the product they are about to harvest
crashes it to $1 for both of you - cheap sabotage that costs you little if you
are not invested in that good. Most submissions will be pure solo-optimisers
with no defence. See `docs/meta-analysis.md` for the mirror-detection angle.
