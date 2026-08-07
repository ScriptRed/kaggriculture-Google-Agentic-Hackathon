# Architecture notes: closed-loop vs. recorded route

We are committed to closed-loop (`agent/main.py` computes every action from
live `obs` every turn, no stored trajectory). This doc is about what that
costs us against the public field, which is overwhelmingly recording-based,
and what it buys us that a recording structurally cannot.

## What "recording-based" actually means here, precisely

Per `docs/target-plan.md`'s notebook audit, the dominant public pattern is:
reconstruct a strong 719-action trace from a real replay (barnyard-economist:
"transcribed from actions visible in one public replay"; v13-r3: "the
719-action production schedule was reconstructed from public replay
observations of OceanMix episode 90343084"), embed it as a compressed
blob, and replay it by **step index**. The credibility-weighting note in the
task brief that "only weed repair and SELL reordering react to the board"
undersells how thin the reactive surface actually is once you read the
notebooks directly - v13-r3's own list of everything layered on top of its
fixed schedule is: hand-count padding, actor-local `DIG`/weed retry, a
narrow near-mirror premium-sell shift (clone distance <= 6), and final-turn
liquidation. That's the entire reactive surface of one of the more
sophisticated public entries. Everything else - crop choice, animal
allocation, land timing, hand ramp, the full day-by-day shape documented in
`docs/target-plan.md` - is baked into the trace at build time, not decided
at runtime.

**kaito-v18-closed-loop is not the exception it's billed as.** We verified
this directly (see the strategy-log Task 2 entry): only its market/sell/
buy/hire layer is closed-loop - a day-level gate picks 1 of 4 "market
experts" from a 29-feature state vector, switching away from the base
expert on just 0.6% of days. Its **farmer/hand field-work trajectory is a
single fixed recording**, identical across all four experts until one
hardcoded fork point at turn 632, and the board-route reactivity gate that
would have made the field layer live too ships *disabled*
(`board_distance_strength = 0.0`) in the published artifact. It sits
exactly where v13-r3 sits: a recorded skeleton with a bounded, narrow,
market-layer overlay - just a market-only overlay instead of a
sell-timing-only one.

**`structured-economic-policy`** is the one genuine counter-example: a
fully live role/mission-assignment architecture (field roles scored every
turn as `S_ij = b_{p_j} + v_j - 8*d_1(x_i,x_j)`, workload-responsive hiring
`H_t* = min(cap, max(floor, ceil((J_t + 2*R_t)/7)))`, live
`obs["town"]["unlocked_shops"]` reads) with no stored trajectory at all -
architecturally the closest public relative to what we're building, not
what the task brief flagged as the closest (`kaito-v18`).

## What a recording buys, that we don't get for free

1. **Zero per-scenario compute and zero live-policy bug surface**, for the
   exact seed/opponent it was tuned against. A step-index lookup can't
   mis-score a task or mis-path a unit - correctness for that one scenario
   is guaranteed by construction, not by a heuristic that has to get every
   turn right.
2. **Execution quality that's hard for a greedy per-turn heuristic to
   match.** Our own `docs/ladder-observations.md` measured this directly:
   we spend 54.8% of actions on movement vs. real opponents' 41.7% - a
   recording built from (or directly copying) a real strong replay
   inherits that replay's pathing efficiency; our greedy `_assign` re-scores
   from scratch every turn and has no notion of a multi-turn route plan.
3. **The strategic design problem is solved by copying, not deciding.**
   barnyard-economist and v13-r3 both sidestep "which crop, how many tiles,
   when to pivot" (exactly what `docs/target-plan.md`'s gap analysis is
   about for us) by reconstructing the answer from a replay that already
   won. We have to get that right ourselves.

## What a policy buys, that a recording structurally cannot

