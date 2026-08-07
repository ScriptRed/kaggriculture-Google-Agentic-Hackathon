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
    hire_cost,
)

PASS = ["PASS"]

# --- tunables. these are the knobs the arena optimises. -------------------
PARAMS = {
    "target_hands": 8,          # hands to hire each morning
    "hand_budget_frac": 0.05,   # ...but never spend more than this of bank
    "sell_floor_frac": 0.65,    # don't sell below this fraction of base price
    "sell_batch_premium": 3,    # max units/turn for premium goods
    "sell_batch_staple": 12,    # max units/turn for wheat/egg
    "seed_buffer": 6,           # keep this many seeds of the active crop
    "capital_reserve": 1200,    # shared cash floor for land/animal/seed spend
    "land_buy_min_day": 10,     # let the crop engine establish before land
    "goose_buy_min_day": 12,    # ...and later still for animals (slower payback)
    "crop_early": "WHEAT",
    "crop_main": "CARROT",
    "goose_target": 4,          # geese to own once affordable
    "fert_reserve": 4,          # fertilizer kept for crops before selling
}

PREMIUM = {"MELON", "STRAWBERRY", "MILK", "WOOL"}


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


def _iter_tiles(farm):
    tiles = farm["tiles"]
    for y, row in enumerate(tiles):
        for x, t in enumerate(row):
            yield x, y, t


# --- task generation -------------------------------------------------------

def _build_tasks(obs, farm, private, day, board_size):
    """Return a list of (score, (x, y), action) candidate tasks."""
    tasks = []
    seeds = private.get("seeds", {}) or {}
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}

    for x, y, t in _iter_tiles(farm):
        if not _unlocked(t):
            continue

        if t is None:
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
                    tasks.append((85 + min(20, value / 25.0), (x, y), ["HARVEST"]))
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

        # animal structures
        if "animal" in t:
            animal = t.get("animal")
            if animal is None:
                # empty coop/pasture: place an animal if we're carrying one
                continue
            a = ANIMALS[animal]
            if t.get("yield_units", 0) > 0:
                tasks.append((88, (x, y), ["HARVEST"]))
            if t.get("fertilizer_available"):
                tasks.append((75, (x, y), ["COLLECT_FERTILIZER"]))
            if not t.get("fed_today"):
                urgency = 100 if t.get("consecutive_unfed", 0) >= 1 else 65
                tasks.append((urgency, (x, y), ["FEED"]))
            elif not t.get("cared_today"):
                tasks.append((45, (x, y), ["CARE"]))

    return tasks


def _pick_crop(farm, seeds, day):
    """Which crop to sow. Early game: wheat (cheap, fast, feeds animals)."""
    days_left = 30 - day
    if days_left < 4:
        return None  # won't mature; don't waste seed money
    if days_left < 6:
        return PARAMS["crop_early"]
    for crop in (PARAMS["crop_main"], PARAMS["crop_early"]):
        if seeds.get(crop, 0) > 0:
            return crop
    return PARAMS["crop_main"]


# --- assignment ------------------------------------------------------------

def _assign(units, tasks, board_size):
    """Greedy: best task first, to its nearest free unit."""
    actions = [None] * len(units)
    tasks = sorted(tasks, key=lambda t: -t[0])
    taken_tiles = set()

    for score, pos, action in tasks:
        if pos in taken_tiles:
            continue
        best_i, best_d = None, None
        for i, u in enumerate(units):
            if actions[i] is not None:
                continue
            d = _manhattan(u, pos)
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        if best_i is None:
            break
        # discount tasks that are far away; a 6-move trip for a low-value task
        # is worse than doing something local
        if best_d > 0 and score - 6 * best_d < 10:
            continue
        move = _step_toward(units[best_i], pos)
        actions[best_i] = move if move else action
        taken_tiles.add(pos)

    shed = _shed_tiles(board_size)
    for i, a in enumerate(actions):
        if a is None:
            # idle unit: walk to the shed so it's central for next turn
            target = min(shed, key=lambda s: _manhattan(units[i], s))
            actions[i] = _step_toward(units[i], target) or PASS
    return actions


# --- market ----------------------------------------------------------------

def _market_orders(obs, farm, private, day, hour):
    orders = []
    money = farm["money"]
    shed = private.get("shed", {}) or {}
    seeds = private.get("seeds", {}) or {}
    inv = (obs.get("market", {}) or {}).get("inventory", {}) or {}
    hires_today = farm.get("hires_today", 0)

    # 1. hire at the start of the day - actions are the constraint
    if hour == 0:
        budget = min(money * PARAMS["hand_budget_frac"], money - 50)
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

    # 2. sell, price-impact aware
    for item, qty in sorted(shed.items(), key=lambda kv: -kv[1]):
        if qty <= 0 or item not in MARKET_PARAMS:
            continue
        if item == "FERTILIZER" and qty <= PARAMS["fert_reserve"]:
            continue
        if item == "WHEAT":
            qty = max(0, qty - _wheat_needed(farm))
            if qty <= 0:
                continue
        cap = PARAMS["sell_batch_premium"] if item in PREMIUM else PARAMS["sell_batch_staple"]
        n = min(qty, cap)
        base = MARKET_PARAMS[item]["base"]
        floor = base * PARAMS["sell_floor_frac"]
        cur_inv = inv.get(item, 10000)
        while n > 0 and marginal_price_after(item, cur_inv, n) < floor:
            n -= 1
        if n > 0:
            orders.append(["SELL", item, n])

    # 3. keep seeds stocked
    crop = _pick_crop(farm, seeds, day)
    if crop:
        want = PARAMS["seed_buffer"] - seeds.get(crop, 0)
        cost = CROPS[crop]["seed"]
        if want > 0 and money > cost * want + PARAMS["capital_reserve"]:
            orders.append(["BUY_SEED", crop, want])

    # 4. buy wheat to feed animals if we're short
    need = _wheat_needed(farm) - shed.get("WHEAT", 0)
    if need > 0 and money > 400:
        price = market_price("WHEAT", inv.get("WHEAT", 10000))
        if money > price * need + 300:
            orders.append(["BUY_PRODUCT", "WHEAT", need])

    # 5. land, then geese
    n_extra = len(farm.get("unlocked_quadrants", ["NW"])) - 1
    if n_extra < len(LAND_PRICES):
        price = LAND_PRICES[n_extra]
        if (money > price + PARAMS["capital_reserve"]
                and PARAMS["land_buy_min_day"] <= day < 22):
            orders.append(["BUY_LAND"])
            money -= price

    n_geese = _count_animals(farm, "GOOSE")
    if n_geese < PARAMS["goose_target"] and PARAMS["goose_buy_min_day"] <= day < 24:
        if money > ANIMALS["GOOSE"]["cost"] + PARAMS["capital_reserve"]:
            orders.append(["BUY_ANIMAL", "GOOSE", 1])

    return orders[:10]  # maxMarketOrdersPerTurn


def _wheat_needed(farm):
    return sum(1 for _, _, t in _iter_tiles(farm)
               if isinstance(t, dict) and t.get("animal"))


def _count_animals(farm, animal):
    return sum(1 for _, _, t in _iter_tiles(farm)
               if isinstance(t, dict) and t.get("animal") == animal)


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
    tasks = _build_tasks(obs, farm, private, day, board_size)
    actions = _assign(units, tasks, board_size)
    market = _market_orders(obs, farm, private, day, hour)

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
