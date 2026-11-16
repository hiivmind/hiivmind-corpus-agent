# PORT

This instance is a copy of the existing corpus refresh, rewritten to the agent-core verbs. The two are kept in step by hand. Each file brought over is listed here with its source and the revision it was taken at.

## Source revisions

| Repository | Revision | What it is the source of |
|---|---|---|
| `hiivmind-corpus` | `d9ba1ad8821ecd4df2a771ef9ce5d75acad782af` | the skills, agents, patterns and scripts the nodes and the package's `documents/` and `scripts/` are ported from |
| `hiivmind-corpus-scheduler` | `1a84e837c51197b0e497629bb4792897c9d077a0` | `TEMPLATE-corpus-refresh.md`: the job's phases, its constraints (`POLICY.md`) |

## Files

| File here | From | Revision |
|---|---|---|
| `packages/corpus-lib/tests/fixtures/render-index.sh` | `hiivmind-corpus-data/hiivmind-corpus-polars/render-index.sh`, unchanged | `hiivmind-corpus-data` `56ef52f` |

The scripts and documents the nodes use are in the corpus package, `packages/corpus-lib/src/hiivmind_corpus/`: `scripts/` and `documents/` (until step 1c, `scripts/` and `reference/` of this instance). They were copied from `hiivmind-corpus` at `d9ba1ad`, unchanged except those listed under "Edited copies". Since then the package owns these copies: nothing keeps them in step with the plugin, which is left as it is.

| File here (under `hiivmind_corpus/`) | From (at `d9ba1ad`) |
|---|---|
| `scripts/detect.py`, `embed.py`, `verify_entries.py`, `lance_meta.py`, `constants.py`, `token_utils.py` | `hiivmind-corpus/lib/corpus/scripts/` |
| `documents/sources/git.md`, `documents/sources/shared.md` | `hiivmind-corpus/lib/corpus/patterns/sources/` |
| `documents/index-updating.md`, `index-format-v2.md`, `freshness.md`, `embeddings.md`, `paths.md`, `graph.md` | `hiivmind-corpus/lib/corpus/patterns/` |
| `documents/source-scanner.md` | `hiivmind-corpus/agents/source-scanner.md` |

The corpus's own `render-index.sh` is used where it is, as the skills use it; it is not copied here.

## Edited copies

Each `${CLAUDE_PLUGIN_ROOT}/lib/corpus/scripts/<x>` is replaced by `scripts/<x>`, and each `${CLAUDE_PLUGIN_ROOT}/lib/corpus/patterns/<x>` by `reference/<x>` (now `documents/<x>` of the package). Nothing else is changed (no wording needed editing to pass the no-coding-agent test).

- `documents/embeddings.md`
- `documents/index-updating.md`
- `documents/source-scanner.md`

## Referenced, not ported; not used by these nodes

The copied documents name these scripts and documents. They stay as written; the files are not in this instance.

- Scripts: `scripts/chunk.py`, `scripts/detect_nav.py`, `scripts/detect_large_files.py`, `scripts/search.py`, `scripts/split_by_headings.py`
- Documents: `reference/extraction.md`, `reference/chunking.md`, `patterns/config-parsing.md`, `index-generation.md`, `index-rendering.md`, `index-reference.md`, `status.md`, `tool-detection.md`, `scanning.md`, `registry-graph.md`, `headless-contract.md`, `discovery.md`

## Behaviour kept from the skills

- `skills/refresh/SKILL.md` (from `hiivmind-corpus-refresh-headless` at `d9ba1ad`, phases 1 to 5): the embedding path of Phase 5 (step 29: `detect.py`, `embed.py`, the statuses `updated`, `no-model` and `not-installed`) is not reached in a run that gets there from step 27. Every entry the refresh adds or modifies is stale, so when `added` or `modified` is above 0 step 28 defers the embedding, and when both are 0 step 27 skips it. The skill has the same two rules in the same order and the same result; they are kept as they are, and the `enrich` node embeds after the summaries are written.
- `skills/enrich/SKILL.md` (from `hiivmind-corpus-enrich-headless` at `d9ba1ad`, phases 3 to 5): phases 1 and 2 are not in the node (the job finds the stale entries with `stale_files`, fans the scanning out with `scan` and merges it with `apply_scan`, which also clears `stale`). The node takes the ids of the re-scanned entries as input. Concepts are assigned from the existing `graph.yaml` only, and new-concept candidates are reported, never written. The verification sample is the first ten entries, not a random ten. There is no result file: the outputs are the result.

## Written here as code, from the skills and the template

These are not copies. Each is the logic of a skill or of the template, as a function or a script, so that no model call is spent on a step that has no judgement in it.

| File here | What it is | Taken from, at |
|---|---|---|
| `jobs/refresh.py` | the job: the template's phases in order, with the scans run at the same time | `hiivmind-corpus-scheduler/TEMPLATE-corpus-refresh.md` at `1a84e83` |
| `tools/status.py`, `tools/sources/` | `corpus_status`, the freshness pre-check; the seam for kinds of source | `hiivmind-corpus/skills/hiivmind-corpus-status-headless/SKILL.md` phases 1 to 4, at `d9ba1ad` |
| `tools/repo.py` | `repo_prepare` (the template's Phase 2), `repo_branch`, `repo_finish` (Phase 4) | the template at `1a84e83` |
| `tools/index.py` | `stale_files`, `apply_scan` (the merge of the scans into `index.yaml`) and `drop_missing` (the removal of the entries whose files git says are gone from the source; the owner's decision of 2026-11-15, not from a skill) | `hiivmind-corpus/skills/hiivmind-corpus-enrich-headless/SKILL.md` Phase 2, at `d9ba1ad` |

## After the runs with a model (Task 10)

The runs on `claude-haiku-5-5` (the two fixture corpora) and on `claude-sonnet-5-5` (Polars, without pushing) needed no change to a ported procedure or document. What the Polars run found is in `README.md`, "Acceptance runs".