1. **Generalization across seeds.** Weed spawns are per-day RNG
   (`weed_chance=0.005` per empty tile, seeded per day - `docs/
   economics.md`), and shop-unlock order is uniformly random per episode
   (Task 1). A fixed action-index trace has no mechanism to react to either
   - it just executes its script regardless of what the board actually
   looks like this game. This is precisely why every recording-based
   notebook we read bolts on *something* reactive for weeds specifically
   (v13-r3's "actor-local WEED recovery"; the credibility-weighting note's
   "weed repair" pattern generally) - recordings concede this weakness by
   patching around it rather than solving it.
2. **Generalization across opponents.** A recording assumes a specific
   opponent shape (usually the frozen `starter` bot or another public
   recording). Against a genuinely different opponent - our own arena pool
   includes `animal-heavy`, `melon-rush`, `market-dumper` specifically
   because they're *not* our own lineage - a hardcoded replay has no
   concept of "this opponent is dumping the item I'm about to harvest,
   sell now instead of waiting." A live policy can, in principle, read
   the opponent's visible tiles and react; every recording here can't, by
   construction, unless a narrow overlay was hand-built for that exact
   failure mode (which is exactly what v13-r3's near-mirror premium-shift
   is - a bespoke patch for one specific adversarial scenario, not a
   general capability).
3. **Immunity to engine version drift.** Multiple notebooks flag this as a
   real risk to a baked-in schedule - `live-meta`/`frontier-lab-high-score`
   claims the strawberry price cliff is 62 units in `kaggle-environments
   1.32.x` vs. ~247 in other builds; v22 explicitly captures the live
   notebook's installed engine version to guard against a "potentially
   lagged Notebook image." A schedule built against one engine's price
   curve can silently mis-time every sale under a different build. A
   policy that reads `obs`/`market` live and computes from `constants.py`
   (itself pinned to the installed engine by `tests/test_constants.py`)
   can't drift this way - it's reading the current curve every turn.
4. **Debuggability and incremental tuning.** Our whole development loop
   (`arena/run.py --compare`, `PARAMS`, `docs/strategy-log.md`) depends on
   being able to attribute an outcome to a specific scoring weight or gate
   and adjust it. A 719-step opaque trace can only be replaced wholesale or
   patched with a narrow reactive overlay - which is the entire strategy
   every recording-based notebook here follows once it needs to react to
   anything at all. We get to iterate on the actual decision logic instead
   of accumulating patches around an opaque core.

## The recordings' own evidence against locally improving a recording

barnyard-economist ran the experiment directly: its 719-action route spends
812 of ~6,000 worker-actions on `PASS` (13% - "free capacity" on its face).
Filling those slots with any available in-place action (not a move, not a
re-plan - just using otherwise-idle turns) **lost 8,685 coins**
(116,113 vs. 124,798 over four seeds), because opportunistic `HARVEST`
destroyed one-time crops before max yield. Every substitution that excluded
`HARVEST` produced a byte-identical tie. This is direct evidence for a
structural property, not a bug in that one implementation: **a recording's
actions are causally entangled with the exact board-state trajectory it
was built against.** Any edit - even one that looks strictly additive, like
using an idle turn - can invalidate every downstream action's assumptions
about what the board looks like, because the recording was never designed
to be locally patched; it was designed to be executed exactly, once, in
order. A live policy doesn't have this fragility by construction: every
decision is re-derived from the actual current board state, so there is no
"downstream" state to invalidate.

## Bottom line

Recordings win on raw execution polish for a fixed scenario and on
sidestepping the strategic-design problem by copying a proven answer. We
lose both of those for free. What we get instead - the entire reason to
stay closed-loop - is generalization the recordings cannot have at any
price: across seeds (weed RNG, shop-unlock order), across opponents
(reacting to what's actually on the board), across engine versions, and
across our own iteration process. Given the ladder pairs us against varied,
unknown-strength real opponents rather than a fixed counterfactual panel,
that generalization is the property that actually determines win rate -
the recordings' own authors concede as much every time they bolt on a
narrow reactive patch instead of trusting the schedule alone.
