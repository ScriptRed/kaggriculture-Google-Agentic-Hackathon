"""route-proxy: a closed-loop approximation of the verified ~195-202k public
route (docs/target-plan.md - barnyard-economist's day-by-day census, checked
directly against the notebook, not paraphrased).

This is not a recording. It computes actions from live state every turn like
every other opponent in this pool, aiming at a day-indexed *target board
composition* (crop tile counts, animal counts, hand count) instead of a step
index. It does not need to hit the source route's own ~195-202k bank - it
needs to be strategically faithful, so our own agent has a real yardstick for
the shape of a strong farm instead of only the improvised archetypes
(animal-heavy, melon-rush, market-dumper) built before we had a verified
census to work from.

Verified census (docs/target-plan.md), the target this file approximates:

    d00  $3,000                                                 25 empty, 75 locked
    d03  $187    12 melon,  7 wheat,               2 cow, 2 sheep
    d06  $972    12 melon,  7 wheat,               4 cow, 2 sheep
    d09  $2,848  12 melon,  7 wheat, 12 strawberry, 6 cow, 4 sheep
    d12  $14,602 12 melon,  7 wheat, 39 strawberry, 8 cow, 6 sheep
    d15  $26,964 12 melon,  7 wheat, 42 strawberry, 8 cow, 6 sheep  <- steady state
    d21  $66,179 12 melon,  7 wheat, 42 strawberry, 8 cow, 6 sheep  <- frozen
    d24  $114,962           19 wheat, 37 strawberry, 8 cow, 6 sheep <- melon gone
    d27  $154,076            35 wheat, 23 strawberry, 8 cow, 6 sheep
    hands: 1(d05) -> 8(d10) -> 13(d15) -> 14(d20-25) -> 6(d29)
    land: exactly two extra quadrants (NE, SW), never the $4,000 SE one

The hand ramp below is deliberately front-loaded relative to the census
numbers above (8 from day 0, not 1 until day 5) - see HAND_SCHEDULE for
why: the census numbers are what a hand-tuned 719-step recording needed,
and a live greedy scorer needs more bodies to service the same board
without collapsing.

Deliberately self-contained: does not import from agent/, which
arena/run.py snapshots per-run so live edits there can't affect this file.
"""

PASS = ["PASS"]

CROPS = {
    "WHEAT":      {"seed": 10,  "first_yield_day": 2,  "max_yield_day": 4,  "max_yield": 6, "ongoing": False},
    "MELON":      {"seed": 80,  "first_yield_day": 10, "max_yield_day": 12, "max_yield": 6, "ongoing": False},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "max_yield": 4, "ongoing": True, "interval": 2},
}
ANIMALS = {
    "COW":   {"cost": 400, "structure": "PASTURE"},
    "SHEEP": {"cost": 500, "structure": "PASTURE"},
}
LAND_PRICES = [1000, 2000, 4000]
TILES_PER_UNIT = 4  # cap on simultaneous plants+held-seed per unit
SELL_BASE = {"WHEAT": 25, "MELON": 250, "STRAWBERRY": 120, "MILK": 160, "WOOL": 200, "FERTILIZER": 100}
SELL_BATCH = {"WHEAT": 12, "MELON": 4, "STRAWBERRY": 4, "MILK": 4, "WOOL": 3, "FERTILIZER": 6}

