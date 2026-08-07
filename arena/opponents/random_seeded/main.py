"""Deterministic stand-in for kaggle_environments' built-in `random_agent`.

The built-in random_agent (kaggriculture.py:1013) constructs `random.Random()`
fresh on every call, seeded from OS entropy - not reproducible given a fixed
episode seed. Confirmed empirically: two identical arena runs against it
produced different banks on all 24 episodes while every other opponent
(`starter`, our own agent) was bit-for-bit identical. See docs/strategy-log.md
"Arena determinism and noise-floor audit".

This opponent replicates random_agent's action distribution but derives its
RNG deterministically from the episode seed, the turn, and the seat, so two
runs with the same seed produce bit-identical opponent behaviour.

kaggle_environments clears configuration["seed"] before any agent (built-in
or custom) ever sees it - verified empirically, not assumed - so the seed
can't be read from `obs` or `config` here. arena/run.py instead injects it
via the KAGGRI_ARENA_SEED environment variable immediately before each
episode's env.run() call.

Deliberately self-contained: does not import from agent/, which arena/run.py
snapshots to an isolated temp dir per run specifically so opponents can't be
affected by concurrent edits to the live working tree (see _snapshot_agent_dir
in arena/run.py). A hard dependency on the live agent/ directory here would
defeat that.
"""

import os
import random

# Mirrors agent/constants.py CROPS[...]["seed"] (verified against the env
# source by tests/test_constants.py). Kept as a static literal rather than
# imported, per the self-containment note above.
CROP_SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}

FARMER_OPS = ["NORTH", "SOUTH", "EAST", "WEST", "WATER", "HARVEST", "PASS"]


def _rng_for(obs):
    base_seed = int(os.environ.get("KAGGRI_ARENA_SEED", "0"))
    step = int(obs.get("step", 0) or 0)
    player = int(obs.get("player", 0) or 0)
    # Same combination style as the env's own per-day RNG (kaggriculture.py
    # _end_of_day: `random.Random((seed * 1_000_003) ^ day)`) - deterministic
    # integer mixing only, no hash() (str/bytes hashing is randomized per
    # process by default and would silently break reproducibility).
    material = (base_seed * 1_000_003) ^ (step * 97_531) ^ (player * 7)
    return random.Random(material)


def agent(obs):
    rng = _rng_for(obs)
    farms = obs.get("farms", [])
    player = obs.get("player", 0)
    private = obs.get("private", {}) or {}
    farm = farms[player] if farms and player < len(farms) else None
    if farm is None:
        return {"farmer": ["PASS"], "hands": [], "market": []}

    market = []
    seeds = private.get("seeds", {}) or {}

    affordable = [c for c in CROP_SEED_COST if CROP_SEED_COST[c] <= farm["money"]]
    if affordable and rng.random() < 0.1:
        market.append(["BUY_SEED", rng.choice(affordable), 1])

    available_seeds = [c for c, n in seeds.items() if n > 0]
    if available_seeds and rng.random() < 0.3:
        farmer = ["PLANT", rng.choice(available_seeds)]
    else:
        farmer = [rng.choice(FARMER_OPS)]

    hands_actions = [[rng.choice(FARMER_OPS)] for _ in farm.get("hands", [])]
    return {"farmer": farmer, "hands": hands_actions, "market": market}
