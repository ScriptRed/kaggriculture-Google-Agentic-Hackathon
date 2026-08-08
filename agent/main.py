"""Kaggriculture agent - baseline v0.

Strategy in one paragraph: actions are the binding constraint, so hire hands
aggressively and keep every unit busy. Each turn we build a list of tasks
(harvest, rescue-water, bonus-water, plant, collect fertilizer, feed, care),
score them, and greedily assign units to the highest-scoring reachable task.
Selling is price-impact aware: we only sell down to a floor fraction of base,
and drip-feed premium goods rather than dumping.

This is deliberately simple. It exists to be beaten. See docs/strategy-log.md.
"""

import os
import sys

# The env (and the Kaggle runner) load this file standalone, not as a package,
# so its own directory is not on sys.path. Put it there before importing.
# NOTE: the env exec's this file with empty globals, so __file__ may not exist.
_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else None
for _p in (_HERE, "/kaggle_simulations/agent", os.getcwd()):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

# Absolute import only. A relative import raises KeyError under the env's
# exec() (there is no __name__ in globals), and the except clause will not
# save you. Submissions are flat: main.py and constants.py side by side.
from constants import (  # noqa: E402
    CROPS, ANIMALS, MOVES, LAND_PRICES, MARKET_PARAMS,
    market_price, marginal_price_after, bonus_window, harvest_age,
    hire_cost, cumulative_hire_cost, sustainable_rate,
)

PASS = ["PASS"]

# --- tunables. these are the knobs the arena optimises. -------------------
PARAMS = {
    # target_hands is intentionally NOT retuned here. notebooks/live-meta's
    # own "5 hands because fib makes the 7th unaffordable" reading of its
    # data is wrong (7 hires cost $33 total against a $21,272 median day-15
    # bank - trivially affordable; its own trend table shows 12->12->5 in
    # three days, which it flags as possibly anomalous, and its hand count
    # is measured at the wound-down final step, day 29) - see docs/
    # strategy-log.md. Left at 8 on purpose.
    "target_hands": 8,          # hands to hire each morning
    "hand_budget_frac": 0.05,   # ...but never spend more than this of bank
    "sell_floor_frac": 0.65,    # price floor for one-time-harvest sells
                                 # (WHEAT) and a safety net under the
                                 # absorption-metered ongoing sells (MILK/
                                 # WOOL) - see _sell_plan.
    "seed_buffer": 6,           # keep this many seeds of the active early crop
    "seed_trickle_cap": 3,      # small top-up ceiling when the full buffer
                                 # purchase isn't affordable - see step 4.
    "capital_reserve": 1200,    # cash floor for land/animal/seed spend
    "tiles_per_unit": 4,        # cap on simultaneous plants+held-seed per
                                 # farmer/hand - see _market_orders step 3.
                                 # capital_reserve alone used to be the only
                                 # thing preventing overplanting, as a side
                                 # effect of being strict about cash; loosen
                                 # the cash side (needed to fix the deadlock
                                 # below) without this and the hand count
                                 # can't keep up with the resulting plants -
                                 # tried it, cost -231/-260 coins paired vs
                                 # v1 (see docs/strategy-log.md).
    "land_buy_min_day": 5,      # notebooks/live-meta: real median first-land
                                 # ORDER day is 7, but that's the outcome of
                                 # cash naturally reaching ~$1,000 by then,
                                 # not a rule to hard-code - gate opens at 5
                                 # so revenue (fertilizer from ~day 2, the
                                 # wheat harvest) has a few days'
                                 # head start before land competes for the
                                 # same cash, then let affordability (see
                                 # _reserve()) decide the actual day.
    "land_quadrants_target": 2,  # NE then SW, never the $4,000 SE one -
                                 # notebooks/live-meta: 0% of top compositions
                                 # own it.
    # Early crop target (notebooks/live-meta §6/8.5, 683 episodes/1,366
    # players): "early seeds avg wheat 14.0, melon 11.6 per player over
    # days 0-4" - a bounded, one-time opening batch, not an ongoing crop
    # program (see _pick_crop - gap-based, no hard day cutoff). No carrot
    # (37/1366 players) or tomato (1/1366) - noise, not meta. No
    # strawberry this branch - the *dominant* modal composition (86% of
    # the top-5 cluster) is pure animal with zero surviving crops;
    # strawberry only appears in minority (~2.5%) compositions and isn't
    # asked for here - see docs/strategy-log.md for the full reasoning.
    #
    # MELON removed entirely (2026-08-08, kaggle-environments 1.32.6):
    # melon has zero shop demand (no SHOPS entry lists it) and lived
    # entirely on the town centre, which the engine upgrade cut from
    # ~140 units/season absorption to 30 (the old day-10/day-20 demand
    # doubling is gone - flat 1/day now, confirmed against a real
    # episode, see tests/test_constants.py). The live-meta target of 12
    # melon tiles/player (~72 units at max yield, 144 combined with an
    # opponent who shares the same market) already oversupplied the old
    # 140-unit season absorption; against 30 it's catastrophic. We were
    # already only reaching 3/12 tiles in practice (docs/strategy-log.md,
    # Task 1 seed-buying priority competition) - not worth fixing that
    # competition now that the crop it was competing with WHEAT for is
    # actively harmful to plant at all.
    "early_crop_target": {"WHEAT": 14},
    # Herd: every one of the top-5 compositions (1,366 players) is exactly
    # COW:8, SHEEP:6, first bought day 0 - no exceptions, and only 1 of
    # 1,366 players ever sold an egg. Geese dropped entirely.
    "animal_target": {"COW": 8, "SHEEP": 6},
    "animal_buy_min_day": {"COW": 0, "SHEEP": 0},
    # Fertilizer is a primary revenue line, not a crop-support reserve (we
    # don't fertilize crops here - FERTILIZE stays unexercised, tracked in
    # tests/test_invariants.py::KNOWN_UNCOVERED). It has zero shop demand
    # and is excluded from town-centre consumption (docs/economics.md) -
    # the ~493-unit pool to the $1 floor never regenerates and is shared
    # with the opponent, so every unit held back is a unit the opponent
    # can sell into the good early prices instead. Sell all of it, always.
    "fert_reserve": 0,
    # Unsold shed inventory doesn't count toward the final score (reward is
    # money only - kaggriculture.json). From this day on, drop the price
    # floor, the fertilizer/wheat reserves, and the metering caps and
    # sell down to zero every turn: a $1-floor sale still beats a stranded
    # unit worth exactly $0 at the final whistle. Two days of lead time -
    # plenty, since a terminal SELL has no per-order quantity cap and the
    # whole shed (<=100 items) clears in one turn once the caps are off.
    "liquidation_day": 28,
    # Construction-phase capital gate (target-plan Task 1, prior session).
    # Applied to BUY_LAND/BUY_ANIMAL only (see _reserve()) - NOT to the
    # seed-buffer purchase in step 3, which keeps PARAMS["capital_reserve"]
    # unconditionally. capital_reserve turned out to also be pacing how
    # fast the seed buffer could refill relative to actual watering
    # throughput, which tiles_per_unit alone doesn't constrain once hand
    # count is nontrivial - see docs/strategy-log.md, "phase-aware capital
    # gate", for the measured regression this split fixes.
    "construction_end_day": 22,
    "capital_reserve_construction": 0,
}


