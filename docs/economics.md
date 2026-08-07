# Economics

All figures below were derived from the environment source
(`kaggle_environments/envs/kaggriculture/kaggriculture.py`), not from the
competition page. Where the two disagree, the source wins.
`tests/test_constants.py` pins our tables to it.

## Revenue density (gross, ignoring price impact)

| Item | Yield/tile/day | Base | $/tile/day | Glut resistance |
|---|---|---|---|---|
| Melon | 0.55 | 250 | **137** | terrible — `sq`, target 3.60 |
| Cow / Milk | 0.50 | 160 | 80 | bad — `linear`, 1.60 |
| Sheep / Wool | 0.33 | 200 | 66 | terrible — `sq`, 3.20 |
| Goose / Egg | 1.00 | 50 | 50 | **excellent** — `log`, 0.20 |
| Strawberry | 0.24 | 120 | 29 | terrible — `linear`, 1.60 |
| Carrot | 0.75 | 35 | 26 | poor — `sqrt`, 0.70 |
| Wheat | 0.80 | 25 | 20 | **excellent** — `log`, 0.20 |
| Tomato | 0.33 | 60 | 20 | medium — `sqrt`, 0.60 |

**The melon trap.** `T` is defined in the source as one 5×5 field's output over
24 days. Melon's `above_target` is 3.60 with a squared shape, so selling ~T
melons takes the price from $250 to the $1 floor. Fill a quadrant with melons
and you personally destroy your own price. Every premium good (melon,
strawberry, milk, wool) shares this. Wheat and eggs are the only items that
absorb volume: at I0+2T wheat still fetches $19 of its $25 base.

Consequence: the objective is **portfolio allocation under self-inflicted price
impact**, not "plant the most valuable crop". `constants.sale_proceeds()`
replicates the curve exactly so the policy can price its own dumping.

## Actions are the binding constraint

Not money, not land. One farmer gets 24 actions/day. A full 10×10 board is 100
tiles, each needing watering and harvesting.

Hire cost is `fib(n)` for the n-th hire *that day*, reset daily:

| Hands | Cumulative cost | Extra actions/day | Cost per action |
|---|---|---|---|
| 5 | 12 | 120 | 0.10 |
| 8 | 54 | 192 | 0.28 |
| 10 | 143 | 240 | 0.60 |
| 12 | 375 | 288 | 1.30 |
| 15 | 1,596 | 360 | 4.43 |

Against crops worth $25–250 a unit, hands are close to free up to ~10/day and
still cheap at 12. Any agent not hiring hard is leaving most of the board idle.
Watch `idle_tile_rate` in the arena output.

## Watering: the alternate-day discovery

From `_daily_refresh_plants`: a plant weeds when `consecutive_unwatered >= 2`,
and watering resets it to 0. A new plant starts at **1**, so it must be watered
on its planting day or it dies that night.

After that, watering every *other* day keeps it alive. Watering only adds yield
inside the bonus window — ages `(max_yield_day+1)//2` through `max_yield_day`
for one-time crops. Outside that window watering is pure survival overhead and
can be halved.

| Crop | First yield | Bonus window (age) | Max unfert | Max fert |
|---|---|---|---|---|
| Wheat | 2 | 2–4 | 4 | 6 |
| Carrot | 2 | 2–3 | 3 | 4 |
| Melon | 10 | 6–12 | **6 (capped)** | 6 |
| Tomato | 8 | n/a (ongoing) | 4 productions | 2× on watered+fert days |
| Strawberry | 10 | n/a (ongoing) | 4 productions | 2× on watered+fert days |

**Fertilizer on melon is wasted** — it reaches the cap of 6 unfertilized (at
age 10; fertilized just gets there by age 8). Wheat and carrot genuinely need
it to hit their listed maximum. Pinned by
`test_melon_needs_no_fertilizer`.

## Fertilizer is the best action in the game

From `_daily_refresh_animals`: every surviving animal sets
`fertilizer_available = True` at end of day **regardless of whether it was fed
or cared for**. `COLLECT_FERTILIZER` is one action for one unit worth $100 base
with mild glut decay (`linear`, 0.40 — still $60 at I0+T).

Nothing else pays that per action. A pasture of animals is a fertilizer mine
that happens to also produce milk.

## Land

Order is **fixed** in the source: `LAND_ORDER = ["NE", "SW", "SE"]` at
$1,000 / $2,000 / $4,000. You do not choose which quadrant. Note the first hand
of each day spawns at (5,4), which sits in NE and is locked until you buy it —
passable, but a wasted move every morning until then.

Against a $3,000 start, buying NE immediately is a real capital decision, and
the current baseline gets this wrong (see strategy-log).

## Town demand

Shops unlock every 3 days, chosen randomly from the eight, each consuming one
of every product it wants every 4 turns (6/day; single-product shops double).
The town centre consumes one of everything every 12 turns, doubling after day
10 and quadrupling after day 20.

Demand therefore grows monotonically and prices trend up late — but the shed
caps at 100 items with overflow **discarded**, so you cannot simply hoard for
the day-20 spike. Timing sales into the late window is worth modelling; naive
stockpiling just throws produce away.

## Adversarial angle

Ratings are win/loss only, margin ignored. You share a market with your
opponent and can see their tiles. Dumping the product they are about to harvest
crashes it to $1 for both of you — cheap sabotage that costs you little if you
are not invested in that good. Most submissions will be pure solo-optimisers
with no defence. Untested; see strategy-log for status.
