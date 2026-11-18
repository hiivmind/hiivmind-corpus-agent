# hiivmind-corpus-agent

A corpus instance for [agent-core](../hiivmind-agent-core): the scheduled refresh of a documentation corpus, as a sequence of nodes with a model. `agent-core job instance.yaml refresh --settings config/<corpus>.yaml` walks the `refresh` sequence of `topology.yaml`: it checks a corpus against its upstream sources, brings its index up to date, commits the result on a new branch and, when `PUSH` is true, opens a pull request. There is no job script.

The nodes (`skills/`) orchestrate tools; the tools (`tools/corpus.py`) are thin clients of the corpus package, `hiivmind-corpus-lib` (`hiivmind_corpus`, the sibling repository `../hiivmind-corpus-lib`), which holds the index writer, the status code, the base-branch check, and the scripts and documents the nodes use. The package imports neither agent-core nor the instance.

It is a port of the existing refresh (`hiivmind-corpus` and `hiivmind-corpus-scheduler`), rewritten to the core's verbs; `PORT.md` lists which file came from which, at which revision. The existing plugin and the scheduler are unchanged.

## Requirements

- Python 3.12 or later and `uv`. `uv sync` installs the instance. `pyproject.toml` takes `agent-core[langgraph]` and `agent-tools` by path from `../hiivmind-agent-core`, and the corpus package as a uv workspace member (`packages/*`), so the core has to be checked out beside this repository; after any change to the core, run `uv sync --reinstall-package agent-core`.
- `git`, and `gh` logged in to GitHub when `PUSH` is true (`publish` lists, opens and closes pull requests); with `PUSH` false no `gh` command runs.
- The corpus's own `render-index.sh` needs `yq`, the Go one (mikefarah, version 4). The snap `yq` cannot read a hidden directory, so a corpus must not be under a path with a hidden component (`.cache`, `.hiivmind`, ...); the tests keep their temporary directories in `test-tmp/` for this reason.
- `npx`, for the reference filesystem MCP server the nodes read and write files through (`instance.yaml`, `servers`).
- `ANTHROPIC_API_KEY` in the environment. The model is `AGENT_CORE_LANGGRAPH_MODEL`, `claude-sonnet-5-5` when it is not set.

## Run the refresh for a corpus

```bash
cd <this directory>
uv sync
uv run agent-core job instance.yaml refresh --settings config/polars.yaml --param PUSH=true
```

`config/base.yaml` sets `PUSH: false`, so a run pushes only when it says `--param PUSH=true`. **`config/polars.yaml` points `CORPUS_PATH` at the owner's working clone** (`~/git/hiivmind/hiivmind-corpus-data/hiivmind-corpus-polars`): the command above, as written, checks out `BASE_BRANCH` in that clone, commits in it and pushes from it. For any other clone, give `--param CORPUS_PATH=...` as below.

A corpus is named by its settings file (`config/polars.yaml`, `config/ibis.yaml`), layered over `config/base.yaml`:

| Setting | Meaning |
|---|---|
| `CORPUS_PATH` | the directory holding the corpus's `config.yaml`: the root of its repository, or a directory inside it |
| `CORPUS_REPO` | `owner/name` on GitHub: where the pull request goes, and where `gh pr list` looks for the open ones. It must be the repository `origin` of the clone points to: with `PUSH` true, `publish` stops before making the branch when `origin` is a GitHub repository with another name (`origin` that is not a GitHub URL, a path for example, is not checked) |
| `BRANCH_PREFIX` | the branches `publish` makes are `<BRANCH_PREFIX>-<date>`, then `-2`, `-3` ... when the name is taken |
| `BASE_BRANCH` | default `main` |
| `PUSH` | `false` in `config/base.yaml`; `false` commits on the new local branch and returns to `BASE_BRANCH`: nothing is pushed, no pull request is made or closed |

`--param KEY=VALUE` beats the environment (`HIIVMIND_CORPUS_<KEY>`), which beats the files. So a run on a clone somewhere else, that does not push, is