def _reserve(day):
    """Cash floor for land/animal/seed spend - see construction_end_day."""
    if day < PARAMS["construction_end_day"]:
        return PARAMS["capital_reserve_construction"]
    return PARAMS["capital_reserve"]


# Task 3 (target-plan rebuild, notebooks/live-meta): sell metering splits
# by market shape, not a flat premium/staple batch cap.
#
# ONGOING_SELL: animals produce these every few days for the rest of the
# game - a real, regenerating demand exists (sustainable_rate(), Task 1's
# sustainable-revenue work), so meter to it: sell up to a share of daily
# town absorption, spread across the day, rather than dumping a flat batch.
#
# One-time-harvest items (WHEAT here - see early_crop_target) get no
# metering cap at all: they're a fixed quantity from a bounded early
# planting window, not a flow to protect over the rest of the season -
# `sustainable_rate` doesn't even apply (there's no "next batch" whose
# price this game's selling needs to preserve). Sold at whatever quantity
# the existing price-floor check allows.
#
# FERTILIZER is neither: `sustainable_rate("FERTILIZER", day)` is
# structurally 0 (no shop entry, excluded from TOWN_CENTER_PRODUCTS -
# docs/economics.md) because nothing regenerates its market - it's a
# ~493-unit pool to the floor, shared with the opponent, only ever drained.
# Metering it to a demand rate of zero would mean never selling it, which
# is backwards: the right move is first-mover, not conservation - see
# fert_reserve=0 and the dedicated branch below.
ONGOING_SELL = {"MILK", "WOOL"}


def _sell_plan(item, qty, day, cur_inv, unlocked_shops):
    """Units of `item` to sell this call, and how (Task 3 metering)."""
    if item in ONGOING_SELL:
        daily = sustainable_rate(item, day, unlocked_shops=unlocked_shops)
        # Spread over the day rather than one lump: shops tick every 4
        # turns (6x/day - constants.SHOP_SELL_TICKS_PER_DAY), so roughly
        # matching that cadence keeps each order's slice of the day's
        # absorption from arriving all at once and crashing itself.
        n = min(qty, max(1, round(daily / 6)))
    else:
        n = qty  # one-time harvest (WHEAT): no daily rate to protect
    base = MARKET_PARAMS[item]["base"]
    floor = base * PARAMS["sell_floor_frac"]
    while n > 0 and marginal_price_after(item, cur_inv, n) < floor:
        n -= 1
    return n


# --- small helpers ---------------------------------------------------------

def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _step_toward(src, dst):
    """One move action from src toward dst, or None if already there."""
    sx, sy = src
    dx, dy = dst
    if (sx, sy) == (dx, dy):
        return None
    # move on the longer axis first; ties prefer horizontal
    if abs(dx - sx) >= abs(dy - sy) and dx != sx:
        return ["EAST"] if dx > sx else ["WEST"]
    if dy != sy:
        return ["SOUTH"] if dy > sy else ["NORTH"]
    return ["EAST"] if dx > sx else ["WEST"]


def _shed_tiles(board_size):
    h = board_size // 2
    return [(h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h)]


def _unlocked(tile):
    return tile != "LOCKED"


