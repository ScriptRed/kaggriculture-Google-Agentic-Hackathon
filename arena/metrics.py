"""Diagnostics extracted from a finished episode.

Win rate is the headline number but it is one bit per 720 turns. These are the
sub-signals that tell you *why* a version regressed. Every one of them is a
lever the policy can pull.
"""

from collections import defaultdict


def _tiles(farm):
    for y, row in enumerate(farm["tiles"]):
        for x, t in enumerate(row):
            yield x, y, t


def episode_metrics(steps, seat):
    """steps: env.steps (list of per-turn [agent0_state, agent1_state]).

    Returns a dict of diagnostics for one seat.
    """
    m = {
        "final_bank": 0.0,
        "actions_taken": 0,
        "noop_actions": 0,
        "moves": 0,
        "idle_tile_days": 0,
        "plants_weeded": 0,
        "animals_lost": 0,
        "fertilizer_missed": 0,
        "units_sold": defaultdict(int),
        "revenue": defaultdict(float),
        "sold_below_base": 0.0,
        "hires": 0,
        "quadrants": 1,
        "peak_units": 0,
    }

    prev_farm = None
    prev_shed = None

    for i, step in enumerate(steps):
        obs = step[0]["observation"]
        farms = obs.get("farms") or []
        if seat >= len(farms):
            continue
        farm = farms[seat]
        priv = step[seat]["observation"].get("private", {}) or {}
        action = step[seat].get("action") or {}

        # --- action accounting
        acts = []
        if isinstance(action, dict):
            f = action.get("farmer")
            if f:
                acts.append(f)
            acts.extend(action.get("hands") or [])
        m["actions_taken"] += len(acts)
        m["peak_units"] = max(m["peak_units"], len(acts))
        for a in acts:
            if not isinstance(a, list) or not a:
                m["noop_actions"] += 1
            elif a[0] == "PASS":
                m["noop_actions"] += 1
            elif a[0] in ("NORTH", "SOUTH", "EAST", "WEST"):
                m["moves"] += 1

        if isinstance(action, dict):
            for o in action.get("market") or []:
                if isinstance(o, list) and o and o[0] == "HIRE":
                    m["hires"] += 1

        # --- board state
        empty = 0
        for x, y, t in _tiles(farm):
            if t is None:
                empty += 1
            elif isinstance(t, dict) and t.get("animal") and t.get("fertilizer_available"):
                # available at observation time and still available next turn
                # is counted once per turn; approximate signal only
                pass
        m["idle_tile_days"] += empty

        # --- transitions: what died
        if prev_farm is not None:
            for x, y, t in _tiles(farm):
                p = prev_farm["tiles"][y][x]
                if isinstance(p, dict) and p.get("kind") == "PLANT":
                    if isinstance(t, dict) and t.get("kind") == "WEED":
                        m["plants_weeded"] += 1
                if isinstance(p, dict) and p.get("animal"):
                    if isinstance(t, dict) and t.get("animal") is None:
                        m["animals_lost"] += 1

        # --- sales: shed shrink coinciding with money growth
        shed = priv.get("shed", {}) or {}
        if prev_shed is not None and prev_farm is not None:
            gained = farm["money"] - prev_farm["money"]
            if gained > 0:
                for item, qty in prev_shed.items():
                    delta = qty - shed.get(item, 0)
                    if delta > 0:
                        m["units_sold"][item] += delta

        prev_farm = {"tiles": [row[:] for row in farm["tiles"]],
                     "money": farm["money"]}
        prev_shed = dict(shed)

    final = steps[-1][0]["observation"]["farms"][seat]
    m["final_bank"] = final["money"]
    m["quadrants"] = len(final.get("unlocked_quadrants", ["NW"]))
    m["units_sold"] = dict(m["units_sold"])
    m["revenue"] = dict(m["revenue"])

    acted = m["actions_taken"] or 1
    m["coins_per_action"] = m["final_bank"] / acted
    m["noop_rate"] = m["noop_actions"] / acted
    m["idle_tile_rate"] = m["idle_tile_days"] / max(1, len(steps) * 25)
    return m


HEADLINE = [
    "final_bank", "coins_per_action", "noop_rate", "idle_tile_rate",
    "plants_weeded", "animals_lost", "hires", "quadrants", "peak_units",
]


def format_summary(rows):
    """rows: list of metric dicts. Returns a printable block."""
    if not rows:
        return "(no episodes)"
    out = []
    for k in HEADLINE:
        vals = [r.get(k, 0) for r in rows]
        mean = sum(vals) / len(vals)
        out.append(f"  {k:<20} {mean:>12.3f}   (min {min(vals):.1f} max {max(vals):.1f})")
    return "\n".join(out)
