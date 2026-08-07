"""animal-heavy: a distinct-strategy pool opponent, not our own lineage.

Built from the ladder-observations.md finding that our own candidate agent
has never completed the animal pipeline (BUY_ANIMAL only reaches the shed;
turning that into a live, producing animal needs BUILD_COOP/BUILD_PASTURE,
PICKUP, and PLACE, none of which agent/main.py issues - see
docs/ladder-observations.md and kaggriculture.py:344-376). This opponent
exists specifically to test that gap: build several coops/pastures, buy and
actually place several geese/cows/sheep, feed and care for them daily,
collect and sell fertilizer, and otherwise ignore crops almost entirely.

Deliberately self-contained: does not import from agent/, which
arena/run.py snapshots per-run so live edits there can't affect this file.
Not a faithful reimplementation of any real ladder agent (we can't see
their code) - a distinct strategic archetype built from verified mechanics.
"""

PASS = ["PASS"]

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP"},
    "COW":   {"cost": 400, "structure": "PASTURE"},
    "SHEEP": {"cost": 500, "structure": "PASTURE"},
}
# One structure tile holds exactly one animal (PLACE replaces the tile with
# the animal outright - kaggriculture.py:363-377). "8 cow" in the meta means
# 8 separate PASTUREs, not one pasture holding 8.
TARGET_COUNTS = {"GOOSE": 3, "COW": 3, "SHEEP": 2}
WHEAT_SEED_COST = 10
WHEAT_MAX_YIELD_DAY = 4
SELL_BASE = {"EGG": 50, "MILK": 160, "WOOL": 200, "FERTILIZER": 100, "WHEAT": 25}
SELL_BATCH = {"EGG": 8, "MILK": 4, "WOOL": 4, "FERTILIZER": 6, "WHEAT": 8}
TARGET_HANDS = 8


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


def _count_animals(farm, kind):
    return sum(1 for _, _, t in _iter_tiles(farm)
               if isinstance(t, dict) and t.get("animal") == kind)


def _empty_structures(farm, structure_kind):
    return [(x, y) for x, y, t in _iter_tiles(farm)
            if isinstance(t, dict) and t.get("kind") == structure_kind and "animal" not in t]


def _build_tile_tasks(obs, farm, private, day, board_size):
    """Tile-bound work: watering/harvesting wheat, feeding/caring/collecting
    from already-placed animals (feed only listed here as a fallback score
    for a unit that happens to already be standing there carrying wheat -
    the main feed routing happens in pass 1 of _agent), building structures.
    PICKUP/PLACE are handled separately (need per-unit carry state).
    """
    tasks = []
    for x, y, t in _iter_tiles(farm):
        if t == "LOCKED":
            continue

        if t is None:
            n_wheat_plants = sum(
                1 for _, _, tt in _iter_tiles(farm)
                if isinstance(tt, dict) and tt.get("kind") == "PLANT" and tt.get("crop") == "WHEAT"
            )
            if n_wheat_plants < 4 and private.get("seeds", {}).get("WHEAT", 0) > 0:
                tasks.append((35, (x, y), ["PLANT", "WHEAT"]))
                continue
            deficit = [(k, TARGET_COUNTS[k] - _count_animals(farm, k)) for k in ANIMALS]
            deficit.sort(key=lambda kv: -kv[1])
            need_kind, need_n = deficit[0]
            if need_n > 0 and not _empty_structures(farm, ANIMALS[need_kind]["structure"]):
                op = "BUILD_COOP" if ANIMALS[need_kind]["structure"] == "COOP" else "BUILD_PASTURE"
                tasks.append((55, (x, y), [op]))
            continue

        if not isinstance(t, dict):
            continue
        kind = t.get("kind")

        if kind == "WEED":
            tasks.append((20, (x, y), ["DIG"]))
            continue

        if kind == "PLANT" and t.get("crop") == "WHEAT":
            age = day - t.get("planted_day", day)
            watered = t.get("watered_today", False)
            unwatered = t.get("consecutive_unwatered", 0)
            units = t.get("yield_units", 0)
            if units > 0 and age >= WHEAT_MAX_YIELD_DAY:
                tasks.append((80, (x, y), ["HARVEST"]))
                continue
            if not watered:
                tasks.append((100, (x, y), ["WATER"]) if unwatered >= 1
                              else (60, (x, y), ["WATER"]))
            continue

        if "animal" in t and t.get("animal"):
            if t.get("yield_units", 0) > 0:
                tasks.append((90, (x, y), ["HARVEST"]))
            if t.get("fertilizer_available"):
                tasks.append((78, (x, y), ["COLLECT_FERTILIZER"]))
            if t.get("fed_today") and not t.get("cared_today"):
                tasks.append((50, (x, y), ["CARE"]))
            continue

    return tasks


