"""market-dumper: a distinct-strategy pool opponent, not our own lineage.

Two things our own agent deliberately avoids, both worth having in the pool
so we're forced to defend against them instead of just never seeing them:

1. Naive full dumping - sells everything in the shed every turn with no
   price-impact floor and no batch cap, the opposite of our own
   price-impact-aware metered selling. Useful as a control: does naive
   dumping actually cost the *dumper* revenue (economics.md predicts yes,
   for glut-cursed goods), and does it depress prices enough to hurt an
   opponent sharing the same market too?
2. Adversarial targeting - docs/economics.md flags this as a real,
   previously untested angle: "you share a market with your opponent and
   can see their tiles... dumping the product they are about to harvest
   crashes it to $1 for both of you - cheap sabotage if you are not
   invested in that good." This opponent watches the visible opponent farm
   (obs["farms"][other_seat]) for crops near their max yield and, if it
   holds any stock of that same item, dumps it first.

Runs a simple wheat/carrot economy to have something worth dumping and
survive on its own merits, not just as a saboteur.

Deliberately self-contained: does not import from agent/, which
arena/run.py snapshots per-run so live edits there can't affect this file.
Not a faithful reimplementation of any real ladder agent - a distinct
strategic archetype built from verified mechanics.
"""

PASS = ["PASS"]

CROPS = {
    "WHEAT":  {"seed": 10, "max_yield_day": 4, "max_yield": 6},
    "CARROT": {"seed": 20, "max_yield_day": 3, "max_yield": 4},
}
TARGET_HANDS = 8
SELLABLE = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"}


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


def _pick_crop(seeds):
    for crop in ("CARROT", "WHEAT"):
        if seeds.get(crop, 0) > 0:
            return crop
    return "CARROT"


def _build_tasks(obs, farm, private, day, board_size):
    tasks = []
    seeds = private.get("seeds", {}) or {}
    days_left = 30 - day

    for x, y, t in _iter_tiles(farm):
        if t == "LOCKED":
            continue

        if t is None:
            crop = _pick_crop(seeds)
            if days_left >= 4 and seeds.get(crop, 0) > 0:
                tasks.append((40, (x, y), ["PLANT", crop]))
            continue

        if not isinstance(t, dict):
            continue
        kind = t.get("kind")

        if kind == "WEED":
            tasks.append((15, (x, y), ["DIG"]))
            continue

        if kind == "PLANT":
            crop = t["crop"]
            cd = CROPS.get(crop, {"max_yield_day": 4, "max_yield": 6})
            age = day - t.get("planted_day", day)
            watered = t.get("watered_today", False)
            unwatered = t.get("consecutive_unwatered", 0)
            units = t.get("yield_units", 0)

            if units > 0 and age >= cd["max_yield_day"]:
                tasks.append((85, (x, y), ["HARVEST"]))
                continue
            if watered:
                continue
            if unwatered >= 1:
                tasks.append((100, (x, y), ["WATER"]))
            else:
                tasks.append((70, (x, y), ["WATER"]))
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
        if best_d > 0 and score - 6 * best_d < 10:
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


def _opponent_near_harvest_items(obs, my_seat):
    """Items the visible opponent is close to harvesting (>=70% of that
    crop's max_yield already accumulated on a tile) - the sabotage target."""
    farms = obs.get("farms") or []
    opp_seat = 1 - my_seat
    if opp_seat >= len(farms):
        return set()
    opp_farm = farms[opp_seat]
    hot = set()
    for _, _, t in _iter_tiles(opp_farm):
        if isinstance(t, dict):
            if t.get("kind") == "PLANT":
                cd = CROPS.get(t.get("crop"), {"max_yield": 6})
                if t.get("yield_units", 0) >= 0.7 * cd.get("max_yield", 6):
                    hot.add(t["crop"])
            elif t.get("animal") and t.get("yield_units", 0) > 0:
                product = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}.get(t["animal"])
                if product:
                    hot.add(product)
    return hot


def _market_orders(obs, farm, private, day, hour, my_seat):
    orders = []
    money = farm["money"]
    shed = private.get("shed", {}) or {}
    seeds = private.get("seeds", {}) or {}

    if hour == 0:
        hires_today = farm.get("hires_today", 0)
        budget = min(money * 0.05, max(0, money - 50))
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

    # Adversarial dump: whatever the opponent is close to harvesting, if we
    # hold any stock of it, sell it first and completely - no floor, no
    # batch cap. Cheap sabotage when we're not invested in that good.
    hot = _opponent_near_harvest_items(obs, my_seat)
    dumped = set()
    for item in hot:
        qty = shed.get(item, 0)
        if qty > 0:
            orders.append(["SELL", item, qty])
            dumped.add(item)

    # Naive full dump of everything else too - no price-impact floor, no
    # batching. This is the control condition, not just the sabotage.
    for item, qty in shed.items():
        if item in dumped or item not in SELLABLE or qty <= 0:
            continue
        if item == "WHEAT" and qty <= 4:
            continue
        orders.append(["SELL", item, qty])

    crop = _pick_crop(seeds)
    want = 6 - seeds.get(crop, 0)
    cost = CROPS[crop]["seed"]
    if want > 0 and money > cost * want + 200:
        orders.append(["BUY_SEED", crop, want])

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
    market = _market_orders(obs, farm, private, day, hour, player)

    return {"farmer": actions[0] if actions else PASS, "hands": actions[1:], "market": market}


def agent(obs):
    try:
        return _agent_impl(obs)
    except Exception:
        farm = (obs.get("farms") or [{}])[obs.get("player", 0)]
        n_hands = len(farm.get("hands", []) or [])
        return {"farmer": PASS, "hands": [PASS] * n_hands, "market": []}
