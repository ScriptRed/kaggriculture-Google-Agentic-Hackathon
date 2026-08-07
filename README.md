# Kaggriculture

Agent for the Kaggle Kaggriculture simulation competition.
Private until the competition closes (Rules §3.6a).

## Setup

```bash
pip install -U kaggle-environments pytest
make test      # verify constants against the env
make quick     # 3-seed smoke test
make arena     # the real fitness signal
```

## Where things are

| Path | What |
|---|---|
| `agent/main.py` | The submission. Entry point is `agent(obs)`. |
| `agent/constants.py` | Game tables + price model, pinned to env by tests. |
| `arena/run.py` | Fitness function: win rate over fixed seeds. |
| `arena/metrics.py` | Diagnostics that explain *why* a version regressed. |
| `docs/economics.md` | Derived analysis of crops, market, labour. |
| `docs/strategy-log.md` | Append-only experiment record. Read before changing. |
| `CLAUDE.md` | Context for Claude Code. |

## Submitting

```bash
make submit MSG="what changed"
kaggle competitions submissions kaggriculture
```

Only the latest 2 submissions are active and used for final scoring. Keep one
known-good and one experimental; never ship two experiments at once near the
deadline.
