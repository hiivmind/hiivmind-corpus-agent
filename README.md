# hiivmind-corpus-agent

A corpus instance for [agent-core](../hiivmind-agent-core): the scheduled refresh of a documentation corpus, as a job with a model. `agent-core job instance.yaml refresh --settings config/<corpus>.yaml` checks a corpus against its upstream sources, brings its index up to date, commits the result on a new branch and, when `PUSH` is true, opens a pull request.

It is a copy of the existing refresh (`hiivmind-corpus` and `hiivmind-corpus-scheduler`), rewritten to the core's verbs; `PORT.md` lists which file came from which, at which revision. The existing plugin and the scheduler are unchanged.

## Requirements

- Python 3.12 or later and `uv`. `uv sync` installs the instance. `pyproject.toml` takes `agent-core[langgraph]` and `agent-tools` by path from `../hiivmind-agent-core`, so the core has to be checked out beside this repository; after any change to the core, run `uv sync --reinstall-package agent-core`.
- `git`, and `gh` logged in to GitHub. The job runs `gh pr list` (it only reads) even when `PUSH` is false.
- `yq`, the Go one (mikefarah, version 4). The snap `yq` cannot read a hidden directory, so a corpus must not be under a path with a hidden component (`.cache`, `.hiivmind`, ...); the tests keep their temporary directories in `test-tmp/` for this reason.
- `npx`, for the reference filesystem MCP server the nodes read and write files through (`instance.yaml`, `servers`).
- `ANTHROPIC_API_KEY` in the environment. The model is `AGENT_CORE_LANGGRAPH_MODEL`, `claude-sonnet-5-5` when it is not set.

## Run the job for a corpus

```bash
cd <this directory>
uv sync
uv run agent-core job instance.yaml refresh --settings config/polars.yaml
```

A corpus is named by its settings file (`config/polars.yaml`, `config/ibis.yaml`), layered over `config/base.yaml`:

| Setting | Meaning |
|---|---|
| `CORPUS_PATH` | the directory holding the corpus's `config.yaml`: the root of its repository, or a directory inside it |
| `CORPUS_REPO` | `owner/name` on GitHub: where the pull request goes, and where `gh pr list` looks for the open ones |
| `BRANCH_PREFIX` | the branches the job makes are `<BRANCH_PREFIX>-<date>`, then `-2`, `-3` ... when the name is taken |
| `BASE_BRANCH` | default `main` |
| `PUSH` | default `true`; `false` commits on the new local branch and stops: nothing is pushed and no pull request is made |

`--param KEY=VALUE` beats the environment (`HIIVMIND_CORPUS_<KEY>`), which beats the files. So a run on a clone somewhere else, that does not push, is

```bash
uv run agent-core job instance.yaml refresh --settings config/polars.yaml --param CORPUS_PATH=/path/to/hiivmind-corpus-data/hiivmind-corpus-polars --param PUSH=false
```

and `--param CORPUS_REPO=someone/fork` sends the pull request to another repository. A setting that no file, variable or parameter gives stops the run before it starts, naming the setting (exit code 2).

What the job does, in order:

1. `repo_prepare`: stops when the working tree is dirty; checks out `BASE_BRANCH`, fetches `origin`, fast-forwards, and lists the earlier refresh branches and their open pull requests.
2. `corpus_status`, the freshness pre-check (no model): when every source is current and the embeddings are not behind, the job ends with status `already current` and has made no model call, no branch.
3. `repo_branch`, then the `refresh` node: updates each source that is behind, marks the index entries of changed files stale, adds an entry for each new file, removes the entry of each deleted one, records the new commits, renders `index.md`.
4. `stale_files`, then one `scan` node run for each batch of at most 30 stale files, all at the same time: each writes the metadata of its files and changes nothing. `apply_scan` is the only writer of the index between them.
5. The `enrich` node: assigns existing concepts, checks a sample of the new summaries against the files, renders the index, embeds it when the embedding model is ready.
6. `repo_finish`: commits what changed under `CORPUS_PATH` (the commit message is the report); with `PUSH`, pushes the branch, opens the pull request and closes the earlier refresh pull requests it supersedes. Without changes it deletes the branch: status `no changes`.

A source of a kind other than git is reported and not refreshed (`skipped-manual`). A source that fails (its upstream cannot be reached, the commit the corpus was indexed at is no longer in its history) is reported `failed` with the reason and its entries stay as they were; the other sources go on, and the job exits 0.

The run is recorded in `runs/refresh-<UTC start>-<six hex digits>/record.json` (`--run-dir` chooses another directory; `runs/` is not committed): the status, the summary, the failed node runs, `model_calls`, and for each node run its `model_calls`, `tokens_sent`, `cache_read` and `cache_written`. The summary holds `status` (`refreshed`, `no changes` or `already current`), `branch`, `sources` (`id`, `type`, `status`, `old_sha`, `new_sha`, `files_changed`, `error`), `index_changes` (`added`, `modified`, `removed`), `enriched` and `enriched_ids`, `skipped` and `skipped_entries`, `needs_attention` (the entries still stale at the end, whatever the cause), `verification`, `new_concept_candidates`, `embeddings` and `embeddings_lag`, `errors`, `pr_url`, `superseded_prs` and `stale_prs`. The exit code is 0 when the job ran to its end, 1 when it failed (a dirty tree, a refresh that gave no result, a push or `gh` that failed), 2 when it could not start.