# --- inventory / DROP --------------------------------------------------
#
# HARVEST lands in the harvesting unit's own personal inventory
# (private["inventories"][idx]), not the shed - SELL only ever reads the
# shed. We never issued DROP until now, so everything we harvested was
# unsellable until the automatic end-of-day sweep (see docs/
# ladder-observations.md). Inventory is per-unit and non-transferable
# (there is no unit-to-unit handoff action), so a dedicated "runner" that
# collects other units' harvests isn't actually possible - the harvesting
# unit itself has to be the one to walk it to the shed. The real design
# question is only ever *when that detour is worth it*, not who does it.
#
# First attempt scored DROP as an unconditional pre-pass, decided before
# the tile-task scorer ever saw the board - it could and did steal a unit
# away from an urgent rescue-water task (score 100, dies tonight),
# reintroducing plants_weeded > 0 for the first time since the capital_
# reserve stall trap fix. DROP must never outrank real work. It's folded
# into _assign's existing idle-unit fallback instead: only a unit _assign
# already decided has nothing better to do this turn gets offered the
# choice to walk toward the shed and drop, instead of walking there with
# no purpose. A unit mid-errand on something that actually scored keeps
# carrying its inventory another turn - selling one turn later costs
# nothing; missing a rescue-water task costs the whole plant.

def _inventory_value(inv, prices):
    """Sellable-goods value of a carried inventory at current posted
    prices. Excludes animals (never relevant yet - BUY_ANIMAL/PICKUP don't
    exist in this file - but kept explicit so a future animal-pipeline
    change can't have a carried, not-yet-placed animal misread as
    droppable stock and dumped into the shed as an item)."""
    total = 0
    for item, qty in (inv or {}).items():
        if qty <= 0 or item in ANIMALS:
            continue
        total += qty * prices.get(item, MARKET_PARAMS.get(item, {}).get("base", 0))
    return total


def _iter_tiles(farm):
    tiles = farm["tiles"]
    for y, row in enumerate(tiles):
        for x, t in enumerate(row):
            yield x, y, t


# --- task generation -------------------------------------------------------