# Day-indexed target board composition, interpolated between breakpoints.
# Matches the verified census exactly at each breakpoint day.
CENSUS = [
    (0,  {"MELON": 0,  "WHEAT": 0, "STRAWBERRY": 0},  {"COW": 0, "SHEEP": 0}),
    (3,  {"MELON": 12, "WHEAT": 7, "STRAWBERRY": 0},  {"COW": 2, "SHEEP": 2}),
    (6,  {"MELON": 12, "WHEAT": 7, "STRAWBERRY": 0},  {"COW": 4, "SHEEP": 2}),
    (9,  {"MELON": 12, "WHEAT": 7, "STRAWBERRY": 12}, {"COW": 6, "SHEEP": 4}),
    (12, {"MELON": 12, "WHEAT": 7, "STRAWBERRY": 39}, {"COW": 8, "SHEEP": 6}),
    (15, {"MELON": 12, "WHEAT": 7, "STRAWBERRY": 42}, {"COW": 8, "SHEEP": 6}),
    (21, {"MELON": 12, "WHEAT": 7, "STRAWBERRY": 42}, {"COW": 8, "SHEEP": 6}),
    (24, {"MELON": 0,  "WHEAT": 19, "STRAWBERRY": 37}, {"COW": 8, "SHEEP": 6}),
    (27, {"MELON": 0,  "WHEAT": 35, "STRAWBERRY": 23}, {"COW": 8, "SHEEP": 6}),
    (29, {"MELON": 0,  "WHEAT": 35, "STRAWBERRY": 23}, {"COW": 8, "SHEEP": 6}),
]
# The verified census's own hand numbers (1 at d05, 8 at d10...) are what a
# hand-optimized 719-step recording needed - a live greedy scorer needs more
# bodies to service the same tile count without collapsing (confirmed: the
# literal census schedule starves the d03-d10 melon/wheat/cow/sheep opening
# with only 0-1 units, plants_weeded and animals_lost both spike, final bank
# near zero). Front-loaded here so the greedy executor can actually run the
# target board it's buying, while keeping the same overall shape (ramp to a
# mid-teens peak, taper at the very end).
HAND_SCHEDULE = [(0, 8), (10, 12), (15, 14), (20, 14), (25, 14), (29, 6)]


def _interp_schedule(day, schedule_of_dicts):
    """schedule_of_dicts: [(day, {key: val}), ...], sorted by day. Linear
    interpolation per key between the two bracketing breakpoints."""
    if day <= schedule_of_dicts[0][0]:
        return dict(schedule_of_dicts[0][1])
    for i in range(len(schedule_of_dicts) - 1):
        d0, v0 = schedule_of_dicts[i]
        d1, v1 = schedule_of_dicts[i + 1]
        if d0 <= day <= d1:
            if d1 == d0:
                return dict(v1)
            t = (day - d0) / (d1 - d0)
            return {k: v0[k] + (v1[k] - v0[k]) * t for k in v0}
    return dict(schedule_of_dicts[-1][1])


def _target_crops(day):
    return {k: round(v) for k, v in
            _interp_schedule(day, [(d, c) for d, c, a in CENSUS]).items()}


def _target_animals(day):
    return {k: round(v) for k, v in
            _interp_schedule(day, [(d, a) for d, c, a in CENSUS]).items()}


def _target_hands(day):
    return round(_interp_schedule(day, [(d, {"n": n}) for d, n in HAND_SCHEDULE])["n"])


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _step_toward(src, dst):
    sx, sy = src
    dx, dy = dst
    if (sx, sy) == (dx, dy):
        return None
    if abs(dx - sx) >= abs(dy - sy) and dx != sx:
        return ["EAST"] if dx > sx else ["WEST"]
    if dy != sy:
        return ["SOUTH"] if dy > sy else ["NORTH"]
    return ["EAST"] if dx > sx else ["WEST"]


def _shed_tiles(board_size):
    h = board_size // 2
    return [(h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h)]


def _nearest(pos, tiles):
    return min(tiles, key=lambda t: _manhattan(pos, t)) if tiles else None


def _iter_tiles(farm):
    for y, row in enumerate(farm["tiles"]):
        for x, t in enumerate(row):
            yield x, y, t


def _count_crop(farm, crop):
    return sum(1 for _, _, t in _iter_tiles(farm)
               if isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("crop") == crop)


def _count_animals(farm, kind):
    return sum(1 for _, _, t in _iter_tiles(farm)
               if isinstance(t, dict) and t.get("animal") == kind)


def _empty_structures(farm, structure_kind):
    return [(x, y) for x, y, t in _iter_tiles(farm)
            if isinstance(t, dict) and t.get("kind") == structure_kind and "animal" not in t]


