"""Game tables, transcribed from the kaggle_environments kaggriculture source.

Verified against the installed environment by tests/test_constants.py.
Do not edit without re-running `make test`.
"""

import math

CROPS = {
    "WHEAT":      {"seed": 10,  "first_yield_day": 2,  "max_yield_day": 4,  "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20,  "first_yield_day": 2,  "max_yield_day": 3,  "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50,  "first_yield_day": 8,  "max_yield_day": 8,  "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80,  "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER"]

MARKET_I0 = 10000
PRICE_FLOOR = 1

MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "T": 450, "below_func": "log",    "below_target": 0.20, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "T": 332, "below_func": "linear", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}

LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]
FARM_HAND_COST_MULT = 1

SHOPS = {
    "BAKERY":         ["EGG", "WHEAT"],
    "PIZZA_SHOP":     ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT":    ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE":     ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE":       ["CARROT"],
    "SMOOTHIE_SHOP":  ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}

CROP_PRODUCTS = set(CROPS)
ANIMAL_PRODUCTS = {a["product"] for a in ANIMALS.values()}


# --- price model -----------------------------------------------------------

def _shape(func, x):
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    return x


def market_price(item, inventory):
    """Replicate the env's price curve so we can simulate our own impact."""
    p = MARKET_PARAMS[item]
    base, T = p["base"], p["T"]
    delta = inventory - MARKET_I0
    if delta == 0:
        return base
    if delta < 0:
        func, target, sign = p["below_func"], p["below_target"], 1
    else:
        func, target, sign = p["above_func"], p["above_target"], -1
    denom = _shape(func, T)
    amp = (target * base / denom) if denom else 0.0
    price = base + sign * amp * _shape(func, abs(delta))
    return max(PRICE_FLOOR, round(price))


def sale_proceeds(item, inventory, qty):
    """Coins from selling `qty` units one at a time, with price impact.

    The env quotes the sell price at pre-sell inventory, then adds the unit.
    Concurrency with the opponent is ignored here - this is a lower bound on
    price and therefore a safe estimate.
    """
    total = 0
    inv = inventory
    for _ in range(qty):
        price = market_price(item, inv)
        total += price
        if price > PRICE_FLOOR:
            inv += 1
    return total, inv


def marginal_price_after(item, inventory, qty):
    """Price we'd receive on the *last* unit if we dumped `qty` now."""
    inv = inventory
    price = market_price(item, inv)
    for _ in range(max(0, qty - 1)):
        if price > PRICE_FLOOR:
            inv += 1
        price = market_price(item, inv)
    return price


# --- derived planting helpers ---------------------------------------------

def bonus_window(crop):
    """(start_age, end_age) inclusive during which WATER adds yield.

    Only meaningful for one-time crops; ongoing crops return None.
    """
    cd = CROPS[crop]
    if cd["ongoing"]:
        return None
    return ((cd["max_yield_day"] + 1) // 2, cd["max_yield_day"])


def expected_yield(crop, fertilized=False):
    """Units harvested from a perfectly watered one-time crop."""
    cd = CROPS[crop]
    if cd["ongoing"]:
        return cd["max_yield"]
    start, end = bonus_window(crop)
    per_day = 2 if fertilized else 1
    return min(cd["max_yield"], 1 + per_day * (end - start + 1))


def harvest_age(crop, fertilized=False):
    """Earliest age at which the crop has reached its capped yield."""
    cd = CROPS[crop]
    if cd["ongoing"]:
        return cd["first_yield_day"]
    start, end = bonus_window(crop)
    per_day = 2 if fertilized else 1
    units = 1
    for age in range(start, end + 1):
        units = min(cd["max_yield"], units + per_day)
        if units >= cd["max_yield"]:
            return age
    return end


def fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def hire_cost(hires_today, mult=FARM_HAND_COST_MULT):
    return mult * fib(hires_today)


def cumulative_hire_cost(n, mult=FARM_HAND_COST_MULT):
    return sum(hire_cost(i, mult) for i in range(n))
