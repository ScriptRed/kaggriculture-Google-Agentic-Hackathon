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
    """
    env = make("kaggriculture",
               configuration={"episodeSteps": 720, "seed": 11}, debug=True)
    env.run([AGENT, "starter"])
    steps = env.steps

    window = 48
    pass_frac = []
    for step in steps:
        acts = _unit_actions(step, 0)
        total = len(acts) or 1
        n_pass = sum(1 for a in acts if not (isinstance(a, list) and a and a[0] != "PASS"))
        pass_frac.append(n_pass / total)

    worst, worst_at = 0.0, 0
    for i in range(len(pass_frac) - window + 1):
        frac = sum(pass_frac[i:i + window]) / window
        if frac > worst:
            worst, worst_at = frac, i

    assert worst <= 0.90, (
        f"activity floor breached: {worst:.0%} PASS across turns "
        f"{worst_at}-{worst_at + window} (day {worst_at // 24})"
    )
