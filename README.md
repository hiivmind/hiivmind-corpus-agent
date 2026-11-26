# hiivmind-corpus-agent

A corpus instance of [agent-core](https://github.com/hiivmind/hiivmind-agent-core): the refresh of a documentation corpus, written as a client of the core's facade (`agent_core.open`). It checks a corpus against its upstream sources, brings its index up to date, commits the result on a new branch and, when `PUSH` is true, opens a pull request.

## Layout

| Path | What it holds |
|---|---|
| `instance.yaml` | the instance: backend, servers, settings class, and the tools `agent_core.open` registers through `harness.tools.register` |
| `nodes/<name>.md` | one instruction file per node: `update-sources`, `scan`, `index`, `concepts`, `verify`, `embed`, `publish`, `checkout-sources`, `status`, `migrate`, `graph-validate`, `prepare-base`, `check-upstream` (13 nodes) |
| `includes/` | the documents of `hiivmind-corpus-lib` (`embeddings.md`, `entry-metadata.md`, `freshness.md`, `graph.md`, `index-fields.md`) and the git procedures in `includes/sources/` (`git.md`, `upstream-head.md`), pulled in with `{{include includes/...}}` |
| `tools/corpus.py` | the 22 tools: thin functions over `Corpus` of `hiivmind-corpus-lib` (`hiivmind_corpus_lib`) |
| `topology.yaml` | the nodes, the fragment `enrich-and-publish` and the sequences |
| `settings.py`, `config/*.yaml` | the settings class and one settings file per corpus, over `config/base.yaml` |
| `POLICY.md` | the policy: no force push, no history rewrite |
| `tests/` | tests through the facade, on the scripted backend |

`hiivmind-corpus-lib` and `hiivmind-agent-core` are checked out beside this repository; `pyproject.toml` takes both by path, so `uv sync` fails without them. They are installed editable: the instance runs whatever the two checkouts hold, on whichever branch they are, with no reinstall.

## Topology

The sequences are `refresh`, `status`, `enrich`, `migrate` and `graph-validate`. Checks make no model call: `graph-validate` checks that the corpus has a `graph.yaml`, `status` has no checks, and `refresh`, `enrich` and `migrate` hold theirs in their `-prepared` sequences.

`refresh`, `enrich` and `migrate` start at the node `prepare-base`, which puts the corpus on its base branch, level with origin, and link to `refresh-prepared`, `enrich-prepared` and `migrate-prepared`: the core runs a sequence's checks before its start, so the checks of the `-prepared` sequence run on the prepared tree. `refresh-prepared` starts at `check-upstream`; `enrich-prepared` and `migrate-prepared` start at `checkout-sources`.

`refresh`, `enrich` and `migrate` end in the same tail, declared once as the fragment `enrich-and-publish`: `scan` fans out over the stale batches, then `index`, `concepts`, `verify`, `embed` and `publish`. Each of the three sequences names the fragment. `publish` is also named at sequence level in `refresh`, so a skipped `update-sources` still publishes.

## Run a sequence

```bash
uv sync
uv run agent-core job instance.yaml <sequence> --settings config/<corpus>.yaml [--param KEY=VALUE ...]
```

- `--param` beats the environment (`HIIVMIND_CORPUS_<KEY>`), which beats the settings files.
- `config/base.yaml` sets `PUSH: false`; a run pushes only with `--param PUSH=true`.
- `CORPUS_PATH` is the corpus's directory, `CORPUS_REPO` is `owner/name` for the pull request, `BRANCH_PREFIX` names the branch, `BASE_BRANCH` defaults to `main`. Run on a scratch clone with `--param CORPUS_PATH=... --param PUSH=false`.
- A relative `CORPUS_PATH` (or one starting `~`) is made absolute against the working directory when the settings load. The files in `config/` expect the corpora checked out beside this repository (`../hiivmind-corpus-data/hiivmind-corpus-polars`) and the job run from here.
- A run is recorded in `runs/<sequence>-<UTC start>-<id>/record.json`; `--resume <run id>` continues a crashed run.
- Exit code: 0 when the sequence ends `done` or `stopped`, 1 when it ends `failed`, 2 when it could not start.

Needs `git`, `npx`, `gh` when `PUSH` is true, the provider credential (`ANTHROPIC_API_KEY`) in the environment, and `AGENT_CORE_LANGGRAPH_MODEL`, which is required, in `provider:model` form with no default, for example `anthropic:claude-sonnet-5-5`. Without it the CLI exits 2.

### Embeddings

The instance installs `hiivmind-corpus-lib[embeddings]`, so the `embed` node keeps a corpus's `index-embeddings.lance/` up to date and `status` computes the embeddings lag. A run never downloads the model: `embed` ends `no-model` until `BAAI/bge-small-en-v1.5` is in the fastembed cache. fastembed's default cache is `<tmp>/fastembed_cache`, which the system may clear. Use a lasting cache and fill it once:

```bash
export FASTEMBED_CACHE_PATH=~/.cache/fastembed     # in the shell that runs the jobs
uv run python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"
```

The `embed` node embeds index entries only. Chunk embeddings (`corpus.embeddings.embed_chunks`) wait for a node that searches chunks.

## Tests

```bash
uv run pytest -q                  # no model: the scripted backend
uv run pytest tests/model -m model -q   # calls a model; costs money
```

`tests/test_language.py` checks that no file of the tree calls a node anything but a node, and that no procedure names an SDK.

## v0 runs

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

2026-11-17, run `refresh-20261116T133407Z-ed3063`, on a scratch clone of `hiivmind-corpus-data` whose `origin` is a private scratch copy of it, `hiivmind/hiivmind-corpus-data-scratch`, with `--param CORPUS_REPO=hiivmind/hiivmind-corpus-data-scratch --param PUSH=true`. The sequence ended `done` (exit 0) in 5 minutes and opened pull request #1 on that copy (branch `automated/corpus-refresh-polars-2026-11-17`). Steps: checks met, `update-sources` updated, `scan[list]`, `scan[1]`, `index`, `concepts`, `verify`, `embed` done, `publish` published. It started from the same commit of `hiivmind-corpus-data` as step 4, and the corpus it committed matches step 4's result:

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
2. **Run `migrate-20261117T044746Z-fe5d98`** ended `done` (exit 0) in about 6 minutes, 44 model calls, and opened pull request #1 on `hiivmind/hiivmind-corpus-better-auth`, a private repository (branch `automated/corpus-refresh-better-auth-2026-11-17`, titled `corpus: migrate 2026-11-17`). Steps: checks met, `checkout-sources` done, `migrate` migrated (148 entries, tiered, sections `authentication`, `plugins`, `integrations`, `concepts`, `reference`; none skipped), `scan[list]`, `scan[1]` done, `scan[2]` to `scan[5]` failed, then `index`, `concepts`, `verify` (10 sampled, none failed), `embed` (skipped: no embeddings) and `publish` published.

   Of the five scan batches, one wrote its 30 entries. Three failed on the provider's rate limit (`429`, "Number of concurrent connections has exceeded your rate limit"), as the fan-out runs its batches at the same time; one ended `invalid_output` (`entries` missing after the one correction). The 118 entries of those batches are in the pull request as the migration wrote them: their v1 titles and summaries, `category: unknown`, and stale (CJW-8). The pull request was merged on the owner's instruction (`418082a`), so the next `enrich` on better-auth scans them again.

### Step 1d: `migrate` on atproto, pushing, `claude-sonnet-5-5`

2026-11-17, on a fresh clone of `hiivmind/hiivmind-corpus-atproto` in `~/agent-core-scratch/`, with `--param CORPUS_PATH=… --param PUSH=true`.

1. **Run `migrate-20261117T081852Z-eb466f`** ended `failed` at `checkout-sources` (exit 1), with nothing written. The source's `docs_root` is `src/app/[locale]`, and `git sparse-checkout set` refuses a directory with `[` in its name ("specify directories rather than patterns"). The git fragment now runs `git sparse-checkout set --skip-checks '<docs_root>'` (`10f2382`). `update-sources` uses the same fragment, so a refresh of atproto would have failed the same way.
2. **Run `migrate-20261117T082248Z-ca1213`** ended `done` (exit 0) in about 4 minutes, 42 model calls, and opened pull request #3 on `hiivmind/hiivmind-corpus-atproto`, a private repository. `migrate` migrated 129 entries (single, none skipped). Of the five scan batches, `scan[2]` and `scan[5]` wrote 39 entries. `scan[1]`, `scan[3]` and `scan[4]`, three of the four that started together, failed on the provider's `429` "Number of concurrent connections has exceeded your rate limit", as in the better-auth run; `scan[5]` started after them and succeeded. The 90 entries of those batches are in the pull request stale, with their v1 titles and summaries.
3. **Run `migrate-20261117T084916Z-eb8373`**, after the core gained its retries (`hiivmind-agent-core` branch `provider-retries`: the model client retries up to 8 times, and a fan-out runs a batch the provider refused once more) and with `max_concurrency: 2`. It used a fresh clone and `PUSH=false`. It ended `done` (exit 0) in about 8 minutes, with 57 model calls. All five scan batches ended `done`, and all 129 entries were scanned; none is stale. No batch needed a second run. Whether the client retried a refusal is not recorded. The commit is on the local branch `automated/corpus-refresh-atproto-2026-11-17-2` of that clone; nothing was pushed.

### Not yet run

Step 5 (criterion 1 on a real corpus: exit 0, `already current`, no model call) is not run: `detect.py` prints `no-model`, so the embeddings lag stays above 0. It runs on a corpus whose embeddings are ready (`detect.py` prints `ready`) or on one with no `index-embeddings.lance/`; the result will say which.

## Cutover gate, 2026-11-19

REB-1 on the new build: `agent-core job` on LangGraph, `AGENT_CORE_LANGGRAPH_MODEL=anthropic:claude-sonnet-5-5`, `--no-ask`, `PUSH=false`, scratch clones only. Origins are local bare repos in `~/agent-core-scratch/gate/` cloned read-only from GitHub; nothing was pushed. Each produced tree was checked in a worktree of the working clone (under `~/agent-core-scratch/gate/`, not `/tmp`: the snap-packaged `yq` that `render-index.sh` calls cannot read `/tmp`).

Result: both runs ended `done` with exit 0, and both produced trees load and render.

### `refresh` on Polars (stale clone `gate-stale` at `1a67fe0`)

```bash
AGENT_CORE_LANGGRAPH_MODEL=anthropic:claude-sonnet-5-5 uv run agent-core job instance.yaml refresh \
  --settings config/polars.yaml --param CORPUS_PATH=$HOME/agent-core-scratch/gate/data/hiivmind-corpus-polars \
  --param BASE_BRANCH=gate-stale --param PUSH=false --no-ask
```

- Run `refresh-20261119T055339Z-f18c6b`; exit 0; `end_state` `done`; 5 m 26 s.
- Steps: `checks` met; `update-sources` updated (`5eaa754` to `b145ff9`, 29 files changed); `enrich-and-publish` committed (`scan[list]`, `scan[1]`, `scan`, `index`, `concepts`, `verify`, `embed`, `publish` committed). 28 entries enriched; no failures, update errors, index errors or scan failures.
- Model calls: 40 (update-sources 10, scan 7, index 3, concepts 4, verify 2, embed 4, publish 10). Tokens sent 781,522 (cache read 574,622, cache written 206,806).
- Produced branch `automated/corpus-refresh-polars-2026-11-19`; validated commit `7c5319831ad3cddfbbd96373e8165f106c5e560d`.
- Index check, in `hiivmind-corpus-polars`: `load_index` printed `2` (the brief's `len()` of the loaded dict: its keys `meta` and `entries`; `entries` holds 80); `bash render-index.sh index.yaml` printed `Rendered ./index.md (80 entries)`, exit `0`, tree left clean.

### `migrate` on atproto (v1 clone `gate-v1`, parent of `32c014f`, the commit that added `index.yaml`)

```bash
AGENT_CORE_LANGGRAPH_MODEL=anthropic:claude-sonnet-5-5 uv run agent-core job instance.yaml migrate \
  --settings config/atproto.yaml --param CORPUS_PATH=$HOME/agent-core-scratch/gate/atproto \
  --param BASE_BRANCH=gate-v1 --param PUSH=false --no-ask
```

- Run `migrate-20261119T055942Z-8702ba`; exit 0; `end_state` `done`; 6 m 42 s.
- Steps: `checks` met; `checkout-sources` done (1 checkout, no errors); `migrate` migrated (129 entries, strategy `single`); `enrich-and-publish` committed (`scan[list]`, `scan[1]` to `scan[5]`, `scan`, `index`, `concepts`, `verify`, `embed`, `publish` committed). 129 entries enriched; no failures or skipped entries.
- Model calls: 59 (checkout-sources 9, migrate 2, scan 7+5+6+5+3, index 3, concepts 2, verify 2, embed 3, publish 12). Tokens sent 1,423,809 (cache read 886,293, cache written 537,374).
- Produced branch `automated/corpus-refresh-atproto-2026-11-19`; validated commit `140fb7c165c22bb8df1f1c135594983e30ef0364`.
- Index check: `load_index` printed `2` (keys `meta`, `entries`; `entries` holds 129); `bash render-index.sh index.yaml` printed `Rendered ./index.md (129 entries)`, exit `0`, tree left clean.

## Capabilities gate, 2026-11-20

Stage 3 of the corpus-lib capabilities design (§10): `agent-core job` on LangGraph, `AGENT_CORE_LANGGRAPH_MODEL=anthropic:claude-sonnet-5-5`, `--no-ask`, `PUSH=false`, scratch clones only. Origins are local bare repos in `~/agent-core-scratch/capabilities/` (`data-origin.git`, branch `gate-stale` at `1a67fe0`; `atproto-origin.git`, branch `gate-v1` at `15e064f`, the parent of `32c014f`, the commit that added `index.yaml`); nothing reached GitHub, and no clone was edited by hand. The instance was at `89057dd` and `hiivmind-corpus-lib` (branch `capabilities`) at `d1ccabf`. Stage 1, `uv run pytest -q` in `hiivmind-corpus-lib`: 404 passed in 18 s. Stage 2, `uv run pytest -q` here: 136 passed, 4 model tests deselected, in 6 m 33 s. Every produced tree was checked in a worktree of the clone, under `~/agent-core-scratch/capabilities/`.

Result: four runs, all ended `done` with exit 0, none failed, no fix was needed. Real `embed` is not in the gate: the instance installs the package without the `embeddings` extra, so `embed` ended `done` with `embeddings` `not-installed`, and where the corpus holds an `index-embeddings.lance/` the lag call's `ExtraMissing` is in the commit message under `## Errors`.

The evidence collector (`~/agent-core-scratch/capabilities/collect.py`, not committed) does what the CLI does: it opens the harness on the instance, runs the sequence and writes `record.json`. Because the record keeps no model output, it also prints from `harness.events.record()` (a) the keys of the `outputs` of each `exit` call of each `update-sources` node run and (b) the text each `apply_source_update` and `drop_missing` call returned. `verify_tree.py`, beside it, loads each file of a produced tree and renders `index.md`.

### `status` on Polars (clone `gate-stale` at `1a67fe0`)

```bash
AGENT_CORE_LANGGRAPH_MODEL=anthropic:claude-sonnet-5-5 uv run agent-core job instance.yaml status \
  --settings config/polars.yaml --param CORPUS_PATH=$HOME/agent-core-scratch/capabilities/data/hiivmind-corpus-polars \
  --param BASE_BRANCH=gate-stale --param PUSH=false --no-ask
```

- Run `status-20261120T042912Z-91fde8`; exit 0; `end_state` `done`; 11 s. Step: `status` `stale`.
- Facts: `sources[0]` `polars` `freshness` `behind` (`last_commit_sha` `5eaa754`; `git ls-remote https://github.com/pola-rs/polars refs/heads/main` printed `e02c237a6b9055f23f33ae632b0490286a579e2e`), `index_format` `v2`, `stale_count` 36, `embeddings_lag` null, `refresh_needed` true, `status_errors` `embeddings lag not computed: install hiivmind-corpus-lib[embeddings]`.
- Model calls: 4. Tokens sent 25,192 (cache read 18,461, cache written 6,721). The clone was unchanged.

### `refresh` on Polars (clone `gate-stale` at `1a67fe0`)

The same arguments with `refresh`, through the collector (`uv run python ~/agent-core-scratch/capabilities/collect.py job instance.yaml refresh …`).

- Run `refresh-20261120T042944Z-4071d0`; exit 0; `end_state` `done`; 3 m.
- Steps: `prepare-base` prepared; `checks` met; `check-upstream` behind; `update-sources` updated (`5eaa754` to `e02c237`, 29 files changed); `enrich-and-publish` committed (`scan[list]`, `scan[1]`, `scan`, `index`, `concepts`, `verify`, `embed`, `publish` committed). 28 entries enriched; no failures, update errors, index errors or scan failures.
- Model calls: 46 (prepare-base 6, check-upstream 4, update-sources 12, scan 3, index 2, concepts 3, verify 2, embed 4, publish 10). Tokens sent 593,523 (cache read 380,342, cache written 213,071).
- Produced branch `automated/corpus-refresh-polars-2026-11-20`; validated commit `c147562b7a6d8b9eb033888b892267b72a3aaeb9`. `git diff --stat 1a67fe0..c147562`: 3 files changed, 1,266 insertions, 745 deletions (`config.yaml` 12 lines, `index.md` 101, `index.yaml` 1,898). This is C2: the first write of a published `index.yaml` and `config.yaml` in canonical form.
- (a) The `exit` call of `update-sources#3` had `outputs` keys `sources` and `update_errors`: none of `index_changes`, `removed_ids`, `excluded_paths`.
- (b) `apply_source_update` returned `files_changed` 29, `added` 1, `modified` 22, `removed` 0, `removed_ids` empty, 23 `stale_entries`, `excluded` 0; `drop_missing` returned 33 `removed_ids`. The record's `facts.index_changes` (`added` 1, `modified` 22, `removed` 0, the same 23 `stale_entries`) equals what `apply_source_update` recorded; `facts.removed_ids` (33) equals what `drop_missing` returned and recorded; `facts.excluded_paths` is empty. The commit message holds `1 added, 22 modified, 0 removed`, `Removed 33 entries whose files are gone from the source:` with the same 33 ids, and `Enriched: 28 entries`.
- Tree, in a worktree of the branch, in `hiivmind-corpus-polars`: `Config.loads(text).dumps() == text` for `config.yaml`, and `Index.loads(text).dumps() == text` for `index.yaml` (80 entries); `Corpus.open(".").render.texts()["index.md"]` equals `index.md`. The run did not write `graph.yaml` (a schema 2 graph holds no entry ids, so a refresh has nothing to remove from it); it is byte for byte the base commit's hand-written layout, so `Graph.loads(text).dumps() == text` is false for it, and it loads and its `dumps` is a fixed point. `render-index.sh` is still in the tree, as the base commit has it.

### A second `refresh` on Polars, after the first commit is merged

The first commit was merged on the scratch origin (`git -C data push origin automated/corpus-refresh-polars-2026-11-20:gate-stale`: `gate-stale` `1a67fe0` to `c147562`); the same command as the first `refresh`.

- Run `refresh-20261120T043431Z-70f93f`; exit 0; `end_state` `done`; 23 s; `summary` `Already current.`
- Steps: `prepare-base` prepared (the clone fast-forwarded to `c147562`); `checks` met; `check-upstream` current. Upstream was still `e02c237`. No branch and no commit; the clone stayed clean on `gate-stale`.
- Model calls: 10 (prepare-base 6, check-upstream 4). Tokens sent 60,641 (cache read 58,914, cache written 1,703).

### `migrate` on atproto (v1 clone `gate-v1`, parent of `32c014f`)

```bash
AGENT_CORE_LANGGRAPH_MODEL=anthropic:claude-sonnet-5-5 uv run agent-core job instance.yaml migrate \
  --settings config/atproto.yaml --param CORPUS_PATH=$HOME/agent-core-scratch/capabilities/atproto \
  --param BASE_BRANCH=gate-v1 --param PUSH=false --no-ask
```

- Run `migrate-20261120T043507Z-8f84b3`; exit 0; `end_state` `done`; 5 m 20 s.
- Steps: `prepare-base` prepared; `checks` met; `checkout-sources` done (1 checkout, no errors); `migrate` migrated (129 entries, strategy `single`, no section, none skipped); `enrich-and-publish` committed (`scan[list]`, `scan[1]` to `scan[5]`, `scan`, `index`, `concepts`, `verify`, `embed`, `publish` committed). 129 entries enriched; no failures or skipped entries; no batch failed.
- Model calls: 56 (prepare-base 6, checkout-sources 10, migrate 2, scan 4+4+5+4+3, index 2, concepts 2, verify 2, embed 3, publish 9). Tokens sent 1,021,041 (cache read 558,337, cache written 462,566).
- Produced branch `automated/corpus-refresh-atproto-2026-11-20`; validated commit `e55287d60717b97a290918503123291c331d08bf`. `git diff --stat gate-v1..e55287d`: 3 files changed, 5,890 insertions, 320 deletions (`config.yaml` 72 lines, `index.md` 427, `index.yaml` 5,711, new).
- Tree, in a worktree of the branch: `config.yaml` and `index.yaml` canonical (`loads(text).dumps() == text`); `index.md` equals `Corpus.open(".").render.texts()["index.md"]`; no `render-index.sh` (the tree holds `CLAUDE.md`, `LICENSE`, `README.md`, `config.yaml`, `index.md`, `index.yaml`); the v1 `index.md` lists 129 ids and all 129 are entries of the new `index.yaml`, which holds no other; `migrated` 129 equals the entry count; none is stale and none has the category `unknown`.
- The commit message of a `migrate` carries `Sources: none looked at` and `not given` for the index changes, removed ids and excluded paths, because the sequence does not run `update-sources`.
