# Meta-analysis: public notebooks

**Source count, corrected:** the task asked for three notebooks. `notebooks/`
now contains three files, but two are byte-identical (`kaggriculture-frontier-
lab-high-score-visuals.ipynb` at the top level and `live-meta/kaggriculture-
what-the-top-farms-do-a-live-meta.ipynb` — same content, different filename;
`diff` confirms it). So there are **two distinct notebooks**:

- **N1** — "Kaggriculture: What the Top Farms Do — a Live Meta Guide"
  (`cjlcjlcjl`). Embeds a real, engine-checked market model but its "meta"
  numbers come from Kaggle's hosted daily replay dataset, which we don't have
  access to.
- **N2** — "Kaggriculture: Findings from Zero to Top Meta" (`notebooks/
  zero-to-top-meta/`). Far more rigorous: its strategic claims come from code
  that calls `kaggle_environments.make()`/`env.run()` directly and reports
  actual local tournament results, not an external dataset. This is the
  stronger source and most of what follows leans on it.

## Security note, read this first

N2's final section embeds a ~446KB Python file as a base64+zlib-compressed
blob (cell 22) and its own code **decodes it, writes it to disk, and
executes it live** inside a `kaggle_environments` episode. I did not run
that cell. I decoded the blob to plain text for static inspection only (no
`compile`/`exec`/`import`) and confirmed: no network, subprocess, `eval`,
`os.system`, or filesystem access outside the stated `main.py`/
`submission.tar.gz`; three further nested blobs inside it decode via
`json.loads` (data, not executable code); and its content is thematically
consistent with a large Kaggriculture strategy agent (memory-based route
matching, sell planning, weed repair) — not anything that reads as
adversarial. N2's own cell 21 states its provenance directly: it's a
reproduction of a real, named, independently-popular public notebook
(`kaitofukami — 177/180 Fresh Top-30 v21.1`), which N1 independently lists
in its own "hot notebooks" section — real cross-corroboration, not just
N2's say-so. My assessment: **legitimate, not malicious**, but the pattern
(opaque compressed blob + auto-decode + auto-exec in a "public" notebook) is
inherently something to verify before running, not skip. I'm reporting the
static-inspection result rather than just declaring it safe and moving on.

## 1. Strategies identified as strong

**From N2, backed by its own runnable local code (`run_pair`/`h2h` call
`kaggle_environments` directly — I can rerun these myself, not just trust
them):**

- **Five strategy clusters**, in roughly increasing local strength: pure cow
  ranch → melon IPO → staged mixed herd (the "C0x" family, 3 cows + 1 sheep
  scaling to 14-15) → adaptive/opponent-routing → "stable efficiency tape"
  (~8 cow + 6 sheep + ~7 strawberry, heavy hand count, tight labor/inventory
  cycling). N2 explicitly frames each cluster as *fixing a specific failure
  mode of the previous one* (cow ranch loses milk wars once cloned; melon
  IPO gets crashed by a second dumper; fixed herds get correlated once
  everyone forks the same code) — a genuine progression, not just a list.
