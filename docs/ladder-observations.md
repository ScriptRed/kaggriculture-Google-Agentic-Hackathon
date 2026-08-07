# Ladder observations: 7 real replays

Analysed with `arena/analyse_replay.py --all replays --seats replays/
my_seats.csv`. Seat assignment came from `my_seats.csv` (regex-parsed to
tolerate a leaked terminal escape sequence contaminating its first line —
noted in the meta-analysis doc), cross-checked against each replay's own
`info.TeamNames` (`ScriptRed` is us) — the two sources agree on every
episode. All 7 games are `module_version 1.32.5`, matching our installed
engine exactly, so there's no version-skew concern for this data
specifically (unlike the notebooks' external dataset, which we can't check).

**Record: 1-6 (14.3%).** Mean final reward: **ours 3,864 vs opponents'
27,311** — a 7x gap. The one win (episode 90748536) was against an opponent
that PASSed 87.6% of its own actions and never hired a hand — not evidence
we're competitive, evidence that a near-inert bot is still beatable.

## The headline finding: our animal economy has never worked, in any of these 7 games

Confirmed by both the action log and the final board state, not inferred:

- `agent/main.py` issues `BUY_ANIMAL` (money leaves the bank, item enters
  the shed) but never `BUILD_COOP`, `BUILD_PASTURE`, `PICKUP`, or `PLACE`
  — confirmed by `grep`, zero matches for any of the four.
- Across all 7 replays, our own action distribution shows **0.0% for
  `BUILD_COOP`, `BUILD_PASTURE`, `PICKUP`, `PLACE`, `CARE`, `FEED`,
  `COLLECT_FERTILIZER`, and `DROP`** — not "rare," exactly zero, every
  game.
- Final animal count: `{}` (zero) for us in **every single one of the 7
  games**, regardless of how many geese we bought.

Mechanically, per direct source read (`kaggriculture.py:344-376`):
`BUY_ANIMAL` only ever puts the animal in the shed. Turning it into a live,
producing animal requires `PICKUP` (shed-adjacent, moves it to a unit's
carried inventory), walking it to an empty `COOP`/`PASTURE` tile (which
itself must be built via `BUILD_COOP`/`BUILD_PASTURE` — free, but a
separate action we also never issue), and `PLACE` (stands on that tile).
**We have never completed any step of this chain.** Every goose we've ever
bought on the ladder has sat inert in the shed for the rest of the game,
producing nothing. This is not a strategic gap, it's a missing feature —
confirmed independently by the meta-analysis doc's source read and now by
real ladder outcomes.

## We also never issue `DROP` — confirmed the same way

0.0% across all 7 games, matching the meta-analysis doc's grep-based
finding exactly. `HARVEST` lands in the harvesting unit's personal
inventory (`kaggriculture.py:298-337`); `SELL` only reads the shed; `DROP`
is the missing link. Opponents in 4 of 7 games did issue `DROP` (13-48
times each) — not universal in this sample, but present exactly where
opponents were doing anything sophisticated with inventory at all.

## What do the agents that beat us do differently?

Two distinct winning patterns show up in this sample, both absent from our
play:

1. **Full animal pipeline, at scale.** Episode 90746013 (`Ak`, final reward
   62,271 vs our 4,441): finished with `GOOSE: 5, SHEEP: 1, COW: 7` — 13
   live animals — using `BUILD_COOP`, `BUILD_PASTURE`, `PICKUP`, `PLACE`,
   `CARE` (3.8% of actions), `FEED` (4.0%), `COLLECT_FERTILIZER` (3.3%),
   and `DROP` (0.7%, 48 times) — every mechanic we skip, in one game. Ended
   with only the free `NW` quadrant, no purchased land at all — the
   animal economy carried the entire game without land expansion.
2. **Melon-heavy, water-disciplined.** Episodes 90746855 (`Ryotaro
   Minato`, 42,673) and 90749347 (`shane18`, 34,248) both finished with
   large melon holdings (17 and 25 tiles respectively) and **`WATER` shares
   of 33.2% and 22.0%** against our 8.6% and 6.6% in the same games —
   almost 4x our watering rate. This is exactly the mechanic both
   notebooks flagged (melon needs full watering ages 6-12 to reach its
   6-unit cap; partial watering silently caps yield around 70% of
   potential) and exactly what our low water share would predict is
   happening to our own melon, if we planted any (we mostly didn't —
   final crops were wheat-heavy or empty in most games).

## On which day does our bank trajectory diverge?

**Day 15, consistently, in 5 of the 6 losses** (all but the Clarence
Trinidad game, which diverges later, around day 25). The pattern is
strikingly uniform:

| | day 0 | day 10 | day 15 | day 20 | day 29 (final) |
|---|---|---|---|---|---|
| us (median across 7 games) | ~2,870 | ~2,650 | ~1,300 | ~1,420 | ~4,170 |
| pattern | starting cash | roughly flat or slightly up | **drops ~50%** | stays depressed | late recovery, still far behind |

