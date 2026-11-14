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

Hashes are the SHA-256 of the file as it is in `hiivmind-corpus` at `d9ba1ad`. All are unchanged copies except those listed under "Edited copies".

| File here | From (at `d9ba1ad`) | SHA-256 of the source |
|---|---|---|
| `scripts/detect.py` | `hiivmind-corpus/lib/corpus/scripts/detect.py` | `6b8c81d8c0a15ff7e2edc1d9483190ccb6a2ef927fdeda733a16c3e44f8a159f` |
| `scripts/embed.py` | `hiivmind-corpus/lib/corpus/scripts/embed.py` | `53f90916c95fbd4c4711f7b4b747fff3d401f31e5af916d1ce7dc3fe46d6ae3d` |
| `scripts/verify_entries.py` | `hiivmind-corpus/lib/corpus/scripts/verify_entries.py` | `f1f74a9df360eddfc625a7f2fa88c69f1b7453fa24efeed4fd3b88955e4fa3a6` |
| `scripts/lance_meta.py` | `hiivmind-corpus/lib/corpus/scripts/lance_meta.py` | `a972d9226f2b51d4c21a1a9e513c3d27a118da0efe1d19ca0a81b34b88023eab` |
| `scripts/constants.py` | `hiivmind-corpus/lib/corpus/scripts/constants.py` | `64fa7d3017d61ec2df345dd0a48acfd3b8c3a630acd0efa6e2c454f28a9db964` |
| `scripts/token_utils.py` | `hiivmind-corpus/lib/corpus/scripts/token_utils.py` | `87e0f51e8baead0102aae6e59822b7b735aedb1e944cf9464f641ad315d873cc` |
| `reference/sources/git.md` | `hiivmind-corpus/lib/corpus/patterns/sources/git.md` | `a830d65a034ce39546b79c9d1bb71d0e7fb64b59f623c79b8474ad611d677ae6` |
| `reference/sources/shared.md` | `hiivmind-corpus/lib/corpus/patterns/sources/shared.md` | `76218fb25384e5894640d9a4a62bdf8957cb128ffc1693f87ced26fde896e767` |
| `reference/index-updating.md` | `hiivmind-corpus/lib/corpus/patterns/index-updating.md` | `213b86c9b9ba68db76d41e9471900e7c423886c5ec51821a1fbf1204b29883bc` |
| `reference/index-format-v2.md` | `hiivmind-corpus/lib/corpus/patterns/index-format-v2.md` | `4a4ead32e8d3626216be506c9ec931d822f39f83957cb385be457b9027347173` |
| `reference/freshness.md` | `hiivmind-corpus/lib/corpus/patterns/freshness.md` | `fefbb0676a217db4bfbee5baabee49ec87f872486b72cd67ea4784cbca564363` |
| `reference/embeddings.md` | `hiivmind-corpus/lib/corpus/patterns/embeddings.md` | `0b5ff17600409e6723be12266c0369b5ca1318dd5f3b4ee8c09a35a482d8aa0f` |
| `reference/paths.md` | `hiivmind-corpus/lib/corpus/patterns/paths.md` | `fa35d5f7e9153807436fd08f2378479cac27eee150ef79bd8a0022e8fc698686` |
| `reference/graph.md` | `hiivmind-corpus/lib/corpus/patterns/graph.md` | `20bef3f037935d3c3bc9b9711bceeafb40afd3c93e4b713c646fa446de4b17f2` |
| `reference/source-scanner.md` | `hiivmind-corpus/agents/source-scanner.md` | `903c7670624137b5d44f76dfcbabe73a4dcfabb6cde69de8204913e63731c01e` |

The corpus's own `render-index.sh` is used where it is, as the skills use it; it is not copied here.

## Edited copies

Each `${CLAUDE_PLUGIN_ROOT}/lib/corpus/scripts/<x>` is replaced by `scripts/<x>`, and each `${CLAUDE_PLUGIN_ROOT}/lib/corpus/patterns/<x>` by `reference/<x>`. Nothing else is changed (no wording needed editing to pass the no-coding-agent test).

- `reference/embeddings.md`
- `reference/index-updating.md`
- `reference/source-scanner.md`

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
| `tools/index.py` | `stale_files` and `apply_scan`: the merge of the scans into `index.yaml` | `hiivmind-corpus/skills/hiivmind-corpus-enrich-headless/SKILL.md` Phase 2, at `d9ba1ad` |

## After the runs with a model (Task 10)

The runs on `claude-haiku-5-5` (the two fixture corpora) and on `claude-sonnet-5-5` (Polars, without pushing) needed no change to a ported procedure or document. What the Polars run found is in `README.md`, "Acceptance runs".