- **Sell-slot ordering matters and has been measured, not just asserted**
  (N2 §12.3, the notebook's own original contribution): market orders
  resolve index-by-index across both players against the same pre-commit
  inventory, so *which slot* a SELL lands in changes its price. N2 ran a
  controlled comparison (6 seeds × both seats) of three ranking keys for
  which SELL goes first: **`impact = qty × (unit_price − price_after_this_
  order)` won 12-0 (+5,205)**; ranking by raw revenue at stake lost 2-10
  (−2,138); ranking by **unit price lost 10-2 in reverse (i.e. −4,121) —
  worse than doing nothing**, because it front-loads goods whose price
  barely moves and leaves the steep-glut goods (wool, melon, milk,
  strawberry) to sell late and cheap. This is directly comparable to our
  own `_market_orders` step 2, which sorts by `-qty` (largest quantity
  first) — not impact, not unit price, a third, untested ordering. Worth a
  real experiment.
- **`DROP` is a required, separate action from `HARVEST`, and skipping it
  costs a full day of capital velocity.** I verified this directly in
  source (`kaggriculture.py:298-337`): `HARVEST` adds to the *harvesting
  unit's personal inventory*, not the shed; `SELL` only reads the shed;
  `DROP` (a distinct action, shed-adjacent-tile only) is what moves goods
  from inventory to shed *before* the automatic end-of-day sweep. **Our own
  `agent/main.py` never issues `DROP` at all** (confirmed: zero matches
  grepping the file) — everything we harvest is invisible to `SELL` until
  the automatic end-of-day drop, meaning same-day reinvestment of harvest
  proceeds is structurally impossible for us right now. This is the single
  most concrete, verified, actionable finding in this document.
- **`BUY_PRODUCT` (not `BUY_SEED`) silently fails when the shed is full** —
  N2 claims both fail; I checked source and only half of that is true.
  `BUY_PRODUCT`'s commit path (`kaggriculture.py:648-658`) really does check
  `sum(shed.values()) >= shed_capacity` and returns `False` (silent no-op,
  no error) if so. `BUY_SEED`'s commit path (`kaggriculture.py:659-664`)
  has no such check — seeds live in `private["seeds"]`, uncapped, entirely
  separate from the shed. **This matters for us specifically**: `agent/
  main.py` issues `BUY_PRODUCT WHEAT` (to feed animals) with no shed-
  capacity check first. If the shed is near its 100-item cap when that
  order fires, it silently fails, feed doesn't arrive, and
  `consecutive_unfed >= 2` means **the animal escapes** — a real, currently
  unguarded path to losing an animal for a reason that would show up
  nowhere in our logs.

## 2. Data-backed vs merely asserted

| Claim | Source | Check |
|---|---|---|
| Melon bonus window (6..12), max yield reached at age 10 not 12, cap 6 | N1 §3, N2 §2.1 | **Confirmed exactly** against `agent/constants.py`: `bonus_window("MELON")=(6,12)`, `harvest_age("MELON", fertilized=False)=10`, `expected_yield=6`. |
| Fibonacci hire cost curve, "~10 hands cheap, 12+ steep" | N1, N2 §1 (chart + table) | **Confirmed** — matches our own `hire_cost`/`fib` and `docs/economics.md`'s table exactly (8→54, 10→143, 12→375). |
| Price cliffs (strawberry 62, wool 59, milk 76, melon 158, wheat/egg ~3000 units to floor) | N1 §4, embedded + engine-checked model | **Confirmed exactly** against our own `agent/constants.py::market_price`. |
| `kaggle-environments>=1.32.4` required; older versions don't fail `BUY_PRODUCT`/`BUY_SEED` on a full shed | N2 §0 (cell 2) | **Half right, checked**: our installed version is 1.32.5 (fine, no action needed), and the shed-capacity gate is real — but only for `BUY_PRODUCT`, not `BUY_SEED` (see above). The notebook overstates which ops are affected. |
| "sell impact ordering beats collision/unit-price ordering, 12-0 vs 2-10 vs 10-2" | N2 §12.3, controlled 6-seed/both-seat comparison, code shown | **Internally consistent and mechanically well-motivated** (matches the known glut-curve shapes in `economics.md`); I have not independently rerun this specific tournament, so treat the exact scoreline as reported, not verified — but the *mechanism* is sound and checkable in our own arena. |
| Modal top farm ≈ "8 cow + 6 sheep [+ ~7 strawberry], NE+SW land, no melon" | N1 §8.5 (external dataset, unverifiable) and N2 §4 ("senkin13" replay fingerprint, described as from a "refreshed corpus" of real replays — also not directly inspectable by us) | **Consistent across two independent notebook sources**, which is worth something, but neither source's raw data is available to us — both are secondhand descriptions, not something I ran myself. Treat as **plausible and corroborated, not verified**. |
| Top-agent bank totals in the 100K-170K range (N1: "median 115,664, max 168,527"; N2: "153,340 vs a weaker opponent, 98,858 in self-play") | N1: external dataset, unverifiable. N2: **from N2's own locally-runnable `h2h`/`env.run()` code**, i.e. the same engine and config we have | This is the one place my read changed while writing this doc. N2's figures come from code I could rerun myself against the real `kaggle_environments` package — they aren't secondhand. That doesn't make N1's specific 115,664 number correct, but it substantially raises the *plausibility* of six-figure banks being achievable in this exact 30-day/$3000-start setup by a sufficiently optimized, fully-hands-utilized, multi-animal economy. Our own v2 agent tops out around 2,000-5,000 in arena runs — a 20-50x gap to what N2 demonstrates is reachable. I no longer think the N1 figure is implausible on its face; I still can't confirm the specific number. |
| "12 hands is the newest upgrade" (N1 §9 executive summary) vs "modal hand count is 5-6, mostly a Fibonacci ceiling — players place 200-300 HIRE orders but can only pay for the first few" (N1 §8.5, same notebook's own detailed data) | Both N1 prose, internally contradictory | Flagged in the prior version of this doc and still stands: N1's own executive summary oversells an aspiration ("12 hands") that its own detailed section says isn't actually being achieved. A concrete example of "a trending notebook is not automatically correct," inside a single source. |

## 3. Findings that contradict `docs/economics.md`

**None that survive a source check** — same conclusion as before, now on
firmer ground with N2's numbers too. `economics.md`'s revenue-density
ranking (melon >> cow/milk > sheep/wool > goose/egg > strawberry ≈ carrot >
wheat ≈ tomato) and N1/N2's crop-economics sections agree on every ordering
that matters; they use different formulas (gross $/tile-day over an assumed
window vs net-of-seed-cost over a different window definition) but point the
same direction. `economics.md` doesn't cover the animal CARE-bonus
compounding mechanic, the free/unlimited multi-structure (`BUILD_COOP`/
`BUILD_PASTURE`) mechanic, the `DROP`-vs-`HARVEST` inventory split, or the
`BUY_PRODUCT` shed-capacity gate — not contradictions, straightforward gaps,
now closed by this document and worth folding into `economics.md` directly
in a follow-up.

## 4. What we can verify ourselves in the arena, right now

- Sell-order-by-`impact` vs our current `-qty` ordering: directly
  A/B-testable via `--compare`, no new opponent needed — just a PARAMS/logic
  change to `_market_orders` step 2. High-value, well-motivated experiment.
- Whether adding explicit `DROP` actions when a unit is shed-adjacent with
  a non-empty inventory measurably improves capital velocity: directly
  testable the same way.
- Whether `BUY_PRODUCT WHEAT` is actually failing silently under real play
  (shed near cap while animals need feed): instrumentable by logging failed
  vs issued `BUY_PRODUCT` orders in a real episode.
- Whether an animal-heavy (cow+sheep, multi-pasture) opponent beats our
  crop-centric v2: directly testable — this is Task 3.
- The CARE-bonus compounding mechanic and multi-pasture mechanic
  (documented in the previous version of this file from N1 alone): both
  independently re-confirmed by N2's cluster descriptions (mixed herds
  staged 3→8-15, cows/sheep the backbone of every strong cluster).
- N1/N2's headline money figures and exact modal composition percentages:
  **still not independently verifiable** — no access to Kaggle's hosted
  dataset, and N2's own tournament numbers (Bradley-Terry league, 1,056
  games) aren't rerunnable without the embedded agent, which I'm not
  executing.