def _assign_tile_tasks(units, tasks, actions, taken):
    tasks = sorted(tasks, key=lambda t: -t[0])
    for score, pos, action in tasks:
        if pos in taken:
            continue
        idx, best_d = None, None
        for i, u in enumerate(units):
            if actions[i] is not None:
                continue
            d = _manhattan(u, pos)
            if best_d is None or d < best_d:
                idx, best_d = i, d
        if idx is None:
            continue
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

    # Pass 1: any unit already carrying wheat feeds the nearest unfed animal.
    unfed = [(x, y) for x, y, t in _iter_tiles(farm)
             if isinstance(t, dict) and t.get("animal") and not t.get("fed_today")]
    for i, u in enumerate(units):
        inv = inventories[i] if i < len(inventories) else {}
        if inv.get("WHEAT", 0) > 0:
            target = _nearest(u, [a for a in unfed if a not in taken])
            if target:
                move = _step_toward(u, target)
                actions[i] = move if move else ["FEED"]
                taken.add(target)

    # Pass 2: any unit carrying a bought animal delivers it to a matching
    # empty structure.
    for i, u in enumerate(units):
        if actions[i] is not None:
            continue
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

    # Pass 3: any idle unit near the shed picks up wheat (to feed later) or
    # a waiting animal (to place later). Shed tiles are not single-occupancy
    # (unlike farm tiles) - multiple units may converge on the same one, so
    # this deliberately does not consult/update `taken`.
    shed_tiles = _shed_tiles(board_size)
    for i, u in enumerate(units):
        if actions[i] is not None:
            continue
        inv = inventories[i] if i < len(inventories) else {}
        want_animal = next((k for k, m in ANIMALS.items()
                             if shed.get(k, 0) > 0 and _empty_structures(farm, m["structure"])
                             and inv.get(k, 0) == 0), None)
        # Proactive, not reactive: carry wheat whenever we own any animal at
        # all, not only once one is already visibly hungry - by the time
        # fed_today/consecutive_unfed shows a problem, the 2-day escape
        # clock is already most of the way run out.
        have_any_animal = any(_count_animals(farm, k) > 0 for k in ANIMALS)
        want_wheat = shed.get("WHEAT", 0) > 0 and inv.get("WHEAT", 0) == 0 and have_any_animal
        if want_animal or want_wheat:
            target = _nearest(u, shed_tiles)
            if target:
                if u == target:
                    actions[i] = (["PICKUP", want_animal, 1] if want_animal
                                  else ["PICKUP", "WHEAT", 2])
                else:
                    actions[i] = _step_toward(u, target)

    # Pass 4: remaining units do tile-bound work (water/harvest/care/
    # collect/build/plant/dig).
    remaining_idx = [i for i, a in enumerate(actions) if a is None]
    if remaining_idx:
        tasks = _build_tile_tasks(obs, farm, private, day, board_size)
        sub_units = [units[i] for i in remaining_idx]
        sub_actions = [None] * len(sub_units)
        _assign_tile_tasks(sub_units, tasks, sub_actions, taken)
        for j, i in enumerate(remaining_idx):
            actions[i] = sub_actions[j]

    for i, a in enumerate(actions):
        if a is None:
            target = _nearest(units[i], shed_tiles)
            actions[i] = (_step_toward(units[i], target) if target else None) or PASS

    return actions


def _market_orders(farm, private, day, hour):
    orders = []
    money = farm["money"]
    shed = private.get("shed", {}) or {}
    seeds = private.get("seeds", {}) or {}

    if hour == 0:
        hires_today = farm.get("hires_today", 0)
        budget = min(money * 0.05, max(0, money - 40))
        spent, n = 0, hires_today
        fib_a, fib_b = 1, 1
        for _ in range(n):
            fib_a, fib_b = fib_b, fib_a + fib_b
        while n < TARGET_HANDS:
            c = fib_a
            if spent + c > budget:
                break
            orders.append(["HIRE"])
            spent += c
            n += 1
            fib_a, fib_b = fib_b, fib_a + fib_b
        money -= spent

    for item, qty in shed.items():
        base = SELL_BASE.get(item)
        if not base or qty <= 0:
            continue
        if item == "FERTILIZER" and qty <= 3:
            continue
        n_animals_total = sum(_count_animals(farm, k) for k in ANIMALS)
        wheat_feed_reserve = n_animals_total + 4
        if item == "WHEAT" and qty <= wheat_feed_reserve:
            continue
        n = min(qty, SELL_BATCH.get(item, 6))
        if n > 0:
            orders.append(["SELL", item, n])

    if seeds.get("WHEAT", 0) < 4 and money > WHEAT_SEED_COST * 4 + 300:
        orders.append(["BUY_SEED", "WHEAT", 4 - seeds.get("WHEAT", 0)])

    # Backstop: our own small wheat patch may not keep up with a growing
    # herd's feed needs - top up directly from the market if the shed is
    # running low relative to how many animals need feeding daily.
    n_animals_total = sum(_count_animals(farm, k) for k in ANIMALS)
    if shed.get("WHEAT", 0) < n_animals_total + 2 and money > 300:
        orders.append(["BUY_PRODUCT", "WHEAT", n_animals_total + 4 - shed.get("WHEAT", 0)])

    for kind, target in TARGET_COUNTS.items():
        have = _count_animals(farm, kind) + shed.get(kind, 0)
        cost = ANIMALS[kind]["cost"]
        if have < target and money > cost + 500 and day < 26:
            orders.append(["BUY_ANIMAL", kind, 1])
            money -= cost

    return orders[:10]


def _agent(obs):
    player = obs.get("player", 0)
    farms = obs.get("farms") or []
    if not farms or player >= len(farms):
        return {"farmer": PASS, "hands": [], "market": []}
    farm = farms[player]
    private = obs.get("private", {}) or {}
    actions = _agent_impl(obs)
    market = _market_orders(farm, private, obs.get("day", 0), obs.get("hour", 0))
    return {"farmer": actions[0] if actions else PASS, "hands": actions[1:], "market": market}


def agent(obs):
    try:
        return _agent(obs)
    except Exception:
        farm = (obs.get("farms") or [{}])[obs.get("player", 0)]
        n_hands = len(farm.get("hands", []) or [])
        return {"farmer": PASS, "hands": [PASS] * n_hands, "market": []}