```bash
uv run agent-core job instance.yaml refresh --settings config/polars.yaml --param CORPUS_PATH=/path/to/hiivmind-corpus-data/hiivmind-corpus-polars --param PUSH=false
```

and `CORPUS_REPO` follows the clone: a clone whose `origin` is `someone/fork` needs `--param CORPUS_REPO=someone/fork`, because the branch is pushed to `origin` and the pull request is opened on `CORPUS_REPO`, and `publish` refuses to push when the two differ. A setting that no file, variable or parameter gives stops the run before it starts, naming the setting (exit code 2).

What the `refresh` sequence does, in order (`topology.yaml`, `sequences.refresh`):

1. **Checks, with no model call.**
   1. `prepare_base`: stops when the working tree is dirty or when `BASE_BRANCH` has commits that `origin/BASE_BRANCH` does not; checks out `BASE_BRANCH`, fetches `origin` and fast-forwards. A problem fails the run before any node, with its reason (exit 1).
   2. `index_is_v2`: a corpus with no `index.yaml` (a v1 corpus) goes on to the `migrate` sequence, below, instead of refreshing.
   3. `corpus_ready`: `config.yaml` has a source, `index.yaml` exists and `index.md` is not the build's placeholder.
   4. `refresh_needed`: when every source is current, no entry is stale and the embeddings do not lag, the run ends `Already current.` (exit 0) and has made no model call and no branch. A source whose freshness is unknown, or a status that cannot be read, counts as needing a refresh.
2. **`update-sources`**: updates each source that is behind, marks the entries of changed files stale, adds and removes entries, records the new commits, drops the entries whose files git says are gone, and renders `index.md`. A failure here ends the run (exit 1) with nothing changed.
3. **`scan`**, a fan-out over the stale files of the index (entries left stale by an earlier run too), in batches of at most 30 files; each run writes the metadata of its files and changes nothing.
4. **`index`**: merges the scans into `index.yaml`; an entry whose batch failed, or whose file no scan returned, is skipped with the reason and stays stale.
5. **`concepts`**: assigns existing concepts to the enriched entries that have none; it writes no concept.
6. **`verify`**: checks a sample of the new summaries against their files and replaces one that does not describe its file.
7. **`embed`**: defers while entries are stale, never downloads a model, embeds again when the model is ready, and reports the lag.
8. **`publish`**: commits the corpus's changes on `<BRANCH_PREFIX>-<date>` with the report as the message (it stops when a file outside the corpus is staged); with `PUSH`, pushes, opens the pull request and closes the ones it supersedes; then returns to `BASE_BRANCH`.

No node edits `index.yaml`, `config.yaml` or `graph.yaml` by text: every change goes through a tool of the package. A failure of `scan`, `index`, `concepts`, `verify` or `embed` still reaches `publish`, which publishes the corpus as it stands and lists every node's problems in the body; the run then exits 0 when `publish` succeeds. A source of a kind other than git is reported and not refreshed (`skipped-manual`); a source that fails is reported `failed` with the reason and its entries stay as they were; the other sources go on.

`prepare_base`'s git commands have a timeout of 300 s, the freshness check's `git ls-remote` one of 60 s, and every `git` and `gh` command of `publish` one of 120 s. The pull request's body lists at most 50 ids in each list, then `and N more`.