def _bonus_window(crop):
    cd = CROPS[crop]
    if cd["ongoing"]:
        return None
    return ((cd["max_yield_day"] + 1) // 2, cd["max_yield_day"])


def _crop_to_plant(day, farm, seeds):
    """Highest-deficit crop still worth planting today, or None. Melon's
    deficit goes to zero from day ~22 in the census (the "melon gone" wind-
    down) - a crop with a negative/zero deficit is never (re)planted, so
    existing melon tiles just get harvested out and not replaced."""
    days_left = 30 - day
    target = _target_crops(day)
    best, best_gap = None, 0
    for crop, want in target.items():
        cd = CROPS[crop]
        # Don't plant something that can't mature (one-time crops need the
        # full bonus window; ongoing crops just need to reach first yield).
        if days_left < cd["max_yield_day"] - (0 if cd["ongoing"] else 0) + 1:
            continue
        have = _count_crop(farm, crop) + seeds.get(crop, 0)
        gap = want - have
        if gap > best_gap:
            best, best_gap = crop, gap
    return best


def _build_tile_tasks(obs, farm, private, day, board_size):
    tasks = []
    seeds = private.get("seeds", {}) or {}
    target_animals = _target_animals(day)
    shed = private.get("shed", {}) or {}

    for x, y, t in _iter_tiles(farm):
        if t == "LOCKED":
            continue

        if t is None:
            crop = _crop_to_plant(day, farm, seeds)
            if crop and seeds.get(crop, 0) > 0:
                tasks.append((40, (x, y), ["PLANT", crop]))
                continue
            # No crop wants this tile right now - offer a structure instead
            # if some animal target still needs a home.
            deficits = [(k, target_animals[k] - (_count_animals(farm, k) + shed.get(k, 0)))
                        for k in ANIMALS]
            deficits.sort(key=lambda kv: -kv[1])
            need_kind, need_n = deficits[0]
            if need_n > 0 and not _empty_structures(farm, ANIMALS[need_kind]["structure"]):
                tasks.append((55, (x, y), ["BUILD_PASTURE"]))
            continue

        if not isinstance(t, dict):
            continue
        kind = t.get("kind")

        if kind == "WEED":
            tasks.append((15, (x, y), ["DIG"]))
            continue

        if kind == "PLANT":
            crop = t["crop"]
            cd = CROPS[crop]
            age = day - t.get("planted_day", day)
            units = t.get("yield_units", 0)
            watered = t.get("watered_today", False)
            unwatered = t.get("consecutive_unwatered", 0)

            if units > 0 and age >= cd["first_yield_day"]:
                if cd["ongoing"]:
                    tasks.append((90, (x, y), ["HARVEST"]))
                    continue
                if age >= cd["max_yield_day"]:
                    mls = t.get("max_lifespan_step", -1)
                    step_now = day * 24 + obs.get("hour", 0)
                    score = 100 if (mls >= 0 and step_now >= mls - 6) else 88
                    tasks.append((score, (x, y), ["HARVEST"]))
                    continue

            if watered:
                continue
            if unwatered >= 1:
                tasks.append((100, (x, y), ["WATER"]))
                continue
            win = _bonus_window(crop)
            if win and win[0] <= age <= win[1]:
                tasks.append((70, (x, y), ["WATER"]))
            elif cd["ongoing"] and age >= cd["first_yield_day"] - 1:
                tasks.append((60, (x, y), ["WATER"]))
            continue

        if kind == "PASTURE":
            animal = t.get("animal")
            if animal is None:
                tasks.append((80, (x, y), ["PLACE", "PASTURE"]))
                continue
            if t.get("yield_units", 0) > 0:
                tasks.append((90, (x, y), ["HARVEST"]))
            if t.get("fertilizer_available"):
                tasks.append((78, (x, y), ["COLLECT_FERTILIZER"]))
            if t.get("fed_today") and not t.get("cared_today"):
                tasks.append((50, (x, y), ["CARE"]))
            continue

    return tasks


def _carried_animal_for(inv, structure_kind):
    for name in ANIMALS:
        if inv.get(name, 0) > 0 and ANIMALS[name]["structure"] == structure_kind:
            return name
    return None


def _assign_tile_tasks(units, tasks, actions, taken, inventories):
    tasks = sorted(tasks, key=lambda t: -t[0])
    for score, pos, action in tasks:
        if pos in taken:
            continue
        verb = action[0]
        idx, best_d = None, None
        for i, u in enumerate(units):
            if actions[i] is not None:
                continue
            if verb == "PLACE":
                inv = inventories[i] if i < len(inventories) else {}
                if _carried_animal_for(inv, action[1]) is None:
                    continue
            d = _manhattan(u, pos)
            if best_d is None or d < best_d:
                idx, best_d = i, d
        if idx is None:
            continue
        if verb == "PLACE":
            action = ["PLACE", _carried_animal_for(inventories[idx], action[1])]
        move = _step_toward(units[idx], pos)
        actions[idx] = move if move else action
        taken.add(pos)


def _agent_impl(obs):
    player = obs.get("player", 0)
    farms = obs.get("farms") or []
    if not farms or player >= len(farms):
        return {"farmer": PASS, "hands": [], "market": []}

    farm = farms[player]
    private = obs.get("private", {}) or {}
    day = obs.get("day", 0)
    board_size = len(farm["tiles"])

    units = [tuple(farm["farmer"])] + [tuple(h) for h in farm.get("hands", [])]
    inventories = private.get("inventories") or [{}]
    shed = private.get("shed", {}) or {}
    actions = [None] * len(units)
    taken = set()

    # Pass 1: any unit carrying a bought animal delivers it to a matching
    # empty structure.
    for i, u in enumerate(units):
        inv = inventories[i] if i < len(inventories) else {}
        for kind, meta in ANIMALS.items():
            if inv.get(kind, 0) > 0:
                spots = [s for s in _empty_structures(farm, meta["structure"]) if s not in taken]
                spot = _nearest(u, spots)
                if spot:
                    move = _step_toward(u, spot)
                    actions[i] = move if move else ["PLACE", kind]
                    taken.add(spot)
                break

    # Pass 2: any unit already carrying wheat feeds the nearest unfed animal.
    unfed = [(x, y) for x, y, t in _iter_tiles(farm)
             if isinstance(t, dict) and t.get("animal") and not t.get("fed_today")]
    for i, u in enumerate(units):
        if actions[i] is not None:
            continue
        inv = inventories[i] if i < len(inventories) else {}
        if inv.get("WHEAT", 0) > 0:
            target = _nearest(u, [a for a in unfed if a not in taken])
            if target:
                move = _step_toward(u, target)
                actions[i] = move if move else ["FEED"]
                taken.add(target)

    # Pass 3: idle unit near the shed picks up a waiting animal or wheat.
    #
    # want_wheat used to be unconditional (any WHEAT in the shed plus any
    # animal anywhere on the farm) - with as few as 1 animal needing 1
    # wheat/day, every idle unit decided it wanted a wheat trip every single
    # turn, and _assign_tile_tasks (Pass 4, where PLANT/HARVEST live) never
    # saw a free unit to give real work to. Confirmed directly (seed 11 vs
    # pass): crops={} through day 9 despite 7 WHEAT + 12 MELON seed already
    # held the whole time - every unit spent every turn on a wheat fetch
    # loop instead of planting. Capped to the actual number of unfed
    # animals not already covered by a carrying unit this turn (`unfed`
    # minus `taken`, from Pass 2 above) - once that's satisfied, remaining
    # idle units fall through to Pass 4.
    wheat_fetchers_needed = len([a for a in unfed if a not in taken])
    shed_tiles = _shed_tiles(board_size)
    for i, u in enumerate(units):
        if actions[i] is not None:
            continue
        inv = inventories[i] if i < len(inventories) else {}
        want_animal = next((k for k, m in ANIMALS.items()
                             if shed.get(k, 0) > 0 and _empty_structures(farm, m["structure"])
                             and inv.get(k, 0) == 0), None)
        want_wheat = (shed.get("WHEAT", 0) > 0 and inv.get("WHEAT", 0) == 0
                      and wheat_fetchers_needed > 0)
        if want_wheat and not want_animal:
            wheat_fetchers_needed -= 1
        if want_animal or want_wheat:
            target = _nearest(u, shed_tiles)
            if target:
                if u == target:
                    actions[i] = (["PICKUP", want_animal, 1] if want_animal
                                  else ["PICKUP", "WHEAT", 2])
                else:
                    actions[i] = _step_toward(u, target)

    # Pass 4: remaining units do tile-bound work.
    remaining_idx = [i for i, a in enumerate(actions) if a is None]
    if remaining_idx:
        tasks = _build_tile_tasks(obs, farm, private, day, board_size)
        sub_units = [units[i] for i in remaining_idx]
        sub_inv = [inventories[i] if i < len(inventories) else {} for i in remaining_idx]
        sub_actions = [None] * len(sub_units)
        _assign_tile_tasks(sub_units, tasks, sub_actions, taken, sub_inv)
        for j, i in enumerate(remaining_idx):
            actions[i] = sub_actions[j]

    # Pass 5: still-idle units carrying something sellable head for the shed.
    for i, a in enumerate(actions):
        if a is not None:
            continue
        inv = inventories[i] if i < len(inventories) else {}
        target = _nearest(units[i], shed_tiles)
        if target and any(inv.get(k, 0) > 0 for k in SELL_BASE):
            actions[i] = (["DROP"] if units[i] == target else _step_toward(units[i], target))
        else:
            actions[i] = (_step_toward(units[i], target) if target else None) or PASS

    return actions


def _wheat_needed(farm):
    return sum(1 for _, _, t in _iter_tiles(farm) if isinstance(t, dict) and t.get("animal"))


def _market_orders(farm, private, day, hour):
    orders = []
    money = farm["money"]
    shed = private.get("shed", {}) or {}
    seeds = private.get("seeds", {}) or {}

    # 1. hire toward the census ramp. Hire cost is a fib sequence (8 hands
    # for $54 total) - trivially cheap next to seed/land/animal spend, so no
    # cash floor here at all: a `money - N` style floor blocks hiring
    # entirely once cash drops below N, which is exactly the stall this
    # opponent hit during testing (money parked at $32 for three weeks
    # straight, budget floored to $0, hires_today stuck at 0 the whole
    # time). Hiring should never be the thing starved for cash.
    if hour == 0:
        target_hands = _target_hands(day)
        hires_today = farm.get("hires_today", 0)
        budget = money
        spent, n = 0, hires_today
        fib_a, fib_b = 1, 1
        for _ in range(n):
            fib_a, fib_b = fib_b, fib_a + fib_b
        while n < target_hands:
            c = fib_a
            if spent + c > budget:
                break
            orders.append(["HIRE"])
            spent += c
            n += 1
            fib_a, fib_b = fib_b, fib_a + fib_b
        money -= spent

    # 2. wheat for feed - protected priority, ahead of seed/land/animal
    # spend, same fix agent/main.py needed (docs/strategy-log.md,
    # "animal-first meta rebuild"). Used to sit after seed-buying (step 3
    # below) with a flat `money > 300` all-or-nothing gate - on a cash-poor
    # day (confirmed: seed 11 vs pass, money $0-44 for a week) that gate
    # never clears, seed-buying (which has no cash floor at all) spends
    # whatever's left first, and every animal on the farm starves and
    # escapes (confirmed: COW+SHEEP both gone by day 9). Moved ahead of
    # seed-buying and changed to buy whatever's affordable toward the need
    # instead of all-or-nothing - losing an already-owned $400-500 animal
    # is a bigger loss than a delayed seed purchase.
    need = _wheat_needed(farm) - shed.get("WHEAT", 0)
    if need > 0 and money > 20:
        buy = min(need, int(money // 5))  # ~$5/unit floor price, backstop only
        if buy > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", buy])
            money -= buy * 5

    # 3. sell, batched (not the full price-impact machinery agent/main.py
    # has - this opponent just needs to be strategically faithful).
    liquidating = day >= 28
    for item, qty in sorted(shed.items(), key=lambda kv: -kv[1]):
        base = SELL_BASE.get(item)
        if not base or qty <= 0:
            continue
        if not liquidating:
            if item == "FERTILIZER" and qty <= 4:
                continue
            if item == "WHEAT":
                qty = max(0, qty - _wheat_needed(farm))
                if qty <= 0:
                    continue
        n = qty if liquidating else min(qty, SELL_BATCH.get(item, 6))
        if n > 0:
            orders.append(["SELL", item, n])

    # 4. seed the target crop mix directly from the census gap - the whole
    # point of this opponent is affording the turn-0 opening (docs/
    # target-plan.md), so no flat capital_reserve gate here at all. Capped
    # by hand capacity though (TILES_PER_UNIT), same fix agent/main.py
    # needed: an uncapped buffer refill outruns how many tiles the current
    # hand count can actually water, and the excess just weeds (confirmed
    # during testing - plants_weeded jumped to 11-13/game without this).
    target = _target_crops(day)
    crop = _crop_to_plant(day, farm, seeds)
    if crop:
        have = _count_crop(farm, crop) + seeds.get(crop, 0)
        n_units = 1 + len(farm.get("hands", []))
        in_flight = sum(seeds.values()) + sum(
            1 for _, _, t in _iter_tiles(farm)
            if isinstance(t, dict) and t.get("kind") == "PLANT"
        )
        capacity = max(0, n_units * TILES_PER_UNIT - in_flight)
        want = min(max(0, target[crop] - have), capacity)
        cost = CROPS[crop]["seed"]
        if want > 0 and money > cost * want:
            orders.append(["BUY_SEED", crop, want])
        elif want > 0 and seeds.get(crop, 0) == 0 and money >= cost:
            orders.append(["BUY_SEED", crop, 1])

    # 5/6. land and animals - hour-gated to once/day. Without this, this
    # function's every-hour cadence buys the whole opening (2 cow + 2 sheep
    # + NE land, $1,800+$1,000) inside the first few hours of day 0, before
    # hiring has any chance to establish hands to work the resulting board -
    # confirmed during testing: money hit exactly $0 for 6+ days straight
    # (day 9-15) with zero hands the whole stretch. Spreading these four
    # purchases across a few hours of day 0 (they still all clear within
    # the first day - the schedule targets them by day 3) leaves room for
    # HIRE and the crop-seed step above to run first each hour.
    #
    # Moving this to hour 4 (tried directly: hire, a real recurring daily
    # cost since `hands` resets to 0 every night - see step 1 - has no cash
    # ceiling and runs first at hour 0, so land/animal often lost the race
    # for whatever was left) was measured and made things *worse*, not
    # better: mean final bank on the probe seed dropped from $55,347 to
    # $5,795 - hands collapsed to 0 for days 9-15, a new and bigger stall.
    # Left at hour 0, unresolved - the animal-growth stall this was meant
    # to fix (COW/SHEEP stuck at 1 each all game even with thousands in the
    # bank) is real and still present, but this specific fix made the
    # bigger number worse. Flagged for Task 2's summary as a known,
    # diagnosed, not-yet-fixed cap rather than risking a regression under
    # time pressure without a proper multi-seed measurement.
    if hour == 0:
        n_extra = len(farm.get("unlocked_quadrants", ["NW"])) - 1
        if n_extra < 2:  # NE, then SW - never SE
            price = LAND_PRICES[n_extra]
            if money > price:
                orders.append(["BUY_LAND"])
                money -= price

        target_animals = _target_animals(day)
        for kind, meta in ANIMALS.items():
            have = _count_animals(farm, kind) + shed.get(kind, 0)
            want = target_animals.get(kind, 0) - have
            if want > 0 and money > meta["cost"]:
                orders.append(["BUY_ANIMAL", kind, 1])
                money -= meta["cost"]

    return orders[:10]


def _agent(obs):
    player = obs.get("player", 0)
    farms = obs.get("farms") or []
    if not farms or player >= len(farms):
        return {"farmer": PASS, "hands": [], "market": []}
    farm = farms[player]
    private = obs.get("private", {}) or {}
    day = obs.get("day", 0)
    hour = obs.get("hour", 0)
    actions = _agent_impl(obs)
    market = _market_orders(farm, private, day, hour)
    return {"farmer": actions[0] if actions else PASS, "hands": actions[1:], "market": market}


def agent(obs):
    try:
        return _agent(obs)
    except Exception:
        farm = (obs.get("farms") or [{}])[obs.get("player", 0)]
        n_hands = len(farm.get("hands", []) or [])
        return {"farmer": PASS, "hands": [PASS] * n_hands, "market": []}