## Add a corpus

Write one settings file, `config/<corpus>.yaml`, with `CORPUS_PATH`, `CORPUS_REPO` and `BRANCH_PREFIX`; nothing else changes. The corpus must have a v2 `index.yaml`, a `config.yaml` with its sources, and its own `render-index.sh`, as the corpora of `hiivmind-corpus-data` do. The same three node files serve every corpus: nothing in them names one.

## Add a source kind

Git is the only kind handled. The seam is `tools/sources/__init__.py`. A kind is:

1. a module in `tools/sources/` with a class that has `freshness(source, corpus)`, returning `("current" | "behind" | "unknown", error or None)` without cloning or changing anything, as `tools/sources/git.py` does;
2. a line in `SOURCE_KINDS`, keyed by the source's `type`;
3. its reference document `reference/sources/<type>.md`, which the `refresh` node loads for each source of that type. Step 7 of the node sends every type but `git` to `skipped-manual`, and its Phase 3 describes how git gets the changed files; for a new kind that step lets the type through and the phase says, from the kind's document, how its changed files are found;
4. the server it needs, declared under `servers:` in `instance.yaml` (a web kind needs a fetch server; none is declared today).

The job, the other tools and the contracts of the nodes do not change.

## Run it on a schedule

The core has no scheduler (JOB-11); whatever the host provides (cron, a systemd timer, CI) starts the job. The line is:

```bash
cd <instance dir> && uv run agent-core job instance.yaml refresh --settings config/<corpus>.yaml
```

For a repository of several corpora, the scheduler runs that line once for each settings file, one after another, not at the same time: the corpora share one working tree, and a run starts by checking that it is clean and by checking out the base branch.

## Tests

```bash
uv run pytest -q                                          # no model: the scripted backend; about two minutes
set -a && . <file holding ANTHROPIC_API_KEY> && set +a
AGENT_CORE_LANGGRAPH_MODEL=claude-haiku-5-5 uv run pytest tests/model -m model -q    # calls a model; costs money
```

The suite builds a corpus and its upstream in `test-tmp/` and uses a stand-in `gh`: no test touches a real corpus repository or opens a pull request. The tests marked `model` run the job with the LangGraph backend on those fixture corpora (`PUSH=false`, apart from the one that pushes to a local bare repository and opens its pull request on the stand-in) and keep each run's directory under `runs/model-tests/<date>/<model>/<test>/`. Develop on `claude-haiku-5-5`; the pass bar is one pass on `claude-sonnet-5-5`.

## Acceptance runs

