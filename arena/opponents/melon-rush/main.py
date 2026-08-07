"""melon-rush: a distinct-strategy pool opponent, not our own lineage.

Built from the notebooks' and our own replay evidence's "melon IPO" cluster:
melon is the single highest profit/tile-day crop by a wide margin (~118,
vs ~22-28 for wheat/carrot/strawberry - independently re-derived in
docs/meta-analysis.md), but only if watered every single day of the bonus
window (age 6-12; missing days silently caps yield well under the 6-unit
max). Two real ladder opponents in our own replays (docs/ladder-
observations.md) beat us this way with 22-33% of their actions spent on
WATER against our 6.6-8.6% in the same games. This opponent is built to
never miss a melon water-day, and otherwise ignores animals entirely.

Deliberately self-contained: does not import from agent/, which
arena/run.py snapshots per-run so live edits there can't affect this file.
Not a faithful reimplementation of any real ladder agent (we can't see
their code) - a distinct strategic archetype built from verified mechanics.
"""

PASS = ["PASS"]

MELON_SEED_COST = 80
MELON_MAX_YIELD_DAY = 12
MELON_BONUS_START = (MELON_MAX_YIELD_DAY + 1) // 2  # 6
MELON_MAX_YIELD = 6
MELON_BASE_PRICE = 250
LAND_PRICES = [1000, 2000, 4000]
TARGET_HANDS = 10
SELL_BATCH = 5
SELL_FLOOR_FRAC = 0.55


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


def _iter_tiles(farm):
    for y, row in enumerate(farm["tiles"]):
        for x, t in enumerate(row):
            yield x, y, t


def _build_tasks(obs, farm, private, day, board_size):
    tasks = []
    seeds = private.get("seeds", {}) or {}
    days_left = 30 - day

    for x, y, t in _iter_tiles(farm):
        if t == "LOCKED":
            continue

        if t is None:
            # Melon takes 12 days to fully mature - stop planting once it
            # can't finish, same rule our own agent uses for its crop.
            if days_left >= MELON_MAX_YIELD_DAY and seeds.get("MELON", 0) > 0:
                tasks.append((40, (x, y), ["PLANT", "MELON"]))
            continue

        if not isinstance(t, dict):
            continue
        kind = t.get("kind")

        if kind == "WEED":
            tasks.append((15, (x, y), ["DIG"]))
            continue

        if kind == "PLANT" and t.get("crop") == "MELON":
            age = day - t.get("planted_day", day)
            watered = t.get("watered_today", False)
            unwatered = t.get("consecutive_unwatered", 0)
            units = t.get("yield_units", 0)

            if units > 0 and age >= MELON_MAX_YIELD_DAY:
                value = units * MELON_BASE_PRICE
                tasks.append((85 + min(20, value / 50.0), (x, y), ["HARVEST"]))
                continue
            if watered:
                continue
            # Never miss a bonus-window water day - this is the whole
            # point of this opponent. Score above every other task type.
            if MELON_BONUS_START <= age <= MELON_MAX_YIELD_DAY:
                tasks.append((120, (x, y), ["WATER"]))
            elif unwatered >= 1:
                tasks.append((110, (x, y), ["WATER"]))  # pre-window: survival only
            continue

    return tasks


def _assign(units, tasks, board_size):
    actions = [None] * len(units)
    tasks = sorted(tasks, key=lambda t: -t[0])
    taken = set()

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
            break
        # Watering inside the melon bonus window is worth almost any walk -
        # unlike a generic distance discount, do not throttle it.
        if action[0] != "WATER" and best_d > 0 and score - 6 * best_d < 10:
            continue
        move = _step_toward(units[idx], pos)
        actions[idx] = move if move else action
        taken.add(pos)

    shed = _shed_tiles(board_size)
    for i, a in enumerate(actions):
        if a is None:
            target = min(shed, key=lambda s: _manhattan(units[i], s))
            actions[i] = _step_toward(units[i], target) or PASS
    return actions


def _market_orders(farm, private, day, hour):
    orders = []
    money = farm["money"]
    shed = private.get("shed", {}) or {}
    seeds = private.get("seeds", {}) or {}
    inv = {}

    if hour == 0:
        hires_today = farm.get("hires_today", 0)
        budget = min(money * 0.06, max(0, money - 160))
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

    melon_qty = shed.get("MELON", 0)
    if melon_qty > 0:
        n = min(melon_qty, SELL_BATCH)
        if n > 0:
            orders.append(["SELL", "MELON", n])

    days_left = 30 - day
    want = 6 - seeds.get("MELON", 0)
    if want > 0 and days_left >= MELON_MAX_YIELD_DAY and money > MELON_SEED_COST * want + 400:
        orders.append(["BUY_SEED", "MELON", want])

    n_extra = len(farm.get("unlocked_quadrants", ["NW"])) - 1
    if n_extra < len(LAND_PRICES):
        price = LAND_PRICES[n_extra]
        if money > price + 500 and day < 20:
            orders.append(["BUY_LAND"])

    return orders[:10]


def _agent_impl(obs):
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
    tasks = _build_tasks(obs, farm, private, day, board_size)
    actions = _assign(units, tasks, board_size)
    market = _market_orders(farm, private, day, hour)

    return {"farmer": actions[0] if actions else PASS, "hands": actions[1:], "market": market}


def agent(obs):
    try:
        return _agent_impl(obs)
    except Exception:
        farm = (obs.get("farms") or [{}])[obs.get("player", 0)]
        n_hands = len(farm.get("hands", []) or [])
        return {"farmer": PASS, "hands": [PASS] * n_hands, "market": []}
