# PORT

This instance is a copy of the existing corpus refresh, rewritten to the agent-core verbs. The two are kept in step by hand. Each file brought over is listed here with its source and the revision it was taken at.

## Source revisions

| Repository | Revision | What it is the source of |
|---|---|---|
| `hiivmind-corpus` | `d9ba1ad8821ecd4df2a771ef9ce5d75acad782af` | the skills, agents, patterns and scripts the nodes, `reference/` and `scripts/` are ported from |
| `hiivmind-corpus-scheduler` | `1a84e837c51197b0e497629bb4792897c9d077a0` | `TEMPLATE-corpus-refresh.md`: the job's phases, its constraints (`POLICY.md`) |

## Files

| File here | From | Revision |
|---|---|---|
| `tests/fixtures/render-index.sh` | `hiivmind-corpus-data/hiivmind-corpus-polars/render-index.sh`, unchanged | `hiivmind-corpus-data` `56ef52f` |