Run on 2026-11-15 (local time; the run records' UTC times are 2026-11-14, 13:13 to 13:20). Nothing was pushed and no pull request was opened.

### Steps 1 and 2: the fixture corpora, `claude-haiku-5-5`

`uv run pytest tests/model -m model -q`, each test once, one after the other: both passed on the first run.

| Test | Result | Model calls (refresh / scan / enrich) | Wall time |
|---|---|---|---|
| `test_the_fixture_corpus_is_refreshed_and_a_lost_commit_fails_its_source` (step 1, and Review Focus 2) | passed | first job 27 (15 / 4 / 8); second job 10 (refresh only) | 62 s and 22 s; 96 s with the fixture |
| `test_the_same_nodes_refresh_a_second_corpus_and_its_pull_request_goes_where_the_parameter_says` (step 2, criterion 11) | passed | 29 (17 / 3 / 9) | 70 s; 76 s with the fixture |

The first job refreshes the fixture corpus (`docs:a.md` modified, `docs:d.md` added, `docs:c.md` deleted upstream): the source is `updated` at the upstream's head, `a.md` is re-scanned and not stale, `d.md` has an entry, `c.md` has none, `index.md` is rendered again, there is one commit on a new branch, and the record lists the source and the two entries enriched. Then the upstream's history is rewritten (one new root commit; the commit the corpus tracks is unreachable) and the job runs again on a clean copy of the source: the source is `failed` with "commit ... is not in the history of main", its entries stay as they were, nothing is committed (`no changes`), the exit code is 0. The second test uses a corpus with another name, another source id (`guide`) and another docs root (`manual/`), the same node files, `--param CORPUS_REPO=someone/other --param PUSH=true`: the branch is pushed to the test's own bare repository and the stand-in `gh` is called for `pr list` and `pr create`, both with `--repo someone/other` and no other.

### Step 3: Polars, without pushing, `claude-sonnet-5-5`

The corpus is a fresh clone of `https://github.com/hiivmind/hiivmind-corpus-data` made for the run, in `~/agent-core-scratch/hiivmind-corpus-data/` (not the owner's working clone, which is older), at `b56f6ce`. From the instance directory:

```bash
uv run agent-core job instance.yaml refresh --settings config/polars.yaml \
  --param CORPUS_PATH=$HOME/agent-core-scratch/hiivmind-corpus-data/hiivmind-corpus-polars --param PUSH=false
```

The run needs the real `gh`: the job runs `gh pr list --repo hiivmind/hiivmind-corpus-data` (it only reads; `PUSH=false` leaves `gh pr create` and `gh pr close` out), and it found no open refresh pull request. It exited 0 in 3 min 50 s (the record: 13:16:28 to 13:20:12 UTC) with status `ok` and no failed node run.

| What | Figure |
|---|---|
| Sources | 1: `polars`, `https://github.com/pola-rs/polars`, `docs/source`, git; `updated` `5075c53` to `36ea0f9` |
| Files | 190 files under `docs/source` upstream (87 Markdown); 26 changed between the two commits, of which 20 have an index entry (`modified` 20, `added` 0, `removed` 0) |
| Entries | 112 in the index before and after (the fresh clone's index is not the 111 of the owner's older copy); 37 stale before the run, 52 to scan after the refresh (37, plus the 20 modified, 5 of them already stale), 26 after the run |
| Scans | 2 node runs at the same time (batches of 30 and 22 files); 26 entries came back from the scans and 26 files had no scan; 26 enriched, 26 skipped, 26 under "Needs attention" |
| Verification | sampled 10, failed 0, no drift; 1 new concept candidate (`Contributing`: 3 entries), nothing written to `graph.yaml` |
| Embeddings | `no-model` (`detect.py` printed it): not updated, lag 5, as before |
| Commit | one, `corpus: refresh 2026-11-15`, on `automated/corpus-refresh-polars-2026-11-15` in the scratch clone: `config.yaml` (6 lines: `last_commit_sha`, `last_indexed_at`, `index.last_updated_at`), `index.yaml`, `index.md`; its message is the report. No pull request (`pr_url` null) |

Model calls and tokens for each node run, from `record.json` (`tokens_sent` is all the input of the run's calls, cached or not; the record keeps no count of output tokens):

| Node run | Model calls | `tokens_sent` | Read from cache | Written to cache | Not cached |
|---|---|---|---|---|---|
| `refresh#1` | 18 | 508,781 | 456,435 (89.7%) | 52,308 | 38 |
| `scan#2` (30 files) | 4 | 163,625 | 91,177 (55.7%) | 72,438 | 10 |
| `scan#3` (22 files) | 4 | 113,339 | 66,010 (58.2%) | 47,319 | 10 |
| `enrich#4` | 11 | 612,320 | 542,057 (88.5%) | 70,239 | 24 |
| Total | 37 | 1,398,065 | 1,155,679 (82.7%) | 242,304 (17.3%) | 82 |

What went right: all four node runs ended `done` on the first run, with no question to the person and no failed run in the record; the refresh resolved the tracked commit in the shallow clone and recorded the new commit and time with edits of `config.yaml` that touch only those lines; the enriched entries I read (summaries, keywords, headings, concepts from the existing graph) are good. The procedures did not need a fix, so the run was not repeated.

What went wrong, or is not as it should be:

- **`index.yaml` is rewritten from top to bottom.** `apply_scan` writes the whole file with PyYAML, and the index on `main` of `hiivmind-corpus-data` is in another layout (list items indented under their key, other quoting) than the one the writer produces; the owner's older copy, which the round-trip test reads, was in the writer's layout. The diff of `index.yaml` is 2,647 lines added and 1,500 removed for 26 entries that changed, which makes the pull request's index diff unreadable, though the entries I read back look right; the file's layout is not kept. A round-trip of the index on `main` through the writer is not byte-identical (3,093 changed lines); with indented lists it is 174. This is for the owner to decide before step 4: `apply_scan` could edit the entries in place or keep the file's layout.
- **26 stale entries point at files that are not in the source.** They are the 25 `polars-on-premises/...` entries and `polars-cloud/run/distributed-engine.md`, stale since 2026-06-30 (16) or 2026-07-06 (10), and no such file exists under `docs/source` at `5075c53` or at `36ea0f9`. The refresh cannot see them (they are not in the diff between the two commits), the scans find no file, so they stay stale and are listed under "Needs attention", as Review Focus 5 expects. They need a decision about the data (remove the entries), not a change to the job.
- **The embeddings stay 5 entries behind**: `detect.py` prints `no-model` on this machine, so `enrich` does not embed (it never downloads the model during a refresh).
- **Noise on the terminal**: the filesystem MCP server prints a line for each request and, after eleven, a Node `MaxListenersExceededWarning`; the job itself prints nothing, its summary is in `record.json`.

### Not yet run

Step 4 (the pull request of criterion 2, `PUSH=true` on the owner's choice of `CORPUS_REPO`) waits for the owner's word, and step 5 (criterion 1 on a real corpus: exit 0, `already current`, no model call) follows it. Step 5 runs on a corpus whose embeddings are ready (`detect.py` prints `ready`) or, as `detect.py` prints `no-model` here, on one with no `index-embeddings.lance/`; the result will say which.
