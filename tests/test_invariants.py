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
