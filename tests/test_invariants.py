"""Behavioural invariants the agent must never violate."""
import sys
from pathlib import Path

import pytest
from kaggle_environments import make

ROOT = Path(__file__).resolve().parent.parent
AGENT = str(ROOT / "agent" / "main.py")


@pytest.fixture(scope="module")
def episode():
    env = make("kaggriculture",
               configuration={"episodeSteps": 240, "seed": 11}, debug=True)
    env.run([AGENT, "starter"])
    return env


def test_agent_does_not_error(episode):
    assert episode.steps[-1][0]["status"] == "DONE"


def test_agent_actually_acts(episode):
    """The most common silent failure: everything falls back to PASS."""
    non_pass = 0
    for step in episode.steps:
        a = step[0].get("action") or {}
        if not isinstance(a, dict):
            continue
        for act in [a.get("farmer")] + list(a.get("hands") or []):
            if isinstance(act, list) and act and act[0] != "PASS":
                non_pass += 1
    assert non_pass > 100, f"only {non_pass} non-PASS actions - agent is inert"


def test_agent_earns_something(episode):
    assert episode.steps[-1][0]["observation"]["farms"][0]["money"] > 0


def test_agent_beats_pass():
    env = make("kaggriculture",
               configuration={"episodeSteps": 240, "seed": 11}, debug=True)
    env.run([AGENT, "pass"])
    mine = env.steps[-1][0]["observation"]["farms"][0]["money"]
    theirs = env.steps[-1][0]["observation"]["farms"][1]["money"]
    assert mine > theirs, f"lost to the do-nothing agent: {mine} vs {theirs}"


def _unit_actions(step, seat):
    a = step[seat].get("action") or {}
    if not isinstance(a, dict):
        return []
    out = []
    f = a.get("farmer")
    if f:
        out.append(f)
    out.extend(a.get("hands") or [])
    return out


def _worst_pass_window(steps, seat=0, window=48, max_turn=None):
    """(worst_fraction, turn_index) of the most PASS-heavy `window`-turn
    stretch in an episode, for one seat. `max_turn` caps how far into the
    episode the scan looks (see test_no_extended_stall for why)."""
    end = len(steps) if max_turn is None else min(max_turn, len(steps))
    pass_frac = []
    for step in steps[:end]:
        acts = _unit_actions(step, seat)
        total = len(acts) or 1
        n_pass = sum(1 for a in acts if not (isinstance(a, list) and a and a[0] != "PASS"))
        pass_frac.append(n_pass / total)

    worst, worst_at = 0.0, 0
    for i in range(len(pass_frac) - window + 1):
        frac = sum(pass_frac[i:i + window]) / window
        if frac > worst:
            worst, worst_at = frac, i
    return worst, worst_at


def test_no_extended_stall():
    """Hard floor on activity: no 48-turn (2-day) window may be >90% PASS.

    Guards the specific failure chain confirmed in docs/strategy-log.md
    "Failure modes": private seeds start at 0 for every crop with no free
    stock, so if BUY_SEED never fires (cash stuck below the purchase
    reserve) _build_tasks stays empty forever and every unit PASSes from
    its shed spawn point every turn, with no way back in. That state is a
    silent, un-erroring ladder loss.

    This does NOT reproduce under normal starting money on either v0 or
    current main (both stay well under the 90% floor - see the log for
    numbers) - it is a forward-looking regression guard, not evidence that
    either version currently stalls in real play.

    Scan is capped at turn 648 (day 27): _pick_crop deliberately returns
    None once days_left < 4 so seed money isn't wasted on a crop that can't
    mature. An efficient agent that has already harvested everything by then
    (confirmed: post capital_reserve-trap fix, seed 11 vs starter finishes
    all planting/harvesting by day 27 with 0 plants and 0 animals left in
    play) has nothing left to spend actions on for the last ~3 days - that's
    intentional wind-down, not the unrecoverable-paralysis failure mode this
    test exists to catch, and checking through it would conflate the two.
    """
    env = make("kaggriculture",
               configuration={"episodeSteps": 720, "seed": 11}, debug=True)
    env.run([AGENT, "starter"])
    worst, worst_at = _worst_pass_window(env.steps, max_turn=648)

    assert worst <= 0.90, (
        f"activity floor breached: {worst:.0%} PASS across turns "
        f"{worst_at}-{worst_at + 48} (day {worst_at // 24})"
    )