The run is recorded in `runs/refresh-<UTC start>-<six hex digits>/record.json` (`--run-dir` chooses another directory; `runs/` is not committed): the steps and their outcomes, the facts every node gave, the summary (`publish`'s outputs: `branch`, `pr_url`, `superseded_prs`), the failed node runs with their reasons, and the model calls and tokens of each node run. A node that fails through the harness (no exit, an invalid output) leaves no outputs: its reason is in the record's `failures`, not in the pull request. The exit code is 0 when the sequence ends `done` or `stopped`, 1 when it ends `failed` (a check, `update-sources` or `publish` failed), 2 when the run could not start. `--resume <run id>` continues a run that crashed, from the steps that finished.

## The other sequences

Each runs the same way, `uv run agent-core job instance.yaml <sequence> --settings config/<corpus>.yaml`, and is recorded in `runs/<sequence>-…/`:

- **`status`**: one node, `status`, reports each source's freshness, the index format, the stale entries, the embeddings' lag and `refresh_needed` in the record's facts, and ends `current` or `stale` (exit 0 either way). It fetches nothing and changes nothing.
- **`enrich`**: the refresh without `update-sources`. Its checks are `prepare_base`, `index_is_v2` (a v1 corpus goes on to `migrate`), `corpus_ready` and `stale_entries` (with nothing stale the run ends `Nothing is stale.`, exit 0, no model call). `checkout-sources` then checks out each git source at the commit the index was built at, and the scans, `index`, `concepts`, `verify`, `embed` and `publish` follow; the pull request is titled `corpus: enrich <date>`.
- **`migrate`**: converts a v1 corpus (`index.md`, `index-*.md`) to `index.yaml`. Its checks refuse a corpus that has no v1 index or has a source of a kind other than git (exit 1, no model call). `checkout-sources` checks out each source at its `last_commit_sha`; one that cannot be checked out ends the run (exit 1) with nothing written. `migrate` writes every entry stale with its v1 title and summary, copies the package's `render-index.sh` into the corpus and renders; an id of the original `.md` files that is neither rendered nor skipped, or a render that fails, puts every file back and ends the run (exit 1). The scans then write each entry's metadata, and `publish` opens the pull request on the corpus's own repository, titled `corpus: migrate <date>`. A v1 corpus is its own repository: its settings file has `CORPUS_PATH` at that repository's root, its own `CORPUS_REPO`, and `BRANCH_PREFIX: automated/corpus-refresh-<name>`.
- **`graph-validate`**: checks `graph.yaml` against the graph rules (errors: the schema, a concept an entry names that the graph lacks, a relationship whose end is not a concept; warnings: a concept no entry names, a relationship type or origin outside the vocabulary of `graph.md`). It ends `valid` or `invalid` (exit 0 either way), with the issues in the record's facts; a corpus with no `graph.yaml` fails the check (exit 1).

## Add a corpus

Write one settings file, `config/<corpus>.yaml`, with `CORPUS_PATH`, `CORPUS_REPO` and `BRANCH_PREFIX`; nothing else changes. The corpus must have a `config.yaml` with its sources, and either a v2 `index.yaml` with its own `render-index.sh`, as the corpora of `hiivmind-corpus-data` do, or a v1 index, which `migrate` converts. The same node files serve every corpus: nothing in them names one.

## Add a source kind

Git is the only kind handled. The seam is `src/hiivmind_corpus/sources/__init__.py` in `hiivmind-corpus-lib`. A kind is:

1. a module in that package with a class that has `freshness(source, corpus)`, returning `("current" | "behind" | "unknown", error or None)` without cloning or changing anything, as `sources/git.py` does;
2. a line in `SOURCE_KINDS`, keyed by the source's `type`;
3. its reference document `documents/sources/<type>.md` in the package, which `update-sources` reads through `reference`. Step 7 of the node sends every type but `git` to `skipped-manual`, and its Phase 3 describes how git gets its new commit; for a new kind that step lets the type through and the phase says, from the kind's document, how its working copy is updated, and `apply_source_update` learns how its changed files are found;
4. the server it needs, declared under `servers:` in `instance.yaml` (a web kind needs a fetch server; none is declared today).

The sequence, the other tools and the contracts of the nodes do not change.

## Run it on a schedule

The core has no scheduler (JOB-11); whatever the host provides (cron, a systemd timer, CI) starts the job. The line is:

```bash
cd <instance dir> && uv run agent-core job instance.yaml refresh --settings config/<corpus>.yaml --param PUSH=true
```

For a repository of several corpora, the scheduler runs that line once for each settings file, one after another, not at the same time: the corpora share one working tree, and a run starts by checking that it is clean and by checking out the base branch.

## Tests

```bash
uv run pytest -q                                          # no model: the scripted backend; a few minutes
set -a && . <file holding ANTHROPIC_API_KEY> && set +a
AGENT_CORE_LANGGRAPH_MODEL=claude-haiku-5-5 uv run pytest tests/model -m model -q    # calls a model; costs money
```

The suite builds a corpus and its upstream in `test-tmp/` and uses a stand-in `gh`: no test touches a real corpus repository or opens a pull request. The tests marked `model` run the `refresh` sequence with the LangGraph backend on those fixture corpora (`PUSH=false`, apart from the one that pushes to a local bare repository and opens its pull request on the stand-in) and keep each run's directory under `runs/model-tests/<date>/<model>/<test>/`. Develop on `claude-haiku-5-5`; the pass bar is one pass on `claude-sonnet-5-5`.

## Acceptance runs

Run on 2026-11-15 (local time; the run records' UTC times are 2026-11-14). Two passes: the first, 13:13 to 13:20 UTC, with commit `0ecf951`; the second, 13:33 to 13:40 UTC, after `b53deb0`, which made `apply_scan` keep the layout of `index.yaml`. Nothing was pushed and no pull request was opened.

### Steps 1 and 2: the fixture corpora

`uv run pytest tests/model -m model -q`, each test once, one after the other, on each model. Both tests passed on the first run on both: `claude-haiku-5-5` in the first pass, `claude-sonnet-5-5` (the pass bar) in the second.

| Test | Model | Result | Model calls (refresh / scan / enrich) | Wall time |
|---|---|---|---|---|
| `test_the_fixture_corpus_is_refreshed_and_a_lost_commit_fails_its_source` (step 1, and Review Focus 2) | haiku | passed | first job 27 (15 / 4 / 8); second job 10 (refresh only) | 62 s and 22 s; 96 s with the fixture |
| the same | sonnet | passed | first job 21 (11 / 3 / 7); second job 8 (refresh only) | 62 s and 21 s; 96 s with the fixture |
| `test_the_same_nodes_refresh_a_second_corpus_and_its_pull_request_goes_where_the_parameter_says` (step 2, criterion 11) | haiku | passed | 29 (17 / 3 / 9) | 70 s; 76 s with the fixture |
| the same | sonnet | passed | 24 (13 / 3 / 8) | 67 s; 73 s with the fixture |

The first job refreshes the fixture corpus (`docs:a.md` modified, `docs:d.md` added, `docs:c.md` deleted upstream): the source is `updated` at the upstream's head, `a.md` is re-scanned and not stale, `d.md` has an entry, `c.md` has none, `index.md` is rendered again, there is one commit on a new branch, and the record lists the source and the two entries enriched. Then the upstream's history is rewritten (one new root commit; the commit the corpus tracks is unreachable) and the job runs again on a clean copy of the source: the source is `failed` with "commit ... is not in the history of main", its entries stay as they were, nothing is committed (`no changes`), the exit code is 0. The second test uses a corpus with another name, another source id (`guide`) and another docs root (`manual/`), the same node files, `--param CORPUS_REPO=someone/other --param PUSH=true`: the branch is pushed to the test's own bare repository and the stand-in `gh` is called for `pr list` and `pr create`, both with `--repo someone/other` and no other.

### Step 3: Polars, without pushing, `claude-sonnet-5-5`

The corpus is a fresh clone of `https://github.com/hiivmind/hiivmind-corpus-data` made for the runs, in `~/agent-core-scratch/hiivmind-corpus-data/` (not the owner's working clone, which is older), at `b56f6ce`. From the instance directory:

```bash
uv run agent-core job instance.yaml refresh --settings config/polars.yaml \
  --param CORPUS_PATH=$HOME/agent-core-scratch/hiivmind-corpus-data/hiivmind-corpus-polars --param PUSH=false
```

The run needs the real `gh`: the job runs `gh pr list --repo hiivmind/hiivmind-corpus-data` (it only reads; `PUSH=false` leaves `gh pr create` and `gh pr close` out), and it found no open refresh pull request. Run twice: the first time on the fresh clone, with `0ecf951`; then, after `b53deb0`, on a fresh state of the same clone (`main` checked out, the first run's local branch deleted, its `.source/` working copy of Polars removed, the tree clean). Both runs exited 0 with status `ok` and no failed node run.

| What | First run (`0ecf951`) | Second run (`b53deb0`) |
|---|---|---|
| Wall time | 3 min 50 s (record 13:16:28 to 13:20:12 UTC) | 4 min 6 s (record 13:36:13 to 13:40:14 UTC) |
| Sources | 1: `polars`, `https://github.com/pola-rs/polars`, `docs/source`, git; `updated` `5075c53` to `36ea0f9` | the same source, `5075c53` to `43d7572` (the upstream moved in between) |
| Files | 190 files under `docs/source` upstream (87 Markdown); 26 changed between the two commits, of which 20 have an index entry (`modified` 20, `added` 0, `removed` 0) | the same counts |
| Entries | 112 in the index before and after (the fresh clone's index is not the 111 of the owner's older copy); 37 stale before the run, 52 to scan after the refresh (37, plus the 20 modified, 5 of them already stale), 26 after the run | the same |
| Scans | 2 node runs at the same time (batches of 30 and 22 files); 26 entries came back from the scans and 26 files had no scan; 26 enriched, 26 skipped, 26 under "Needs attention" | the same, and the same entries |
| Verification | sampled 10, failed 0, no drift; 1 new concept candidate (`Contributing`: 3 entries), nothing written to `graph.yaml` | the same |
| Embeddings | `no-model` (`detect.py` printed it): not updated, lag 5, as before | the same |
| Commit | one, `corpus: refresh 2026-11-15`, on `automated/corpus-refresh-polars-2026-11-15` in the scratch clone (`ed6ba7a`): `config.yaml` (6 lines: `last_commit_sha`, `last_indexed_at`, `index.last_updated_at`), `index.yaml`, `index.md`; its message is the report. No pull request (`pr_url` null) | the same files, `235609d` |
| `index.yaml` in the commit | **2,647 lines added, 1,500 removed**: the whole file, rewritten in another layout | **1,192 lines added, 158 removed**, 94 hunks, every one inside one of the 26 enriched entries (one line, `meta.generated_at`, apart); the other 86 entries and every other line are as they were |
| `index.md` in the commit | 56 lines changed | 59 lines changed |

The 1,350 changed lines of the second run are the 26 entries themselves. All 26 had no `path`, `keywords`, `content_type`, `size`, `headings` or `grep_hint` (97 of the 112 entries of this index had no `path` before the run, 71 have none after it), so each gains them, about 46 lines an entry, with the new summary and tags.

Model calls and tokens for each node run, from `record.json` (`tokens_sent` is all the input of the run's calls, cached or not; the record keeps no count of output tokens). The scans are `scan#2` (30 files) and `scan#3` (22 files).

First run:

| Node run | Model calls | `tokens_sent` | Read from cache | Written to cache | Not cached |
|---|---|---|---|---|---|
| `refresh#1` | 18 | 508,781 | 456,435 (89.7%) | 52,308 | 38 |
| `scan#2` | 4 | 163,625 | 91,177 (55.7%) | 72,438 | 10 |
| `scan#3` | 4 | 113,339 | 66,010 (58.2%) | 47,319 | 10 |
| `enrich#4` | 11 | 612,320 | 542,057 (88.5%) | 70,239 | 24 |
| Total | 37 | 1,398,065 | 1,155,679 (82.7%) | 242,304 (17.3%) | 82 |

Second run:

| Node run | Model calls | `tokens_sent` | Read from cache | Written to cache | Not cached |
|---|---|---|---|---|---|
| `refresh#1` | 17 | 497,933 | 447,583 (89.9%) | 50,314 | 36 |
| `scan#2` | 4 | 163,955 | 92,614 (56.5%) | 71,331 | 10 |
| `scan#3` | 4 | 113,339 | 67,449 (59.5%) | 45,880 | 10 |
| `enrich#4` | 12 | 681,164 | 610,069 (89.6%) | 71,069 | 26 |
| Total | 37 | 1,456,391 | 1,217,715 (83.6%) | 238,594 (16.4%) | 82 |

What went right: all four node runs of each run ended `done` on the first try, with no question to the person and no failed run in the record; the refresh resolved the tracked commit in the shallow clone and recorded the new commit and time with edits of `config.yaml` that touch only those lines; the enriched entries I read (summaries, keywords, headings, concepts from the existing graph) are good. The procedures did not need a fix, so neither run was repeated for one.

What went wrong, or is not as it should be:

- **`index.yaml` was rewritten from top to bottom (first run; fixed).** `apply_scan` wrote the whole file with PyYAML, and the index on `main` of `hiivmind-corpus-data` is in another layout (list items indented under their key, other quoting) than the one the writer produced; the owner's older copy, which the first round-trip test read, was in the writer's layout. The commit's diff of `index.yaml` was 2,647 lines added and 1,500 removed for 26 entries that changed, unreadable as a pull request's index diff. `b53deb0` writes only the entries that changed, in the layout the file has; the second run's diff is the one in the table.
- **26 stale entries point at files that are not in the source.** They are the 25 `polars-on-premises/...` entries and `polars-cloud/run/distributed-engine.md`, stale since 2026-06-30 (16) or 2026-07-06 (10), and no such file exists under `docs/source` at `5075c53` or at either head. The refresh cannot see them (they are not in the diff between the two commits), the scans find no file, so they stay stale and are listed under "Needs attention", as Review Focus 5 expects, in both runs. The owner decided on 2026-11-15 that an entry whose file is gone from its source is removed, so the job now removes them: `drop_missing` runs after the refresh and before the scans, and the 26 entries go from `index.yaml` on the first run after this change. The two runs above predate it; step 4 below removed them.
- **The embeddings stay 5 entries behind**: `detect.py` prints `no-model` on this machine, so `enrich` does not embed (it never downloads the model during a refresh).
- **Noise on the terminal**: the filesystem MCP server prints a line for each request and, after eleven, a Node `MaxListenersExceededWarning`; the job itself prints nothing, its summary is in `record.json`.

### Step 4: Polars, pushing, `claude-sonnet-5-5` (the first real pull request)

2026-11-15, on a fresh scratch clone of `hiivmind-corpus-data`, with `--param PUSH=true`. The run exited 0 with status `ok` and no failed node run, and opened https://github.com/hiivmind/hiivmind-corpus-data/pull/17 (branch `automated/corpus-refresh-polars-2026-11-15`; no stale or superseded refresh pull requests). Wall time 5 min 18 s (record 00:48:31 to 00:53:49 UTC).

| What | Result |
|---|---|
| Source | `polars`, `updated` `5075c53` to `2d9938d`; 26 files changed |
| Entries | 20 modified, 0 added; 26 enriched, 0 skipped; nothing under "Needs attention" |
| Removed | 33 entries whose files are gone from `docs/source` (each was checked absent at both commits) |
| Verification | sampled 10, failed 0, no drift; 1 new concept candidate (`Contributing`: 3 entries) |
| Embeddings | `no-model`, lag 26 |
| Model calls | 36 (refresh 16, scan 5, enrich 15) |

Tokens, from `record.json`:

| Node run | Model calls | `tokens_sent` | Read from cache | Written to cache | Not cached |
|---|---|---|---|---|---|
| `refresh#1` | 16 | 475,908 | 423,393 (89.0%) | 52,481 | 34 |
| `scan#2` | 5 | 325,812 | 220,007 (67.5%) | 105,793 | 12 |
| `enrich#3` | 15 | 726,962 | 662,238 (91.1%) | 64,692 | 32 |
| Total | 36 | 1,528,682 | 1,305,638 (85.4%) | 222,966 (14.6%) | 78 |

The dead entries that step 3 left stale are removed (33 in the record); nothing is left under "Needs attention".

### Step 1c: Polars on a scratch copy, pushing, `claude-haiku-5-5` (the `refresh` sequence)

2026-11-17, run `refresh-20261116T133407Z-ed3063`, on a scratch clone of `hiivmind-corpus-data` whose `origin` is the private repository `hiivmind/hiivmind-corpus-data-scratch`, with `--param CORPUS_REPO=hiivmind/hiivmind-corpus-data-scratch --param PUSH=true`. The sequence ended `done` (exit 0) in 5 minutes and opened https://github.com/hiivmind/hiivmind-corpus-data-scratch/pull/1 (branch `automated/corpus-refresh-polars-2026-11-17`). Steps: checks met, `update-sources` updated, `scan[list]`, `scan[1]`, `index`, `concepts`, `verify`, `embed` done, `publish` published. It started from the same commit of `hiivmind-corpus-data` as step 4, and the corpus it committed matches step 4's result:

| What | Result |
|---|---|
| Source | `polars`, `updated` `5075c53` to `8c19cc2`; 26 files changed, all `M` |
| Entries | 112 before, 79 after: 33 removed by `drop_missing` (files gone from `docs/source` at the head), 20 marked stale by the update, 26 enriched (with 6 left stale by earlier runs), 0 skipped, none still stale |
| Config | only `last_commit_sha`, `last_indexed_at` and `index.last_updated_at` changed |
| Verification | sampled 10, failed 0, no drift; 4 concepts assigned; 1 new concept candidate (`Contributing`: 3 entries) |
| Embeddings | `no-model`, lag 26 |
| Model calls | 50 (update-sources 13, scan 6, index 3, concepts 4, verify 2, embed 4, publish 18) |

| Node run | Model calls | `tokens_sent` | Read from cache | Written to cache |
|---|---|---|---|---|
| `update-sources#1` | 13 | 159,395 | 145,820 | 13,547 |
| `scan#2` | 6 | 323,528 | 216,729 | 106,785 |
| `index#3` | 3 | 16,892 | 11,870 | 5,014 |
| `concepts#4` | 4 | 122,793 | 82,723 | 40,060 |
| `verify#5` | 2 | 24,397 | 7,299 | 17,092 |
| `embed#6` | 4 | 24,079 | 18,867 | 5,202 |
| `publish#7` | 18 | 241,996 | 225,158 | 16,800 |
| Total | 50 | 913,080 | 708,466 (77.6%) | 204,500 |

What the model wrote wrong, in the facts of `update-sources` and so in the pull request's body (the index itself, written by the tools, is right):
- `index_changes.removed` is 40; the update removed 0 and `drop_missing` 33;
- `removed_ids` lists 32 of the 33 (`polars:polars-on-premises/bare-metal/configuration/persistence.md` is missing);
- `update_errors` holds `excluded-by-config: none`, though nothing was excluded.

The owner accepted this (2026-11-17): real runs use `claude-sonnet-5-5`, the default when `AGENT_CORE_LANGGRAPH_MODEL` is not set, which copied the same figures correctly in step 4.

### Step 1d: `status` on Polars, `claude-sonnet-5-5`

2026-11-17, run `status-20261117T043727Z-f6b450`, on the owner's working clone (`config/polars.yaml`; `status` reads and changes nothing, and the clone's six changed files were the same after the run). The sequence ended `done` (exit 0) with 2 model calls. Step: `status` → `stale`. Facts: source `polars` `behind`, `index_format` `v2`, `stale_count` 36, `embeddings_lag` null (no embeddings table), `refresh_needed` true, `status_errors` none.

### Step 1d: `migrate` on better-auth, pushing, `claude-sonnet-5-5`

2026-11-17, on a fresh clone of `hiivmind/hiivmind-corpus-better-auth` in `~/agent-core-scratch/`, with `--param CORPUS_PATH=$HOME/agent-core-scratch/hiivmind-corpus-better-auth --param PUSH=true`.

1. **Run `migrate-20261117T043835Z-391175`** ended `failed` at `checkout-sources` (exit 1), with nothing written: `git clone failed: Remote branch canary not found in upstream origin`. The corpus tracked `canary`, which `better-auth/better-auth` no longer has; the indexed commit `a9e5301` is an ancestor of its `main`. With the owner's go-ahead, `config.yaml`'s `branch` was set to `main` and pushed to the corpus's `main` (`f0070d3`; the push bypassed the repository's "changes through a pull request" rule).
2. **Run `migrate-20261117T044746Z-fe5d98`** ended `done` (exit 0) in about 6 minutes, 44 model calls, and opened https://github.com/hiivmind/hiivmind-corpus-better-auth/pull/1 (branch `automated/corpus-refresh-better-auth-2026-11-17`, titled `corpus: migrate 2026-11-17`). Steps: checks met, `checkout-sources` done, `migrate` migrated (148 entries, tiered, sections `authentication`, `plugins`, `integrations`, `concepts`, `reference`; none skipped), `scan[list]`, `scan[1]` done, `scan[2]` to `scan[5]` failed, then `index`, `concepts`, `verify` (10 sampled, none failed), `embed` (skipped: no embeddings) and `publish` published.

   Of the five scan batches, one wrote its 30 entries. Three failed on the provider's rate limit (`429`, "Number of concurrent connections has exceeded your rate limit"), as the fan-out runs its batches at the same time; one ended `invalid_output` (`entries` missing after the one correction). The 118 entries of those batches are in the pull request as the migration wrote them: their v1 titles and summaries, `category: unknown`, and stale (CJW-8). The pull request was merged on the owner's instruction (`418082a`), so the next `enrich` on better-auth scans them again.

### Step 1d: `migrate` on atproto, pushing, `claude-sonnet-5-5`

2026-11-17, on a fresh clone of `hiivmind/hiivmind-corpus-atproto` in `~/agent-core-scratch/`, with `--param CORPUS_PATH=… --param PUSH=true`.

1. **Run `migrate-20261117T081852Z-eb466f`** ended `failed` at `checkout-sources` (exit 1), with nothing written. The source's `docs_root` is `src/app/[locale]`, and `git sparse-checkout set` refuses a directory with `[` in its name ("specify directories rather than patterns"). The git fragment now runs `git sparse-checkout set --skip-checks '<docs_root>'` (`10f2382`). `update-sources` uses the same fragment, so a refresh of atproto would have failed the same way.
2. **Run `migrate-20261117T082248Z-ca1213`** ended `done` (exit 0) in about 4 minutes, 42 model calls, and opened https://github.com/hiivmind/hiivmind-corpus-atproto/pull/3. `migrate` migrated 129 entries (single, none skipped). Of the five scan batches, `scan[2]` and `scan[5]` wrote 39 entries. `scan[1]`, `scan[3]` and `scan[4]`, three of the four that started together, failed on the provider's `429` "Number of concurrent connections has exceeded your rate limit", as in the better-auth run; `scan[5]` started after them and succeeded. The 90 entries of those batches are in the pull request stale, with their v1 titles and summaries.
3. **Run `migrate-20261117T084916Z-eb8373`**, after the core gained its retries (`hiivmind-agent-core` branch `provider-retries`: the model client retries up to 8 times, and a fan-out runs a batch the provider refused once more) and with `max_concurrency: 2`. It used a fresh clone and `PUSH=false`. It ended `done` (exit 0) in about 8 minutes, with 57 model calls. All five scan batches ended `done`, and all 129 entries were scanned; none is stale. No batch needed a second run. Whether the client retried a refusal is not recorded. The commit is on the local branch `automated/corpus-refresh-atproto-2026-11-17-2` of that clone; nothing was pushed.

### Not yet run

Step 5 (criterion 1 on a real corpus: exit 0, `already current`, no model call) is not run: `detect.py` prints `no-model`, so the embeddings lag stays above 0. It runs on a corpus whose embeddings are ready (`detect.py` prints `ready`) or on one with no `index-embeddings.lance/`; the result will say which.
