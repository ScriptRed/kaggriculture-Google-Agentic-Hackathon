"""Guard the transcribed tables against the real environment.

If this fails, the env was updated and agent/constants.py is stale. Fix
constants.py, never the test's expectations.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

import constants as C  # noqa: E402

env_mod = pytest.importorskip(
    "kaggle_environments.envs.kaggriculture.kaggriculture")


def test_crops_match_env():
    assert C.CROPS == env_mod.CROPS


def test_animals_match_env():
    assert C.ANIMALS == env_mod.ANIMALS


def test_products_match_env():
    assert C.PRODUCTS == env_mod.PRODUCTS


def test_shops_match_env():
    assert C.SHOPS == env_mod.SHOPS


def test_land_matches_env():
    assert C.LAND_ORDER == env_mod.LAND_ORDER
    assert C.LAND_PRICES == env_mod.LAND_PRICES


def test_market_params_match_env():
    for item, p in C.MARKET_PARAMS.items():
        e = env_mod.MARKET_PARAMS[item]
        for k in ("base", "T", "below_func", "below_target",
                  "above_func", "above_target"):
            assert p[k] == e[k], f"{item}.{k}"


@pytest.mark.parametrize("item", list(C.MARKET_PARAMS))
@pytest.mark.parametrize("delta", [-2000, -400, -1, 0, 1, 400, 2000, 8000])
def test_price_curve_matches_env(item, delta):
    inv = C.MARKET_I0 + delta
    assert C.market_price(item, inv) == env_mod.market_price(item, inv)


def test_hire_cost_matches_env():
    for n in range(15):
        assert C.hire_cost(n) == env_mod._hire_cost(n)


def test_bonus_window_matches_env_water_logic():
    for crop, cd in C.CROPS.items():
        if cd["ongoing"]:
            assert C.bonus_window(crop) is None
        else:
            assert C.bonus_window(crop) == ((cd["max_yield_day"] + 1) // 2,
                                            cd["max_yield_day"])


def test_melon_needs_no_fertilizer():
    """Melon caps at max_yield unfertilized - fertilizing it is wasted."""
    assert C.expected_yield("MELON", False) == C.CROPS["MELON"]["max_yield"]


def test_wheat_and_carrot_need_fertilizer_for_max():
    for crop in ("WHEAT", "CARROT"):
        assert C.expected_yield(crop, False) < C.CROPS[crop]["max_yield"]
        assert C.expected_yield(crop, True) == C.CROPS[crop]["max_yield"]


# --- town demand -------------------------------------------------------

def test_town_center_products_match_env():
    assert C.TOWN_CENTER_PRODUCTS == env_mod.TOWN_CENTER_PRODUCTS


def test_max_shop_instances_matches_env():
    assert C.MAX_SHOP_INSTANCES == env_mod.MAX_SHOP_INSTANCES


def test_town_center_is_flat_one_per_day():
    """kaggle-environments 1.32.6 (PR #1394) removed the old
    TOWN_CENTER_DEMAND_SCHEDULE day-10/day-20 doubling. Verified against a
    real short episode (no agent action needed - both PASS the whole time,
    isolates the town centre from any shop/player effect since the first
    shop doesn't unlock until day 3): WHEAT inventory should drop by
    exactly 1 unit once per day, every day, days 0-2, matching
    CENTER_SELL_TICKS_PER_DAY == 1 - not the old 2/4/8 escalation."""
    from kaggle_environments import make
    env = make("kaggriculture", configuration={"episodeSteps": 72, "seed": 1},
               debug=True)
    env.run(["pass", "pass"])
    inv = [step[0]["observation"]["market"]["inventory"]["WHEAT"]
           for step in env.steps]
    assert C.MARKET_I0 - inv[24] == 1 * C.CENTER_SELL_TICKS_PER_DAY  # end of day 0
    assert C.MARKET_I0 - inv[48] == 2 * C.CENTER_SELL_TICKS_PER_DAY  # end of day 1
    assert C.CENTER_SELL_TICKS_PER_DAY == 1


def test_melon_has_no_shop_demand():
    """No SHOPS entry lists melon - town centre is its only buyer."""
    assert all("MELON" not in products for products in C.SHOPS.values())


def test_sustainable_rate_melon_is_center_only():
    """Flat 1/day at every point in the season now (no more day-10/day-20
    doubling) - melon's only demand source, and it never grows."""
    for day in [0, 9, 10, 19, 20, 29]:
        assert C.sustainable_rate("MELON", day) == C.CENTER_SELL_TICKS_PER_DAY
        assert C.sustainable_rate("MELON", day, unlocked_shops=list(C.SHOPS)) == \
            C.CENTER_SELL_TICKS_PER_DAY


def test_sustainable_rate_fertilizer_has_no_town_demand():
    assert C.sustainable_rate("FERTILIZER", 25) == 0


def test_sustainable_rate_live_mode_matches_manual_count():
    # One single-product shop (YARN_STORE, wool) and one multi-product shop
    # (FARMERS_MARKET) unlocked; check both shop math and the additive
    # centre term by hand.
    unlocked = ["YARN_STORE", "FARMERS_MARKET"]
    assert C.sustainable_rate("WOOL", 5, unlocked_shops=unlocked) == \
        C.CENTER_SELL_TICKS_PER_DAY * 1 + C.SHOP_SELL_TICKS_PER_DAY * 2
    assert C.sustainable_rate("WHEAT", 5, unlocked_shops=unlocked) == \
        C.CENTER_SELL_TICKS_PER_DAY * 1 + C.SHOP_SELL_TICKS_PER_DAY * 1
    assert C.sustainable_rate("MELON", 5, unlocked_shops=unlocked) == \
        C.CENTER_SELL_TICKS_PER_DAY * 1


def test_sustainable_rate_live_mode_counts_duplicates():
    """A shop drawn twice (with-replacement mechanic) consumes twice -
    each list entry contributes its own rate independently."""
    unlocked = ["YARN_STORE", "YARN_STORE", "YARN_STORE"]
    assert C.sustainable_rate("WOOL", 5, unlocked_shops=unlocked) == \
        C.CENTER_SELL_TICKS_PER_DAY * 1 + 3 * C.SHOP_SELL_TICKS_PER_DAY * 2


def test_planning_rate_at_zero_known_matches_full_season_expectation():
    """No shops unlocked yet (0 known, all MAX_SHOP_INSTANCES remaining):
    planning_rate assumes the full season's worth of draws will
    eventually happen (matches sustainable_rate's expected mode evaluated
    once shops_unlocked_by_day saturates, i.e. day >= 24) - the right
    question for "is this worth planting for its whole lifetime", not "is
    a shop unlocked at this literal instant". "Hedge early" falls out of
    the algebra (full population-average weight when nothing is known
    yet), not a tuned day cutoff.
    """
    for item in ("WHEAT", "STRAWBERRY", "CARROT", "WOOL"):
        assert C.planning_rate(item, []) == pytest.approx(
            C.sustainable_rate(item, day=24))


def test_planning_rate_at_full_known_matches_live_mode():
    """All MAX_SHOP_INSTANCES shops drawn: planning_rate should equal the
    live-exact rate - "specialise once shops reveal", also falling out of
    the algebra (zero remaining slots contribute zero expectation)."""
    unlocked = ["YARN_STORE"] * C.MAX_SHOP_INSTANCES
    for item in ("WHEAT", "WOOL", "STRAWBERRY"):
        assert C.planning_rate(item, unlocked) == pytest.approx(
            C.sustainable_rate(item, day=27, unlocked_shops=unlocked))


def test_planning_rate_is_between_known_and_full_expectation():
    """Partially revealed (some known, some remaining): result should sit
    between "nothing known yet" and "fully known" - a real interpolation,
    not clamped to one end."""
    none_known = C.planning_rate("WOOL", [])
    some_known = C.planning_rate("WOOL", ["YARN_STORE", "YARN_STORE"])
    all_known = C.planning_rate("WOOL", ["YARN_STORE"] * C.MAX_SHOP_INSTANCES)
    assert none_known < some_known < all_known


def test_sustainable_rate_steady_state_matches_full_shop_rate():
    """By day 24, MAX_SHOP_INSTANCES (8) draws have happened in expectation
    (min(8, 24//3) == 8) - in expectation this is the same total shop rate
    as "one of every shop type", even though a real episode may have
    duplicates/gaps now (with-replacement draws)."""
    assert C.shops_unlocked_by_day(24) == C.MAX_SHOP_INSTANCES
    for item in set(C.PRODUCTS) - {"FERTILIZER"}:
        expected_shop = C._item_shop_full_rate(item)
        got_shop = C.sustainable_rate(item, 24) - C.CENTER_SELL_TICKS_PER_DAY
        assert got_shop == pytest.approx(expected_shop)


def _reference_shop_unlock_schedule(seed, n_days=30):
    """Transcribed from kaggriculture.py's `_end_of_day` shop-unlock block
    (the only part of `sustainable_rate`'s expected-mode that isn't a pure
    function of public constants - it depends on the env's per-day RNG).

    kaggle-environments >=1.32.6: drawn WITH replacement, capped at
    MAX_SHOP_INSTANCES total draws (not "one of each") - so the same shop
    can appear more than once. Returns a list of (shop, day_unlocked)
    per draw, not a dict, since a dict keyed by shop name can't represent
    a duplicate.
    """
    import random
    draws = []
    for day in range(n_days):
        next_day = day + 1
        rng = random.Random((seed * 1_000_003) ^ day)
        if next_day > 0 and next_day % C.SHOP_UNLOCK_INTERVAL == 0:
            if len(draws) < C.MAX_SHOP_INSTANCES:
                choice = rng.choice(sorted(C.SHOPS))
                draws.append((choice, next_day))
    return draws


def test_sustainable_rate_expected_mode_matches_monte_carlo_of_env_rng():
    """`sustainable_rate`'s no-`unlocked_shops` mode claims to be the exact
    expectation over the env's per-episode random shop-unlock order, even
    under the new with-replacement draw mechanic (linearity of expectation
    still gives k/len(SHOPS) instances in expectation - see the docstring).
    Verify that claim empirically by simulating the env's own unlock
    algorithm across many seeds, rather than trusting the argument by
    inspection.
    """
    import random as _random
    rng = _random.Random(12345)
    n_trials = 3000
    days_to_check = [0, 3, 9, 15, 21, 27]
    items = ["STRAWBERRY", "WHEAT", "WOOL", "CARROT"]

    totals = {item: {d: 0.0 for d in days_to_check} for item in items}
    for _ in range(n_trials):
        seed = rng.randrange(10**9)
        draws = _reference_shop_unlock_schedule(seed)
        for item in items:
            for d in days_to_check:
                rate = sum(
                    C.SHOP_SELL_TICKS_PER_DAY * C._shop_unit_rate(s)
                    for s, day_unlocked in draws
                    if item in C.SHOPS[s] and day_unlocked <= d
                )
                totals[item][d] += rate

    for item in items:
        for d in days_to_check:
            empirical = totals[item][d] / n_trials
            model = C.sustainable_rate(item, d) - (
                C.CENTER_SELL_TICKS_PER_DAY if item in C.TOWN_CENTER_PRODUCTS else 0)
            assert empirical == pytest.approx(model, abs=0.6), (item, d)


# --- premium price-cliff engine check (notebooks/live-meta) ----------------
#
# Guards against a real, specific failure mode: a kaggle-environments
# upgrade silently shipping different market math. notebooks/live-meta
# flags this directly - "the strawberry price cliff is 62 units in 1.32.x
# but ~247 in other builds" - and embeds its own reference model rather
# than trusting whatever's installed, for exactly this reason. We instead
# pin the expectation here: if a future pip upgrade changes these numbers,
# `test_price_curve_matches_env` (above) will already fail since it checks
# every point against the installed env directly - this test additionally
# pins the four specific "units to hit the $1 floor from I0" figures the
# notebook's own 683-episode/1,366-player ladder analysis was built
# against, so a silent engine change that happens to still pass the
# per-point check can't silently invalidate that calibration too.

def _cliff_units(item):
    inv, sold = C.MARKET_I0, 0
    while C.market_price(item, inv) > 1 and sold < 3000:
        inv += 1
        sold += 1
    return sold


@pytest.mark.parametrize("item,expected", [
    ("STRAWBERRY", 62),
    ("WOOL", 59),
    ("MILK", 76),
    ("MELON", 158),
])
def test_premium_price_cliffs_match_notebook_reference(item, expected):
    assert _cliff_units(item) == expected
