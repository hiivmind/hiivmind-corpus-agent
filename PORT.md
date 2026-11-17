# PORT

This instance is a port of the existing corpus refresh, rewritten to the agent-core verbs and, since step 1c, split into the nodes of the `refresh` sequence over the corpus package. Nothing keeps the two in step: the plugin is left as it is. Each file brought over is listed here with its source and the revision it was taken at.

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
| `templates/render-index.sh` | `hiivmind-corpus/templates/render-index.sh`, the tiered-capable renderer the plugin's `migrate` copies |

A v2 corpus's own `render-index.sh` is used where it is, as the skills use it. `migrate_index` copies the package's `templates/render-index.sh` into the corpus it migrates, as the plugin's `migrate` does.

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

The seven nodes are written from step 1b's `refresh` and `enrich` nodes (themselves from `hiivmind-corpus-refresh-headless` and `hiivmind-corpus-enrich-headless` at `d9ba1ad`) and its job script, which step 1c deleted. The port made only these changes (the design's §4.3): the procedures are split among the nodes; each step that edited `index.yaml`, `config.yaml` or `graph.yaml` by exact text calls a package tool; a step that repeated code calls the code; scripts and documents are reached through tools (`reference` for a document, a named tool for each script); `scan` takes one `batch`, and each node names its own error list. Every other step keeps its wording.

| Node | From |
|---|---|
| `update-sources` | `refresh` phases 1 to 4, and the job's `drop_missing` call |
| `scan` | `scan` |
| `index` | the job's `apply_scan` call |
| `concepts` | `enrich` phases 1 and 2 |
| `verify` | `enrich` phase 3 |
| `embed` | `enrich` phase 4 and `refresh` phase 5 |
| `publish` | `repo_branch`, `repo_finish` and the job's pull request body |

## Written here as code, from the skills and the template

These are not copies. Each is the logic of a skill or of the template, as a function or a script, so that no model call is spent on a step that has no judgement in it. They are in the corpus package, `packages/corpus-lib/src/hiivmind_corpus/`.

| File there | What it is | Taken from, at |
|---|---|---|
| `status.py`, `sources/` | `corpus_status`, the freshness pre-check; the seam for kinds of source | `hiivmind-corpus/skills/hiivmind-corpus-status-headless/SKILL.md` phases 1 to 4, at `d9ba1ad` |
| `repo.py` | `prepare_base`, the first part of the template's Phase 2 | the template at `1a84e83` |
| `index.py` | the layout-keeping writer, `stale_files`, `apply_scan` (the merge of the scans into `index.yaml`) and `drop_missing` (the removal of the entries whose files git says are gone from the source; the owner's decision of 2026-11-15, not from a skill) | `hiivmind-corpus/skills/hiivmind-corpus-enrich-headless/SKILL.md` Phase 2, at `d9ba1ad` |
| `refresh.py` | the capabilities the nodes call; `status_report` and the checks of the job sequences | `refresh` and `enrich` of step 1b; `apply_source_update` follows `documents/index-updating.md` |
| `migrate.py` | `migrate_index`: the v1 parser, the id check and the restore | `hiivmind-corpus/skills/hiivmind-corpus-migrate/SKILL.md` phases 1, 2, 3 (resolution only) and 5, at `d9ba1ad` |
| `graph.py` | `validate_graph` | `documents/graph.md`, "Validation Rules" |
| `reference.py`, `run.py` | a document of `documents/`, whole or one section; `uv run` of a script of `scripts/` | new |

## After the runs with a model (step 1b, Task 10)

The runs on `claude-haiku-5-5` (the two fixture corpora) and on `claude-sonnet-5-5` (Polars, without pushing) needed no change to a ported procedure or document. What the Polars run found is in `README.md`, "Acceptance runs".