We are **ahead or roughly tied through day 10 in every single game** —
this isn't a case of being outplayed from turn one. Then our own bank
visibly *drops* (not just stalls) in the day 10-15 window in every losing
game, while opponents who go on to win begin sustained, compounding growth
in that same window. The magnitude of our day-10-to-15 drop (roughly
$1,300-2,000 per game, remarkably consistent) lines up with a land
purchase plus multiple goose purchases landing in exactly that window —
and we now know the goose spend in that drop is money that produces
nothing, ever, for the rest of the game. The single clearest story this
data tells: **we correctly spend capital around day 10-12, opponents'
matching spend starts compounding by day 15, and ours doesn't, because a
real fraction of ours was never converted into a working animal in the
first place.**

## Action distribution: ours vs theirs, aggregated across all 7 games

| Action | Us | Them |
|---|---|---|
| Movement (N/S/E/W combined) | **54.8%** | **41.7%** |
| PLANT | 17.8% | 5.7% |
| WATER | 7.6% | 12.1% |
| PASS | 16.2% | 35.6%* |
| HARVEST | 3.5% | 1.9% |
| CARE / FEED / COLLECT_FERTILIZER / PICKUP / PLACE / BUILD_* / DROP | 0.0% (all) | 0.5-0.7% each |

\* Skewed by two near-inert opponents (87.6% and 95.1% PASS in the two
weakest games in this sample); excluding those two, the remaining
opponents' PASS rate is much lower and this aggregate shouldn't be read as
"strong opponents pass more."

**We spend over half our actions moving — 13 points more than the
opponent average**, and the gap is bigger against the strongest opponents
specifically (up to 24.8% on a single direction in one game). This matches
the task's own hypothesis almost exactly ("if we spend 40% moving and they
spend 15%, that's the largest single lever available") — not quite that
extreme, but the same shape and a real, quantified, aggregate-of-7 finding,
not a guess.

**Plant:water ratio is inverted.** We plant 2.33x more than we water
(17.8%:7.6%); the opponent average waters 2.1x more than it plants
(5.7%:12.1%, i.e. plant:water = 0.47x). Combined with the melon-window
mechanic (full water needed ages 6-12 to hit cap), this single ratio is
probably the most compact summary of "why do stronger agents' crops earn
more from the same or less planting" in this whole dataset.

## Does the replay evidence support or contradict the notebooks' claims?

**Strongly supports**, on every checkable point:

- Animal-heavy economies dominate: the single highest-scoring opponent in
  this sample (62,271) won almost entirely on a 13-animal herd with no
  land expansion — matches both notebooks' modal-meta claims directly,
  now confirmed against a real replay instead of an unreachable external
  dataset.
- Melon + heavy watering produces outsized results: two of the top three
  opponents by score ran melon-heavy, water-heavy plays — matches N1 §3/
  N2 §2.1's melon-window mechanics exactly, and the profit/tile-day
  numbers independently re-derived in the meta-analysis doc (melon ≈
  118/tile-day vs wheat ≈ 22.5).
- `DROP` discipline matters: present in every opponent that did anything
  beyond the bare minimum with inventory, absent in every one of our own
  games.
- Six-figure-adjacent bank totals are real and reachable in this exact
  engine/config: the top opponent reached 62,271 in a real ladder game
  (not a notebook's local sandbox or an external dataset) — direct,
  first-party evidence that the meta-analysis doc's revised, less-
  skeptical read of the notebooks' 100K+ figures was the right call.

**Nothing in this sample contradicts either notebook.** If anything, the
replays make the notebooks' claims feel understated relative to what we're
actually losing to.

## Did seat position correlate with outcome?

We were seat 1 in 5 of 7 games (matches the task's stated "five of seven"
exactly, cross-checked against `my_seats.csv` and each replay's own
`info` block independently). Results: **seat 0: 1-1 (50%). Seat 1: 0-5
(0%).**

This *looks* like a large effect, but treat it as a flagged pattern, not a
finding: n=2 for seat 0 is nowhere near enough to separate "seat matters"
from "these happened to be easier opponents" — each game is against a
different real opponent of unknown, uncontrolled strength, unlike our own
arena's paired both-seats-same-opponent design (Task C), which exists
specifically to avoid this confound. **Do not adjust how we weight arena
seat results based on this** — 7 games against 7 different unknown-skill
opponents can't tell us that; our own `--compare`/both-seats tooling is
the right instrument for an actual seat-effect measurement, and this
replay sample doesn't move that needle either way. It's worth remembering
that the ladder itself doesn't offer seat choice, so if a real seat effect
exists it affects our ladder rating regardless of what we do locally —
but this sample can't confirm or rule that out.

## Bottom line

We are not being out-strategised in the early game — day-0-to-10 bank
trajectories are competitive or ahead in every single replay. We are
losing because **a real fraction of our mid-game capital goes into an
animal economy that structurally cannot produce anything** (missing
`BUILD_COOP`/`BUILD_PASTURE`/`PICKUP`/`PLACE`), **harvested goods sit
outside the sellable shed for up to a full day** (missing `DROP`), and
**we water our crops at roughly half the rate the strongest opponents do**
relative to how much we plant, most costly on melon specifically. None of
these are strategic disagreements about which crop or animal to favor —
they're missing mechanics, straightforwardly fixable, and the replay
evidence says fixing them would matter more than any opponent-pool or
PARAMS tuning we've done so far this session.
