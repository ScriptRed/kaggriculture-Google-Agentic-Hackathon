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
