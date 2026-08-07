# Competition rules and mechanics

Paste the full Overview text from
https://www.kaggle.com/competitions/kaggriculture here, verbatim.

It is kept out of CLAUDE.md deliberately: it is long, and Claude Code should
load it on demand rather than paying for it every session.

The environment source is the real ground truth and lives at:
`kaggle_environments/envs/kaggriculture/kaggriculture.py` in your site-packages.
That package also ships `AGENTS.md` and a detailed `README.md` — both are worth
reading; they document the mechanics more precisely than the competition page.

## Deadlines

- Entry / team merger: 23 September 2026
- Final submission: 30 September 2026
- Leaderboard converges ~15 October 2026 via a Bradley-Terry tournament

## Constraints that shape the code

- No ingress or egress during an episode (§2.12)
- 5 submissions/day, latest 2 active and used for final scoring
- 100 MiB submission, 1.6 vCPU, 6.5 GiB RAM
- `main.py` at archive root; files land in `/kaggle_simulations/agent/`
- Winners must open-source under CC-BY 4.0 and write up their method