def _build_tasks(obs, farm, private, day, board_size, inventories):
    """Return a list of (score, (x, y), action) candidate tasks."""
    tasks = []
    seeds = private.get("seeds", {}) or {}
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    shed = private.get("shed", {}) or {}
    step_now = day * 24 + obs.get("hour", 0)

    # Whether to offer BUILD_COOP/BUILD_PASTURE at all this turn - computed
    # once, not per tile, since farm state doesn't change during planning.
    # Deliberately scored *above* PLANT (55 vs 40) so it wins the tile
    # outright wherever both are offered, rather than being subordinate
    # ("only build once there's no crop to plant") - subordinate lost every
    # single tile to PLANT in practice, since seed buying keeps a standing
    # buffer almost always > 0: confirmed empirically (0 structures built
    # over a full 30-day game with 6+ animals sitting bought-and-unplaced
    # in the shed the whole time) before this was scored competitively
    # instead. _structure_needed is self-limiting on its own terms (stops
    # once shed stock <= empty structures of that kind), so this naturally
    # stops contesting tiles once there's enough capacity - crops get every
    # remaining tile after that, same as before animals existed.
    build_structure = _structure_needed(farm, private)

    for x, y, t in _iter_tiles(farm):
        if not _unlocked(t):
            continue

        if t is None:
            if build_structure:
                op = "BUILD_COOP" if build_structure == "COOP" else "BUILD_PASTURE"
                tasks.append((55, (x, y), [op]))
            crop = _pick_crop(farm, seeds, day)
            if crop and seeds.get(crop, 0) > 0:
                tasks.append((40, (x, y), ["PLANT", crop]))
            continue

        if not isinstance(t, dict):
            continue

        kind = t.get("kind")

        if kind == "WEED":
            tasks.append((12, (x, y), ["DIG"]))
            continue

        if kind == "PLANT":
            crop = t["crop"]
            cd = CROPS[crop]
            age = day - t["planted_day"]
            units = t.get("yield_units", 0)
            watered = t.get("watered_today", False)
            unwatered = t.get("consecutive_unwatered", 0)

            # harvest when mature and at cap (or ongoing with product waiting)
            if units > 0 and age >= cd["first_yield_day"]:
                if cd["ongoing"]:
                    tasks.append((90, (x, y), ["HARVEST"]))
                elif age >= harvest_age(crop, t.get("fertilized_until_day", -1) >= day):
                    value = units * prices.get(crop, MARKET_PARAMS[crop]["base"])
                    score = 85 + min(20, value / 25.0)
                    # A one-time crop has a hard, absolute lifespan deadline
                    # (env's max_lifespan_step) set at planting time - miss
                    # it and the crop starts decaying a yield unit every 2
                    # turns until the tile becomes WEED, same visible outcome
                    # as watering neglect but a completely different cause.
                    # harvest_age's own eligibility gate can land with as
                    # little as a few turns of runway before that deadline
                    # (confirmed: seed 73, a CARROT became harvest-eligible
                    # and hit its lifespan cutoff the same day, lost before
                    # any unit reached it - see docs/strategy-log.md). Once
                    # Branch 2 added several more daily-recurring high-score
                    # chores (FEED, animal PICKUP/PLACE) competing for the
                    # same units, that thin margin started actually costing
                    # crops. Escalate to rescue-tier in the last few turns
                    # before the deadline, same as WATER rescue - both are a
                    # total, irreversible loss if missed. Buffer has to stay
                    # small: harvest_age's own fallback (never reaches max
                    # yield) lands eligibility onset within about a day of
                    # the deadline for most one-time crops *by construction*,
                    # so a full day's buffer effectively promotes routine
                    # end-of-life harvesting to rescue-tier for its entire
                    # eligible window, not just genuine last-minute risk -
                    # tried 24 turns first, cost -1,806 mean paired-diff coins
                    # vs v2 for a problem worth a few dozen coins/game (see
                    # docs/strategy-log.md). Also tried 12: counterintuitively
                    # *worse* than 6 (6 pool seeds hit plants_weeded>0 vs v2,
                    # up from 0) - a wider rescue-tier window raises
                    # contention density at score 100 overall, so it can
                    # cost a different, previously-fine harvest elsewhere in
                    # the same crowded turn. Widening this knob is not free;
                    # remeasure the full pool before changing it again. 6
                    # only fires in the closing quarter-day and leaves a
                    # small residual (2/48 pool seeds vs animal-heavy
                    # specifically, 2 crops each - not fully eliminated, see
                    # docs/strategy-log.md).
                    mls = t.get("max_lifespan_step", -1)
                    if mls >= 0 and step_now >= mls - 6:
                        score = max(score, 100)
                    tasks.append((score, (x, y), ["HARVEST"]))
                    continue

            if watered:
                continue

            # rescue: it dies tonight if we don't water
            if unwatered >= 1:
                tasks.append((100, (x, y), ["WATER"]))
                continue

            # bonus window: watering here actually adds yield
            win = bonus_window(crop)
            if win and win[0] <= age <= win[1]:
                tasks.append((70, (x, y), ["WATER"]))
            elif cd["ongoing"] and age >= cd["first_yield_day"] - 1:
                tasks.append((60, (x, y), ["WATER"]))
            continue

        # animal structures. A freshly built COOP/PASTURE is {"kind": ...}
        # with no "animal" key at all - not "animal": None - so the guard
        # has to be the structure kind, not key presence (confirmed against
        # the env source: BUILD_COOP writes {"kind": "COOP"} exactly).
        if kind in ("COOP", "PASTURE"):
            animal = t.get("animal")
            if animal is None:
                # Empty COOP/PASTURE: place an animal here if some unit is
                # carrying one that matches (eligibility - and, once
                # eligible, which specific animal - resolved in _assign,
                # since that's the only place we know what any given unit
                # is currently carrying). Scored above routine fieldwork:
                # every day an animal sits in the shed instead of placed is
                # a lost production day, but nothing dies over it, so it
                # stays below rescue-tier (100).
                tasks.append((80, (x, y), ["PLACE", kind]))
                continue
            a = ANIMALS[animal]
            if t.get("yield_units", 0) > 0:
                tasks.append((88, (x, y), ["HARVEST"]))
            if t.get("fertilizer_available"):
                # Raised 75 -> 86 (Task 2, target-plan rebuild): fertilizer
                # is a primary revenue line here, not a minor side-product -
                # a finite, non-regenerating, opponent-shared pool where
                # collecting (and selling - see fert_reserve=0) first is a
                # real edge (docs/economics.md, docs/strategy-log.md). Above
                # PLACE (80) and routine FEED (82), below animal-product
                # HARVEST (88) and rescue-tier (100 - emergency FEED never
                # loses to this).
                tasks.append((86, (x, y), ["COLLECT_FERTILIZER"]))
            if not t.get("fed_today"):
                # Non-urgent baseline 82: FEED is only ever eligible for a
                # unit already carrying WHEAT (a small, deliberately-
                # limited pool - see the wheat-pickup runner cap above),
                # so unlike most tasks it can't out-compete other work for
                # a *free* unit. Raising this to 87 (above
                # COLLECT_FERTILIZER) was tried and measured *worse*
                # (mean animals_lost 3.1 -> 4.4 across 8 seeds) - not the
                # actual bottleneck; reverted. 82 beats PLACE (80) and
                # most ordinary harvests while staying below rescue-tier
                # (100).
                urgency = 100 if t.get("consecutive_unfed", 0) >= 1 else 82
                tasks.append((urgency, (x, y), ["FEED"]))
            elif not t.get("cared_today"):
                tasks.append((45, (x, y), ["CARE"]))

    # Animal pickup: an empty structure exists (the PLACE task above, score
    # 80) but PLACE eligibility requires already carrying a matching animal
    # (see _assign) - nothing generated that carry until now, so those PLACE
    # tasks previously had no eligible unit ever, and every bought animal
    # sat in the shed forever. Fetch exactly as many as there are open slots
    # (net of animals already in transit), one PICKUP task per distinct
    # shed tile so at most that many units get pulled onto the job - same
    # bounded pattern as the wheat pickup below, just capped instead of
    # flooding all 4 shed tiles regardless of how many are actually needed.
    empty_slots_by_structure = {}
    for score, pos, action in tasks:
        if action[0] == "PLACE":
            empty_slots_by_structure[action[1]] = empty_slots_by_structure.get(action[1], 0) + 1
    carrying_by_structure = {}
    for inv in inventories:
        for name in ANIMALS:
            qty = inv.get(name, 0)
            if qty > 0:
                s = ANIMALS[name]["structure"]
                carrying_by_structure[s] = carrying_by_structure.get(s, 0) + qty
    shed_tiles = _shed_tiles(board_size)
    for animal_name, spec in ANIMALS.items():
        structure = spec["structure"]
        free_slots = empty_slots_by_structure.get(structure, 0) - carrying_by_structure.get(structure, 0)
        if free_slots <= 0:
            continue
        n = min(free_slots, shed.get(animal_name, 0), len(shed_tiles))
        for k in range(n):
            tasks.append((78, shed_tiles[k], ["PICKUP", animal_name, 1]))
        # claim the slots we just requested so COW and SHEEP, which share
        # PASTURE, don't both fetch for the same open spot
        carrying_by_structure[structure] = carrying_by_structure.get(structure, 0) + n

    # Wheat pickup for FEED: scaled to actual need, not a flat qty=2. A
    # flat amount only ever covers one animal - with double-digit herds by
    # midgame this left roughly half the animals unfed every single day
    # even with plenty of WHEAT sitting unused in the shed, which is what
    # drove animals_lost into the teens per game. Fetch enough for every
    # animal currently owed a feed today, net of wheat units already being
    # carried, via all 4 shed tiles whenever any feed is owed - not scaled
    # down for a small need, because FEED requires the assigned unit to
    # already be *carrying* wheat (a same-turn PICKUP doesn't chain into a
    # same-turn FEED - the scheduler re-decides every unit's task fresh
    # each turn, no "finish the delivery" memory), so more simultaneous
    # carriers means more chances one of them is near whichever cluster of
    # the herd is currently unfed. Confirmed this matters at scale: with
    # only 2 runners, 6 sheep split across two tiles a few squares apart
    # had 4 of them starve while the other 2 got fed every day (the
    # runners kept reaching the same nearer cluster) - animals_lost traced
    # directly to this before widening to 4. No carry-quantity cap in this
    # game, so each runner can still restock several feeds worth per trip.
    feed_needed = sum(1 for s, _, a in tasks if a and a[0] == "FEED")
    wheat_carried = sum((inv or {}).get("WHEAT", 0) for inv in inventories)
    wheat_needed = feed_needed - wheat_carried
    if wheat_needed > 0 and shed.get("WHEAT", 0) > 0:
        any_unfed_urgent = any(s == 100 and a and a[0] == "FEED" for s, _, a in tasks)
        score = 100 if any_unfed_urgent else 65
        shed_tiles = _shed_tiles(board_size)
        qty = min(wheat_needed, shed["WHEAT"])
        qty_per_runner = max(1, -(-qty // len(shed_tiles)))  # ceil(qty/4)
        for st in shed_tiles:
            tasks.append((score, st, ["PICKUP", "WHEAT", qty_per_runner]))

    return tasks


def _count_crop(farm, crop):
    return sum(1 for _, _, t in _iter_tiles(farm)
               if isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("crop") == crop)


def _pick_crop(farm, seeds, day):
    """Which crop to sow on one empty tile right now, or None.

    A bounded, one-time opening batch (docs/strategy-log.md,
    notebooks/live-meta: "early seeds avg wheat 14.0, melon 11.6 per
    player, days 0-4") - not an ongoing crop program. Gap-based, not a
    hard day cutoff: at the real $3,000 start the buffer purchase in
    _market_orders step 3 comfortably closes both gaps within days 0-4
    on its own, matching the notebook's own numbers, so a cutoff would be
    redundant there. A hard `day > early_crop_end_day` cutoff was tried
    first and cost the low-startingMoney stress test hard: at low cash
    only the one-seed-at-a-time trickle fallback can fire (the full-
    buffer purchase needs capital_reserve=$1,200 headroom it may never
    reach), so by day 4 only a few tiles were planted, the cutoff then
    permanently blocked any more, and with animals (COW $400/SHEEP $500)
    also unaffordable there was nothing left to do - a new deadlock,
    same shape as the original capital_reserve stall trap. Gap-based
    keeps trying (at whatever pace cash allows) until the target is
    actually met, so a slow start still finishes eventually instead of
    stalling forever. Picks whichever crop in `early_crop_target` has the
    bigger remaining gap (WHEAT only since the 2026-08-08 melon removal -
    see the PARAMS comment - but left as a loop over the dict rather than
    hard-coded to one crop, in case that target ever grows again)."""
    best, best_gap = None, 0
    for crop, target in PARAMS["early_crop_target"].items():
        cd = CROPS[crop]
        if 30 - day < cd["max_yield_day"] + 1:
            continue  # won't mature in time; don't waste seed money
        have = _count_crop(farm, crop) + seeds.get(crop, 0)
        gap = target - have
        if gap > best_gap:
            best, best_gap = crop, gap
    return best


# --- assignment ------------------------------------------------------------

def _carried_animal_for(inv, structure_kind):
    """Name of an animal in `inv` that matches `structure_kind`, or None.
    A unit could in principle carry more than one animal type at once (no
    game rule against it) - arbitrary but deterministic pick among ANIMALS
    in dict order is fine, this is only ever used to pick something to
    PLACE right now."""
    for name in ANIMALS:
        if inv.get(name, 0) > 0 and ANIMALS[name]["structure"] == structure_kind:
            return name
    return None


def _assign(units, tasks, board_size, inventories=None, prices=None):
    """Greedy: best task first, to its nearest free ELIGIBLE unit.

    Most tasks are eligible for any free unit. Two are not: FEED requires
    the assigned unit to already be carrying WHEAT, and PLACE requires it
    to be carrying an animal matching the target structure - both are
    resolved here, at assignment time, since which unit (if any) is
    currently carrying the right thing is exactly what determines whether
    the task can be done at all this turn. A task with no eligible unit
    this turn is skipped (not treated as "no units left" - other units may
    still be free for other tasks), so the old "no free unit -> stop
    entirely" short-circuit only fires once every unit truly has an
    action, not just once the *nearest* one is taken.
    """
    inventories = inventories or [{}] * len(units)
    actions = [None] * len(units)
    tasks = sorted(tasks, key=lambda t: -t[0])
    taken_tiles = set()

    def eligible(i, verb, arg):
        if verb == "FEED":
            return (inventories[i] if i < len(inventories) else {}).get("WHEAT", 0) > 0
        if verb == "PLACE":
            inv = inventories[i] if i < len(inventories) else {}
            return _carried_animal_for(inv, arg) is not None
        return True

    for score, pos, action in tasks:
        if pos in taken_tiles:
            continue
        if all(a is not None for a in actions):
            break  # every unit already has an action - nothing left to assign
        verb, arg = action[0], (action[1] if len(action) > 1 else None)

        best_i, best_d = None, None
        for i, u in enumerate(units):
            if actions[i] is not None or not eligible(i, verb, arg):
                continue
            d = _manhattan(u, pos)
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        if best_i is None:
            continue  # no eligible free unit for *this* task - try the next one

        # discount tasks that are far away; a 6-move trip for a low-value task
        # is worse than doing something local
        if best_d > 0 and score - 6 * best_d < 10:
            continue

        if verb == "PLACE":
            animal_name = _carried_animal_for(inventories[best_i], arg)
            action = ["PLACE", animal_name]

        move = _step_toward(units[best_i], pos)
        actions[best_i] = move if move else action
        taken_tiles.add(pos)

    # Idle units (nothing scored high enough above to claim them, or
    # carrying the only thing that would have made them eligible for
    # something that scored) get a purpose in priority order, each of
    # which can only ever claim a turn _assign already decided was
    # otherwise unproductive - none of this can preempt a real task, in
    # particular never a rescue-water or emergency-feed task (see the
    # comment above _inventory_value for why an earlier DROP-only version
    # of this got that wrong).
    #
    # A carrying unit can still reach here: e.g. two units each carrying a
    # COW but only one empty PASTURE - one places via the main loop above,
    # the other has nowhere left to put its animal this turn.
    unclaimed_place = {}
    for score, pos, action in tasks:
        if action[0] == "PLACE" and pos not in taken_tiles:
            unclaimed_place.setdefault(action[1], []).append(pos)

    shed = _shed_tiles(board_size)
    for i, a in enumerate(actions):
        if a is not None:
            continue
        inv = inventories[i] if i < len(inventories) else {}

        # 1. Already carrying a bought animal with somewhere to put it:
        # deliver it.
        delivered = False
        for structure, spots in unclaimed_place.items():
            animal_name = _carried_animal_for(inv, structure)
            if animal_name is None or not spots:
                continue
            target = min(spots, key=lambda s: _manhattan(units[i], s))
            actions[i] = (["PLACE", animal_name] if units[i] == target
                          else _step_toward(units[i], target))
            spots.remove(target)
            delivered = True
            break
        if delivered:
            continue

        # 2. Carrying anything sellable: walk to the shed and DROP.
        target = min(shed, key=lambda s: _manhattan(units[i], s))
        if _inventory_value(inv, prices or {}) > 0:
            actions[i] = (["DROP"] if units[i] == target
                           else _step_toward(units[i], target))
            continue

        # 3. Nothing carried: just center at the shed for next turn.
        actions[i] = _step_toward(units[i], target) or PASS
    return actions


# --- market ----------------------------------------------------------------

def _market_orders(obs, farm, private, day, hour, inventories=None, tasks=None):
    orders = []
    money = farm["money"]
    shed = private.get("shed", {}) or {}
    seeds = private.get("seeds", {}) or {}
    inv = (obs.get("market", {}) or {}).get("inventory", {}) or {}
    hires_today = farm.get("hires_today", 0)
    crop = _pick_crop(farm, seeds, day)

    # 1. hire at the start of the day - actions are the constraint. But
    # hiring must never be able to spend the cash the crop engine needs to
    # bootstrap itself: floor the budget at twice the active crop's seed
    # cost (not a flat $50), so a run of cheap hires can't leave us unable
    # to afford the one purchase that generates future income.
    #
    # Except: a couple of hires cost almost nothing (fib(0)+fib(1) = $2)
    # and are never worth fully blocking, regardless of the reserve above.
    # Confirmed a real, severe cost of not guaranteeing this: at 14
    # animals, a near-zero-cash day (money < seed_floor, common during the
    # target route's own trough - docs/strategy-log.md) zeroed the hire
    # budget entirely, leaving only the farmer to cover the whole board -
    # 5+ animals sat unfed *all day* despite wheat sitting in the shed,
    # not because feed wasn't there but because there was no one left to
    # deliver it. animals_lost 19-22/game traced directly to this. A tiny
    # floor here is negligible next to any real purchase but is the
    # difference between 1 unit and 3 on the worst days.
    #
    # Even that wasn't enough at 14 animals split across separate corners
    # of the board: traced directly (day 8, seed 11) - 8 animals
    # simultaneously needed FEED (all rescue-tier, score 100) but only 3
    # hands existed that day (the flat floor above covers ~2-3 hires); a
    # 6-animal cluster got serviced by hour 20, two more distant sheep
    # never did and escaped the next morning - confirmed via fed_today,
    # not a feed-supply problem (shed held 5-13 WHEAT the entire day,
    # never empty). The greedy per-turn assignment has no notion of
    # "make sure every urgent task gets covered today," only "assign the
    # nearest reachable one" - so with too few units, an entire cluster
    # can go untouched all day even while wheat sits unused. Size the
    # hire budget to the day's actual rescue-tier workload directly,
    # rather than guess a flat floor: cheap insurance against exactly
    # this failure, since hire_cost is fib-cheap next to a $400-500
    # animal.
    if hour == 0:
        seed_floor = (CROPS[crop]["seed"] * 2) if crop else 20
        budget = max(
            min(money * PARAMS["hand_budget_frac"], max(0, money - seed_floor)),
            min(money, 4),
        )
        urgent = len({pos for score, pos, _ in (tasks or []) if score >= 100})
        if urgent > 0:
            target_urgent_hands = min(hires_today + urgent, PARAMS["target_hands"])
            urgent_cost = (cumulative_hire_cost(target_urgent_hands)
                           - cumulative_hire_cost(hires_today))
            budget = max(budget, min(money, urgent_cost))
        spent = 0
        n = hires_today
        while n < PARAMS["target_hands"]:
            c = hire_cost(n)
            if spent + c > budget:
                break
            orders.append(["HIRE"])
            spent += c
            n += 1
        money -= spent

    # 2. sell. Reserves, the price floor, and the metering cap all exist to
    # protect *future* sales - once there's no future left (liquidation_day),
    # unsold shed inventory doesn't count toward the final score at all, so
    # every one of those becomes a way to strand value instead of protect
    # it. Drop them and dump the shed.
    liquidating = day >= PARAMS["liquidation_day"]
    unlocked_shops = (obs.get("town", {}) or {}).get("unlocked_shops", [])
    for item, qty in sorted(shed.items(), key=lambda kv: -kv[1]):
        if qty <= 0 or item not in MARKET_PARAMS:
            continue
        if not liquidating and item == "WHEAT":
            qty = max(0, qty - _wheat_needed(farm))
            if qty <= 0:
                continue
        if liquidating:
            n = qty
        elif item == "FERTILIZER":
            n = qty  # first-mover, finite shared pool - see fert_reserve=0
        else:
            cur_inv = inv.get(item, 10000)
            n = _sell_plan(item, qty, day, cur_inv, unlocked_shops)
        if n > 0:
            orders.append(["SELL", item, n])

    # 3. buy wheat to feed the herd - protected priority, ahead of new
    # seed/land/animal spend (Task 1, target-plan rebuild). Losing an
    # already-owned animal ($400-500) to a missed feed is a real capital
    # loss, not just a missed opportunity, and 14 animals x 1 wheat/day
    # (~390 over the season, notebooks/live-meta) needs real, ongoing cash
    # that the early wheat batch alone can't fully cover. Buys whatever
    # is affordable toward the need, not all-or-nothing: partially fed is
    # still much better than the old flat "$400 minimum, or nothing" gate,
    # which blocked every feed purchase for most of the cash-poor early
    # game and reproduced the "capital_reserve stall trap" shape at animal
    # scale - confirmed directly (seed 11: animals_lost 22, cow/sheep
    # counts oscillating 4->0, 5->1 day to day - see docs/strategy-log.md).
    need = _wheat_needed(farm) - shed.get("WHEAT", 0)
    if need > 0 and money > 20:
        price = market_price("WHEAT", inv.get("WHEAT", 10000))
        buy = min(need, int(money // max(1, price)))
        if buy > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", buy])
            money -= price * buy

    # 4. keep seeds stocked. Three things, kept deliberately separate:
    #
    # (a) a cap on *simultaneous* plants+held-seed relative to hand count,
    #     independent of cash. Fixes overplanting - see the tiles_per_unit
    #     comment above.
    # (b) the cash gate for the full top-up to `seed_buffer`. Unchanged
    #     from the original all-or-nothing `capital_reserve` check.
    # (c) a capped trickle when the full top-up isn't affordable. This
    #     used to only fire at *exactly* zero held seed - found (target-
    #     plan rebuild, Task 1 investigation) that this leaves a real gap:
    #     held count settles at 1-2 (never fully zero, since the trickle
    #     itself refills it slightly, but never zero) while `capital_
    #     reserve`'s $1,200 headroom requirement is far out of reach for
    #     most of the game's cash-poor early trough. Confirmed directly
    #     (seed 11): WHEAT seed count stuck at 1 and MELON at 2 for the
    #     entire days 1-9 window, while tile counts decayed toward 0 as
    #     existing plants matured and harvested with nothing replacing
    #     them - `_pick_crop`'s gap kept growing (5 -> 13 for WHEAT) the
    #     whole time, correctly *requested*, never *achieved*. Not a
    #     labour/capacity problem - `capacity` (the tiles_per_unit cap in
    #     (a)) stayed positive (2-24) throughout the same window.
    #     Widened to top up toward `seed_trickle_cap` (well under the full
    #     `seed_buffer`) whenever affordable, not just at zero - small and
    #     capped, so this isn't the same uncapped "any room" drain an
    #     earlier version of this trickle was reverted for (cost -156
    #     coins paired, see docs/strategy-log.md): that one re-fired for
    #     the *entire* remaining buffer gap every hour a tile freed up;
    #     this one only ever tops up to a small fixed ceiling.
    if crop:
        n_units = 1 + len(farm.get("hands", []))
        in_flight = sum(seeds.values()) + sum(
            1 for _, _, t in _iter_tiles(farm)
            if isinstance(t, dict) and t.get("kind") == "PLANT"
        )
        capacity = max(0, n_units * PARAMS["tiles_per_unit"] - in_flight)
        want = min(PARAMS["seed_buffer"] - seeds.get(crop, 0), capacity)
        cost = CROPS[crop]["seed"]
        if want > 0 and cost > 0:
            if money > cost * want + PARAMS["capital_reserve"]:
                orders.append(["BUY_SEED", crop, want])
            else:
                top_up = min(want, PARAMS["seed_trickle_cap"] - seeds.get(crop, 0))
                buy = min(top_up, int(money // cost))
                if buy > 0:
                    orders.append(["BUY_SEED", crop, buy])

    # 5. land, then animals. One BUY_ANIMAL per call (the biggest deficit,
    # from _animal_deficit) rather than the whole target at once - this
    # function runs every hour, so purchases naturally pace themselves the
    # same way the seed-buying above does, instead of a single-turn burst.
    n_extra = len(farm.get("unlocked_quadrants", ["NW"])) - 1
    if n_extra < PARAMS["land_quadrants_target"]:  # NE then SW, never SE
        price = LAND_PRICES[n_extra]
        if (money > price + _reserve(day)
                and PARAMS["land_buy_min_day"] <= day < PARAMS["construction_end_day"]):
            orders.append(["BUY_LAND"])
            money -= price

    deficit_kind, deficit_room = _animal_deficit(farm, private, day, inventories)
    if deficit_kind and deficit_room > 0 and day < 26:
        cost = ANIMALS[deficit_kind]["cost"]
        if money > cost + _reserve(day):
            orders.append(["BUY_ANIMAL", deficit_kind, 1])

    return orders[:10]  # maxMarketOrdersPerTurn


def _wheat_needed(farm):
    return sum(1 for _, _, t in _iter_tiles(farm)
               if isinstance(t, dict) and t.get("animal"))


def _count_animals(farm, animal):
    return sum(1 for _, _, t in _iter_tiles(farm)
               if isinstance(t, dict) and t.get("animal") == animal)


def _empty_structures(farm, structure_kind):
    """Built COOP/PASTURE tiles with no animal placed yet. One structure
    tile always holds exactly one animal - PLACE replaces the tile outright
    (kaggriculture.py:363-377) - so "8 cow" in the meta means 8 separate
    PASTUREs, not one pasture holding 8."""
    return [(x, y) for x, y, t in _iter_tiles(farm)
            if isinstance(t, dict) and t.get("kind") == structure_kind and "animal" not in t]


def _animal_deficit(farm, private, day, inventories=None):
    """Animal kind furthest below target and past its buy-day gate, for the
    BUY_ANIMAL decision: counts what's on the board, what's sitting in the
    shed, AND what a unit is currently carrying between PICKUP and PLACE
    (so this settles toward 0 once enough is in the pipeline, instead of
    buying past target while a few are mid-transit - PICKUP removes an
    animal from the shed the instant it's issued, so a shed-only count goes
    right back to "deficit" for every animal that's actually just a couple
    of turns from being placed; confirmed empirically as the cause of a
    3x-over-target COW/SHEEP overbuy before this was added). Deliberately
    does NOT count empty structures - an empty COOP/PASTURE is spare
    *capacity*, not a fulfilled purchase; counting it here would count the
    same capacity toward two different animals' targets (a PASTURE fits
    either COW or SHEEP) and would block ever buying the first animal to
    fill a structure built ahead of need.
    Returns (kind, room) or (None, 0)."""
    shed = private.get("shed", {}) or {}
    carried = {}
    for inv in (inventories or []):
        for name in ANIMALS:
            qty = (inv or {}).get(name, 0)
            if qty > 0:
                carried[name] = carried.get(name, 0) + qty
    best_kind, best_room = None, 0
    for kind, target in PARAMS["animal_target"].items():
        if day < PARAMS["animal_buy_min_day"].get(kind, 0):
            continue
        have = _count_animals(farm, kind) + shed.get(kind, 0) + carried.get(kind, 0)
        room = target - have
        if room > best_room:
            best_kind, best_room = kind, room
    return best_kind, best_room


def _structure_needed(farm, private):
    """Structure kind (COOP/PASTURE) to build next, for the BUILD_COOP/
    BUILD_PASTURE decision: some animal is bought and sitting in the shed
    with no empty structure of the matching kind to receive it. Grouped by
    structure, not by animal, since COW and SHEEP share PASTURE - shed
    COW=2, SHEEP=1 means 3 pastures wanted, not evaluated separately.
    Returns a structure kind or None."""
    shed = private.get("shed", {}) or {}
    unplaced_by_structure = {}
    for kind in PARAMS["animal_target"]:
        structure = ANIMALS[kind]["structure"]
        unplaced_by_structure[structure] = unplaced_by_structure.get(structure, 0) + shed.get(kind, 0)
    for structure, unplaced in unplaced_by_structure.items():
        if unplaced > len(_empty_structures(farm, structure)):
            return structure
    return None


# --- entrypoint ------------------------------------------------------------

def _agent(obs):
    player = obs.get("player", 0)
    farms = obs.get("farms") or []
    if not farms or player >= len(farms):
        return {"farmer": PASS, "hands": [], "market": []}

    farm = farms[player]
    private = obs.get("private", {}) or {}
    day = obs.get("day", 0)
    hour = obs.get("hour", 0)
    board_size = len(farm["tiles"])

    units = [tuple(farm["farmer"])] + [tuple(h) for h in farm.get("hands", [])]
    inventories = private.get("inventories") or [{}]
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}

    tasks = _build_tasks(obs, farm, private, day, board_size, inventories)
    actions = _assign(units, tasks, board_size, inventories, prices)
    market = _market_orders(obs, farm, private, day, hour, inventories, tasks)

    return {
        "farmer": actions[0] if actions else PASS,
        "hands": actions[1:],
        "market": market,
    }


def agent(obs):
    """Never raise - a crash forfeits the episode."""
    try:
        return _agent(obs)
    except Exception:
        farm = (obs.get("farms") or [{}])[obs.get("player", 0)]
        n_hands = len(farm.get("hands", []) or [])
        return {"farmer": PASS, "hands": [PASS] * n_hands, "market": []}