## 5. What they do that we do not do at all

- **We never issue `DROP`.** Confirmed by direct grep of `agent/main.py`.
  This is the highest-confidence, most concrete gap in this whole
  document — not a strategic preference, a missing action type.
- **We own zero cows and zero sheep**, and never issue `BUILD_COOP`/
  `BUILD_PASTURE` (also confirmed by grep) — our goose economy depends on
  however coop tiles get created, which isn't via our own agent's actions.
  Worth checking directly whether our geese are even being placed
  correctly given this (flagged, not resolved, in the prior version of
  this doc — still open).
- **We don't rank SELL orders by price impact.** We sort by quantity
  descending; N2's measured comparison says that's closer to the
  "unit price" ordering that *loses to doing nothing*, not the `impact`
  ordering that wins 12-0. Not proven for our specific agent, but the
  mechanism transfers directly.
- **We don't check shed capacity before issuing `BUY_PRODUCT`.** A
  verified, currently-silent risk to our (small) animal economy.
- **We don't distinguish early-bootstrap crop choice from late-sustained
  crop/animal choice** — `_pick_crop` picks one active crop for the whole
  game. Every strong cluster in N2 (and N1's early-seed data) stages: cheap
  capital crop early, animals/strawberry late.
- **We don't do opponent-adaptive routing or condition on visible opponent
  state at all** — N2's cluster D/E and its "impact" sell layer both react
  to what the opponent is doing; our agent only ever looks at its own farm.

## Bottom line

Everything mechanically checkable against `kaggriculture.py` directly
(price cliffs, melon window, hire curve, the `BUILD_*`/`DROP`/
`BUY_PRODUCT` mechanics) checked out true, including two places where I
found the *specific* claim was subtly wrong (`BUY_SEED` isn't shed-gated;
N1's "12 hands" executive summary contradicts its own data section) —
exactly the kind of thing a skeptical read is supposed to catch, and
exactly why checking against source instead of trusting either document
was worth doing. The two firmest, most actionable, most verified findings
are structural, not strategic: **we never `DROP` harvested goods**, and
**we never check shed capacity before feed purchases**. Both are small,
concrete code changes with an unambiguous mechanism behind them, and both
are more immediately fixable than "grow an animal empire." The animal-
economy gap (cow/sheep, multi-pasture, CARE-bonus compounding) is the
bigger strategic gap and the natural target for Task 3's opponent design.

---

## 6. The mirror opportunity (Task 5 - assessment only, no code)

**Question:** a large share of the ladder runs the same published open-loop
recording (see `docs/architecture-notes.md`). It can't react to anything,
its sell schedule is fixed and knowable step-by-step, and we can see the
opponent's tiles. Can we detect a known route from public state, and what
is the value of selling premium goods one turn ahead of a known dump?

### It's not hypothetical - it's already built, twice, and it's already measured live

`barnyard-economist` (a live-engine-verified fork of the `v22 price-impact`
route, itself built on `Kaito v21.1`'s recorded trajectory - see
`docs/target-plan.md`) ran the exact mirror matchup and reported it
straight: two copies of the same route playing each other **tie dead at
102,145 each**, "because both play the same route into the same market."
Contrast with the same agent's other live results: **194,871 / 201,932**
vs. the built-in `starter`, **150,939** vs. a public "Frontier Lab" agent,
**160,361** vs. "Night Harvest / Blackclaw", **120,864-142,107** vs. "a
tuned closed-loop policy agent." The mirror matchup is its *worst* live
result by a wide margin - not a loss (both score identically, so it's a
draw, not a defeat), but the crushing margin the route gets against
everyone else evaporates completely. Its own words: "as more copies enter
the ladder, they increasingly crash each other's prices, and the
artifact's edge decays without anyone touching it" - exactly the brief's
claim, now with a real live-engine number behind it rather than a
notebook's assertion.

**Two separate public notebooks already implement detection-and-exploit,
independently, with different designs:**

- **`v13-r3`** (the brief's example): a *near-mirror gate* comparing public
  crop/animal/structure/hand/`unlocked_quadrants` counts; if clone distance
  `<= 6`, it applies a bounded one-turn premium `SELL` shift (capped at 30
  units, `STRAWBERRY`/`MELON`/`MILK`/`WOOL` only, turns 120-680) with
  repayment on the following turn so the two-turn quantity is conserved.
  Narrow and reversible by design.
- **`kaito-v21` ("conditional memory")** - not named as a mirror mechanism
  in the brief, but that is exactly what it is: a full **1-nearest-neighbor
  opponent-route detector** against 30 stored public medoids (signatures
  built from hand count, unlocked quadrants, crop/animal/pasture/coop
  counts, weed count weighted 0.25, actor positions). Below a distance
  threshold (`<= 48`), it predicts the opponent's future `SELL` set and
  **reorders its own already-planned sells** to go first when they collide
  with a predicted opponent sell - it does not invent new sells. This
  matters: an earlier prototype *did* invent new early sells from the same
  prediction, and its own ablation reports "performance collapse" at
  roughly 28 preemptions/game. Two independent notebooks (v13-r3's
  front-insert-vs-append finding, v21's invent-vs-reorder finding) converge
  on the same shape of lesson: **react by reordering what you already
  decided to do, never by fabricating new actions from a prediction.**

**Detection itself is feasible with fields we already receive.** Both
implementations use only public observation - `obs["farms"][opponent]`
(tiles, hands, unlocked quadrants) and `obs["market"]` - nothing hidden.
Our own `obs` already exposes everything both mechanisms need.

**But it decays, and that cost is measured too.** `v22`'s own text reports
that `v21`'s mirror threshold "did not gradually lose because its mirror
threshold became slightly wrong" - it fell to 1/46 after the meta drifted,
and needed a full route-refresh (`v21.1`) to recover. A signature library
built from today's public notebooks needs upkeep as the field forks and
mutates; it is not a one-time build.

### Estimated coin value of "sell one turn ahead of a known dump"

Computed directly from `agent/constants.py::sale_proceeds` (the same price
model the env uses), for a plausible dump size per product (`their_dump`
chosen near what a mature holding of each item looks like in
`docs/target-plan.md`'s route, e.g. 42 strawberry at the d15-d21 plateau)
against a modest 10-unit position of our own:

| Item | We hold | Their dump | Sell before | Sell after their dump | Edge | Edge/unit |
|---|---:|---:|---:|---:|---:|---:|
| **STRAWBERRY** | 10 | 42 | $1,113 | $308 | **$805** | **$80.5** |
| MILK | 10 | 18 | $1,506 | $1,128 | $378 | $37.8 |
| WOOL | 10 | 12 | $1,983 | $1,837 | $146 | $14.6 |
| MELON | 10 | 12 | $2,498 | $2,472 | $26 | $2.6 |
| WHEAT | 10 | 35 | $237 | $220 | $17 | $1.7 |

Strawberry towers over everything else here - consistent with Task 1's
finding that it sits at the top of the sustainable-revenue ranking *and*
has one of the steepest glut curves (`linear`, `above_target 1.60`), so
timing around it is worth roughly **4-6x** any other single product.
Melon and wheat are barely worth the mechanism at this dump size - melon's
curve is quadratic but only bites hard much further from equilibrium than
a 12-unit dump reaches (consistent with the ~158-unit-to-floor figure in
`docs/economics.md`), and wheat is glut-resistant by design.

### Why this is worth ~nothing to us right now, concretely

The task brief's framing - "worth nothing while we are at 3,000" - holds up
under this analysis, for two compounding reasons, not just one:

1. **We hold none of the product that matters most.** The $80/unit edge is
   on strawberry, and Task 2's gap analysis already established
   `_pick_crop` never plants strawberry at all. A mechanism that pays out
   on inventory we don't have pays us nothing.
2. **Our own banks (4,000-20,000 in the arena's own opponent pool, per
   Task 4's numbers) are an order of magnitude below the route family's
   live results (100K-200K).** Repositioning a 10-unit sale by one turn is
   real money in absolute terms ($805 for strawberry) but small relative
   to the gap Task 2 is about closing - and irrelevant if we don't survive
   to hold a meaningful premium-goods position in the first place.

There's also a coverage question this analysis can't answer from here: we
don't have ladder telemetry on what fraction of opponents at our current
rating actually run this specific route family vs. something else
entirely - `docs/ladder-observations.md`'s 7 real replays show one
animal-heavy winner and two melon-heavy runners-up, not a recording match
to barnyard-economist's shape (see `docs/target-plan.md`). Building a
detector tuned to a route family we haven't confirmed we actually face
would be optimizing for an assumption, not a measurement.

**Recommendation, unchanged from the brief's own framing and now with
numbers behind it: do not implement.** Revisit once Task 2's production
gaps are closed and we're actually holding strawberry/premium-goods
inventory worth repositioning - and even then, build it as v13-r3 and v21
both converged on independently: narrow, reorder-only, gated tightly, never
inventing new sells from a prediction.