@pytest.mark.parametrize("starting_money", [400, 500, 800, 1000, 1200, 1500, 2000, 3000])
def test_no_extended_stall_under_cash_pressure(starting_money):
    """The activity floor must hold even when the bank starts scarce.

    Unlike test_no_extended_stall (which never comes close to the 90% floor
    under normal $3000 starting money on either version), this one is a real
    discriminator: it FAILS on the pre-fix agent (capital_reserve=1200 could
    never clear while hiring kept draining cash - permanent PASS, confirmed
    at every value in this list, see docs/strategy-log.md "capital_reserve
    stall trap") and passes after the fix (seed purchases yield their
    reserve once no productive assets exist, and hiring can't spend below
    what the next seed costs).
    """
    env = make("kaggriculture",
               configuration={"episodeSteps": 240, "seed": 11,
                               "startingMoney": starting_money},
               debug=True)
    env.run([AGENT, "pass"])
    worst, worst_at = _worst_pass_window(env.steps)

    assert worst <= 0.90, (
        f"startingMoney={starting_money}: activity floor breached, "
        f"{worst:.0%} PASS across turns {worst_at}-{worst_at + 48}"
    )


# Every verb the env recognises for a unit action (kaggriculture.py's op ==
# dispatch, farmer/hand side) and for a market order (same file, the
# HIRE/BUY_LAND/SELL/BUY_*/PLACE-shed-path branch). DROP and the whole
# BUY_ANIMAL/BUILD_COOP/BUILD_PASTURE/PICKUP/PLACE chain went unimplemented
# for most of this project with nothing catching it - `make test` stayed
# green throughout because nothing asserted these verbs were ever issued,
# only that *some* non-PASS action happened (test_agent_actually_acts) and
# that the agent didn't stall (test_no_extended_stall). Movement
# (NORTH/SOUTH/EAST/WEST) and PASS are excluded: trivially exercised by
# every episode, not interesting to track here.
UNIT_VERBS = {
    "PLANT", "WATER", "HARVEST", "DIG", "DROP", "PICKUP", "PLACE",
    "BUILD_COOP", "BUILD_PASTURE", "FEED", "CARE", "COLLECT_FERTILIZER",
    "FERTILIZE",
}
MARKET_VERBS = {"HIRE", "BUY_LAND", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"}

# Verbs known to be unexercised right now, tracked as a real gap rather than
# silently allowed to regress further - see docs/strategy-log.md. Remove an
# entry here the same commit that makes it fire.
KNOWN_UNCOVERED = {"FERTILIZE"}


def test_every_action_verb_is_exercised():
    """Every verb in the action space must be issued at least once across a
    full game - the class of test that would have caught DROP and the
    BUILD_COOP/PICKUP/PLACE chain going unimplemented (see the Branch 1/
    Branch 2 strategy-log entries). A verb that's never issued is either
    dead code or, as those two were, a mechanic silently worth thousands of
    coins that nothing ever exercises.
    """
    env = make("kaggriculture",
               configuration={"episodeSteps": 720, "seed": 11}, debug=True)
    env.run([AGENT, "starter"])

    seen_unit, seen_market = set(), set()
    for step in env.steps:
        for act in _unit_actions(step, 0):
            if isinstance(act, list) and act:
                seen_unit.add(act[0])
        action = step[0].get("action") or {}
        if isinstance(action, dict):
            for order in action.get("market") or []:
                if isinstance(order, list) and order:
                    seen_market.add(order[0])

    missing = (UNIT_VERBS - seen_unit - KNOWN_UNCOVERED) | (MARKET_VERBS - seen_market)
    assert not missing, f"action verbs never issued in a full game: {sorted(missing)}"

    stale = KNOWN_UNCOVERED & (seen_unit | seen_market)
    assert not stale, (
        f"{sorted(stale)} now fires - remove from KNOWN_UNCOVERED "
        "instead of leaving it excused"
    )
