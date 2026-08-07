#!/usr/bin/env python3
"""Extract strategic signal from Kaggriculture ladder replay JSON.

    python arena/analyse_replay.py replays/episode-90746013-replay.json
    python arena/analyse_replay.py --all replays --seats replays/my_seats.csv --json out.json

Each replay is read and reduced to a compact summary dict before the next
one loads - files run 10-16MB each (~92MB for all seven), so nothing here
holds more than one full replay in memory at a time.

Which farm is "ours" must come from replays/my_seats.csv (or --my-seat for a
single file) - do not guess. `_load_seats` tolerates a leaked terminal
escape-sequence prefix found on that file's first line (see
docs/strategy-log.md "notebook and replay ingestion") by extracting
(episode_id, seat) pairs with a regex instead of a line-oriented CSV parse.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.constants import MARKET_PARAMS  # noqa: E402


def load_seats(csv_path):
    """{episode_id: our_seat}, robust to leaked escape-sequence garbage."""
    text = Path(csv_path).read_text(errors="replace")
    return {int(m.group(1)): int(m.group(2))
            for m in re.finditer(r"(\d+),([01])\b", text)}


def _crop_animal_mix(farm):
    crops, animals = Counter(), Counter()
    for row in farm["tiles"]:
        for t in row:
            if isinstance(t, dict):
                if t.get("kind") == "PLANT":
                    crops[t["crop"]] += 1
                elif t.get("animal"):
                    animals[t["animal"]] += 1
    return crops, animals


def analyse_replay(path, my_seat):
    """One replay -> a compact dict. Reads the file once; nothing about the
    raw `steps` list survives past this call."""
    with open(path) as f:
        data = json.load(f)

    steps = data["steps"]
    turns_per_day = data["configuration"].get("turnsPerDay", 24)
    opp_seat = 1 - my_seat
    team_names = data["info"]["TeamNames"]
    seats = {"mine": my_seat, "opp": opp_seat}

    out = {
        "episode_id": data["info"]["EpisodeId"],
        "my_seat": my_seat,
        "team": {"mine": team_names[my_seat], "opp": team_names[opp_seat]},
        "final_reward": {"mine": data["rewards"][my_seat], "opp": data["rewards"][opp_seat]},
        "won": data["rewards"][my_seat] > data["rewards"][opp_seat],
        "bank_by_day": {"mine": [], "opp": []},
        "hands_by_day": {"mine": [], "opp": []},
        "crop_mix_by_day": {"mine": [], "opp": []},
        "animal_mix_by_day": {"mine": [], "opp": []},
        "hires_per_day": {"mine": defaultdict(int), "opp": defaultdict(int)},
        "land_buy_days": {"mine": [], "opp": []},
        "sells": {"mine": defaultdict(list), "opp": defaultdict(list)},
        "action_counts": {"mine": Counter(), "opp": Counter()},
        "market_op_counts": {"mine": Counter(), "opp": Counter()},
        "drop_actions": {"mine": 0, "opp": 0},
        "final_crop_mix": {}, "final_animal_mix": {}, "final_land": {}, "final_hands": {},
    }

    # Sample day-level snapshots at hour 1, not hour 0: hands reset to 0 at
    # the day boundary and are re-hired within hour 0's own action, so hour 0
    # is a stale-zero artifact, not a representative snapshot (see
    # docs/strategy-log.md "capital_reserve stall trap" for how this exact
    # off-by-one confused an earlier debugging session).
    SNAPSHOT_HOUR = 1

    for t, step in enumerate(steps):
        day = t // turns_per_day
        hour = t % turns_per_day
        prices_now = step[0]["observation"].get("market", {}).get("prices", {})
        for label, seat in seats.items():
            obs = step[seat]["observation"]
            farm = obs["farms"][seat]
            action = step[seat].get("action") or {}

            acts = []
            fa = action.get("farmer")
            if fa:
                acts.append(fa)
            acts.extend(action.get("hands") or [])
            for a in acts:
                op = a[0] if isinstance(a, list) and a else "PASS"
                out["action_counts"][label][op] += 1
                if op == "DROP":
                    out["drop_actions"][label] += 1

            for order in action.get("market") or []:
                if not (isinstance(order, list) and order):
                    continue
                op = order[0]
                out["market_op_counts"][label][op] += 1
                if op == "HIRE":
                    out["hires_per_day"][label][day] += 1
                elif op == "BUY_LAND":
                    out["land_buy_days"][label].append(day)
                elif op == "SELL" and len(order) >= 3:
                    item, qty = order[1], order[2]
                    out["sells"][label][item].append({
                        "day": day, "qty": qty,
                        "price_at_order": prices_now.get(item),
                        "base": MARKET_PARAMS.get(item, {}).get("base"),
                    })

            if hour == SNAPSHOT_HOUR:
                out["bank_by_day"][label].append(farm["money"])
                out["hands_by_day"][label].append(len(farm.get("hands") or []))
                crops, animals = _crop_animal_mix(farm)
                out["crop_mix_by_day"][label].append(dict(crops))
                out["animal_mix_by_day"][label].append(dict(animals))

    final_step = steps[-1]
    for label, seat in seats.items():
        farm = final_step[seat]["observation"]["farms"][seat]
        crops, animals = _crop_animal_mix(farm)
        out["final_crop_mix"][label] = dict(crops)
        out["final_animal_mix"][label] = dict(animals)
        out["final_land"][label] = sorted(farm.get("unlocked_quadrants") or [])
        out["final_hands"][label] = len(farm.get("hands") or [])

    for label in ("mine", "opp"):
        out["hires_per_day"][label] = dict(out["hires_per_day"][label])
        out["sells"][label] = dict(out["sells"][label])
        out["action_counts"][label] = dict(out["action_counts"][label])
        out["market_op_counts"][label] = dict(out["market_op_counts"][label])

    return out


def format_summary(r):
    lines = []
    tag = "WIN" if r["won"] else "LOSS"
    lines.append(f"episode {r['episode_id']}  seat {r['my_seat']}  "
                  f"{r['team']['mine']} vs {r['team']['opp']}  -> {tag}")
    lines.append(f"  final reward: mine={r['final_reward']['mine']:,.0f}  "
                 f"opp={r['final_reward']['opp']:,.0f}")
    lines.append(f"  final hands: mine={r['final_hands']['mine']}  opp={r['final_hands']['opp']}")
    lines.append(f"  final land: mine={r['final_land']['mine']}  opp={r['final_land']['opp']}")
    lines.append(f"  final crops: mine={r['final_crop_mix']['mine']}  opp={r['final_crop_mix']['opp']}")
    lines.append(f"  final animals: mine={r['final_animal_mix']['mine']}  opp={r['final_animal_mix']['opp']}")
    lines.append(f"  DROP actions issued: mine={r['drop_actions']['mine']}  opp={r['drop_actions']['opp']}")
    total_mine = sum(r["action_counts"]["mine"].values()) or 1
    total_opp = sum(r["action_counts"]["opp"].values()) or 1
    lines.append("  action distribution (mine -> opp):")
    all_ops = sorted(set(r["action_counts"]["mine"]) | set(r["action_counts"]["opp"]))
    for op in all_ops:
        m = r["action_counts"]["mine"].get(op, 0) / total_mine
        o = r["action_counts"]["opp"].get(op, 0) / total_opp
        lines.append(f"    {op:10s} {m:6.1%}  ->  {o:6.1%}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay", nargs="?", help="single replay JSON path")
    ap.add_argument("--all", metavar="DIR", help="process every *-replay.json in DIR")
    ap.add_argument("--seats", default=str(ROOT / "replays" / "my_seats.csv"))
    ap.add_argument("--my-seat", type=int, choices=(0, 1),
                     help="override the seat for a single --replay run instead of looking it up")
    ap.add_argument("--json", default=None, help="write all per-episode summaries here")
    args = ap.parse_args()

    if args.all:
        seat_map = load_seats(args.seats)
        paths = sorted(Path(args.all).glob("*-replay.json"))
        if not paths:
            raise SystemExit(f"no *-replay.json files found in {args.all}")
        results = []
        for p in paths:
            m = re.search(r"episode-(\d+)-replay", p.name)
            if not m:
                print(f"skip {p.name}: can't parse episode id from filename")
                continue
            eid = int(m.group(1))
            if eid not in seat_map:
                print(f"skip {p.name}: episode {eid} not in {args.seats}")
                continue
            print(f"[{len(results)+1}/{len(paths)}] {p.name} (seat {seat_map[eid]})")
            r = analyse_replay(p, seat_map[eid])
            results.append(r)
            print(format_summary(r))
            print()
        if args.json:
            Path(args.json).write_text(json.dumps(results, indent=2, default=str))
            print(f"wrote {args.json}")
        return 0

    if not args.replay:
        raise SystemExit("pass a replay path or --all DIR")
    seat = args.my_seat
    if seat is None:
        seat_map = load_seats(args.seats)
        m = re.search(r"episode-(\d+)-replay", Path(args.replay).name)
        eid = int(m.group(1)) if m else None
        if eid not in seat_map:
            raise SystemExit(f"episode {eid} not found in {args.seats}; pass --my-seat explicitly")
        seat = seat_map[eid]
    r = analyse_replay(args.replay, seat)
    print(format_summary(r))
    if args.json:
        Path(args.json).write_text(json.dumps(r, indent=2, default=str))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
