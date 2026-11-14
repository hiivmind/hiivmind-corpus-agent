---
name: refresh
description: Refresh the sources of the corpus named in the settings, mark the index entries of changed files stale, add and remove entries, record the new commits and report what changed. Handles git sources only.
inputs:
  sources: which sources to update, by id, or `all` for each source that is behind
outputs:
  sources:
    type: array
    description: one item for each source looked at, in the order of config.yaml
    items:
      type: object
      required: [id, type, status, old_sha, new_sha, files_changed]
      properties:
        status: {enum: [current, updated, failed, skipped-manual]}
        error: {type: string}
  index_changes: {type: object, required: [added, modified, removed, stale_entries]}
  embeddings: {enum: [updated, skipped, no-model, not-installed, deferred]}
  embeddings_lag: {type: [integer, "null"]}
  errors: {type: array, items: {type: string}}
exits: [done, declined, failed]
allowed-tools: [shell__run, files__read_text_file, files__write_file, files__edit_file, files__search_files, files__list_directory]
preconditions:
  - tool: shell__run
    args: {command: "test -f {{settings.CORPUS_PATH}}/config.yaml && test -f {{settings.CORPUS_PATH}}/index.yaml"}
    message: "The corpus at {{settings.CORPUS_PATH}} has no config.yaml or no built index."
context: none
---
# Refresh

Brings the index of one corpus up to date with its sources. It finds the files that changed upstream, marks the index entries of changed files stale, adds an entry for each new file, removes the entry of each deleted file, and records the commit each source is now at. It does not read the changed files: the `scan` node writes the metadata of the stale entries afterwards. The sources are worked one after another.

Corpus: {{settings.CORPUS_PATH}}.
Sources to update: {{input.sources}}.

Keep a list `errors`, empty to begin with, and one record for each source looked at: `id`, `type`, `status`, `old_sha`, `new_sha`, `files_changed` and, for a source that failed or was skipped, `error`. A sha in a record is the first seven characters of the commit.

## Phase 1: Validate
Outputs: the sources to work on.

1. If "Sources to update" reads "not given", ASK "Which sources should I update?". When the person answers, STATE.set `sources` to the answer. If the answer says that no source is to be updated, EXIT `declined` with output `reason` saying so.
2. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/config.yaml`. If it returns an error, EXIT `failed` with output `reason` set to the error.
3. If `config.yaml` has no `sources` or the list is empty, EXIT `failed` with output `reason` set to "config.yaml has no sources".
4. CALL `shell__run` with the command `if [ ! -f {{settings.CORPUS_PATH}}/index.yaml ]; then echo v1; elif grep -qs "Run hiivmind-corpus-build" {{settings.CORPUS_PATH}}/index.md; then echo placeholder; else echo built; fi`.
   - It prints `v1`: EXIT `failed` with output `reason` set to "v1-index: read-only, run hiivmind-corpus-migrate".
   - It prints `placeholder`: EXIT `failed` with output `reason` set to "index.md is a placeholder: the index is not built".
5. Choose the sources to work on, from the sources of `config.yaml`. When "Sources to update" is `all` (or the answer to step 1 is), take every source. Otherwise take the ids it names, which are separated by commas or spaces. An id that is not a source of `config.yaml` is left out and `unknown source: <id>` is added to `errors`. If no source is left, EXIT `failed` with output `reason` set to "none of the sources named is in config.yaml".

## Phase 2: Check freshness
Outputs: the status of each source, and which sources are behind.

For each source chosen in step 5, in the order of `config.yaml`:

6. CALL `load` with the path `reference/sources/<type>.md`, `<type>` being the source's `type`. Do this once for each type. If the call returns an error, this instance has no document for that kind of source and does not handle it: its record is `status: skipped-manual`, `old_sha` and `new_sha` null, `files_changed` 0, and `error` set to "source type `<type>` is not handled by this instance yet". Leave this source alone in every later step and go on to the next.
7. The source is a git source. CALL `shell__run` with the command `GIT_TERMINAL_PROMPT=0 git ls-remote <repo_url> refs/heads/<branch>`, with the source's `repo_url` and `branch` (`main` when it has none) written out.
   - If the call exits with an error or prints nothing, its record is `status: failed` with `error` set to what the command said, `old_sha` the first seven characters of `last_commit_sha`, `new_sha` null, `files_changed` 0. Add `<id>: <error>` to `errors`.
   - If the first field of the output is the source's `last_commit_sha`, its record is `status: current`, `old_sha` and `new_sha` both its first seven characters, `files_changed` 0.
   - Otherwise the source is behind: it is to be updated, and its `old_sha` is the first seven characters of `last_commit_sha`.
8. If no source is behind, there is nothing to apply: skip Phases 3 and 4 and set `index_changes` to `added` 0, `modified` 0, `removed` 0, `stale_entries` empty. Go to step 22.

## Phase 3: Update sources
Outputs: the changed files of each source that is behind, as `A`, `M` or `D` with a path.

Update each source that is behind, one after the other. A source that fails does not stop the others: its record is `status: failed` with `error` set to what went wrong, its `new_sha` null and `files_changed` 0, `<id>: <error>` is added to `errors`, its entries are left as they were, and you go on with the next source.

The working copy of a source is `<clone>` = `{{settings.CORPUS_PATH}}/.source/<id>`, where `<id>` is the source's `id`. Follow the sections of `reference/sources/git.md` on the sparse clone and on never using the GitHub compare API. Never use the GitHub compare API to find the changed files (`gh api repos/<owner>/<repo>/compare/...`): it stops at 300 files and drops the rest without saying so. Find them with a local `git diff` in the clone.

9. CALL `shell__run` with the command `test -d <clone>/.git && echo cloned || echo missing`, the path written out.
10. If it printed `missing`, CALL `shell__run` with the command `mkdir -p {{settings.CORPUS_PATH}}/.source && git clone --filter=blob:none --sparse --depth=50 --branch <branch> <repo_url> <clone>`. Then CALL `shell__run` with `git -C <clone> sparse-checkout set <docs_root>`; when the source's `docs_root` is `.` or none, use `git -C <clone> sparse-checkout disable` instead.
11. CALL `shell__run` with the command `git -C <clone> fetch --depth=50 origin <branch>`.
12. Make sure the commit the index was built at can be resolved, so that it can be diffed. CALL `shell__run` with `git -C <clone> cat-file -e <last_commit_sha>^{commit}`. If it exits with an error:
    1. CALL `shell__run` with `git -C <clone> rev-parse --is-shallow-repository`. If it prints `false`, the commit is not in the history of the branch: the source fails with the error "commit <last_commit_sha> is not in the history of <branch>".
    2. Otherwise deepen the clone: CALL `shell__run` with `git -C <clone> fetch --shallow-since=<last_indexed_at> origin <branch>`, then try `cat-file -e` again.
    3. If it still cannot be resolved, CALL `shell__run` with `git -C <clone> fetch --unshallow origin <branch>`, then try `cat-file -e` again. If it still cannot be resolved, the source fails with the error "commit <last_commit_sha> cannot be resolved, even with the full history".
13. CALL `shell__run` with `git -C <clone> checkout -q -B <branch> FETCH_HEAD`, then CALL `shell__run` with `git -C <clone> rev-parse HEAD`. That is the source's new commit, `<new_sha>`; its record's `new_sha` is its first seven characters.
14. CALL `shell__run` with `git -C <clone> diff --name-status --no-renames <last_commit_sha>..<new_sha> -- <docs_root>`. When `docs_root` is `.` or none, leave out `-- <docs_root>`. Each line is a status (`A` added, `M` modified, `D` deleted) and a path: a rename shows as a `D` and an `A`. Take `<docs_root>/` off the front of each path to get its path under the docs root; its entry id is `<id>:<path>`. The record is `status: updated` and `files_changed` is the number of lines. If the diff has no line, the record is still `updated` with `files_changed` 0.

## Phase 4: Apply changes to the index
Outputs: `index_changes`.

Skip this phase when no source was updated; set `index_changes` as step 8 says and go to step 22.

15. CALL `load` with the path `reference/index-updating.md`. Its section "v2 format" says how each change is applied, and its section "Updating config.yaml after index changes" says what is recorded afterwards. The v1 rules are not used.
16. CALL `shell__run` with the command `date -u +%Y-%m-%dT%H:%M:%SZ`. That is "now" in the steps below.
17. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/index.yaml`.
18. Count the changes in `index_changes`: `added`, `modified`, `removed` as numbers, and `stale_entries`, the list of entry ids that were marked stale or added. For each source that was updated, for each of its changes, change `{{settings.CORPUS_PATH}}/index.yaml` with `files__edit_file`, one entry at a time, the old text being the exact text of that entry in the file:
    - `M`: if the index has the entry, set `stale: true` and `stale_since` to now, and change nothing else (keep its summary, tags, keywords, concepts and links). Add one to `modified` and its id to `stale_entries`. If it has no such entry, do nothing.
    - `A`: if the `build` block of `config.yaml` has `skip_sections` that exclude the path, add no entry and add `excluded-by-config: <path>` to `errors`. Otherwise add an entry after the last one, as the document says: `id`, `source`, `path`, `stale: true`, `stale_since` now, `category: unknown`, `summary: Pending re-scan`, `section` as the document says (the source's id when `build.organization` is `by-source` and the corpus is tiered, otherwise null), and `tags`, `keywords` and `concepts` empty. Add one to `added` and its id to `stale_entries`.
    - `D`: remove the whole entry, then CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/graph.yaml` (if it returns an error, there is no graph: go on) and remove from it the id where it is listed. Add one to `removed`.

    If an edit fails, add `index update failed: <error>` to `errors` and go on with the next change; what was saved stays saved.
19. CALL `shell__run` with the command `yq '.entries | length' {{settings.CORPUS_PATH}}/index.yaml`. With `files__edit_file`, set `meta.generated_at` of `index.yaml` to now and `meta.entry_count` to that number.
20. With `files__edit_file` on `{{settings.CORPUS_PATH}}/config.yaml`, for each source that was updated set `last_commit_sha` to its `<new_sha>` (the full commit) and `last_indexed_at` to now, and set `index.last_updated_at` to now. A source that failed keeps its `last_commit_sha`. If an edit fails, add `config save failed: <error>` to `errors`.
21. CALL `shell__run` with the command `cd {{settings.CORPUS_PATH}} && bash ./render-index.sh index.yaml`. If it exits with an error, add `index.md not rendered: <error>` to `errors`.

## Phase 5: Embeddings
Outputs: `embeddings`, `embeddings_lag`.

22. CALL `load` with the path `reference/embeddings.md`. Its sections "Dependency Detection" and "Embedding Lag" are used here.
23. CALL `shell__run` with the command `test -d {{settings.CORPUS_PATH}}/index-embeddings.lance && echo present || echo absent`. If it printed `absent`, set `embeddings` to `skipped` and `embeddings_lag` to null, and go to step 28.
24. If `added` and `modified` of `index_changes` are both 0, set `embeddings` to `skipped` and go to step 27.
25. If `stale_entries` of `index_changes` is not empty, set `embeddings` to `deferred` and embed nothing: stale entries have placeholder or outdated summaries, and embedding them would poison the semantic search. The `enrich` node embeds again after it has written the summaries. Go to step 27.
26. CALL `shell__run` with the command `uv run scripts/detect.py`.
    - It prints `ready`: CALL `shell__run` with `uv run scripts/embed.py {{settings.CORPUS_PATH}}/index.yaml {{settings.CORPUS_PATH}}/index-embeddings.lance/`. If it exits with success, set `embeddings` to `updated`; otherwise set it to `skipped` and add `embedding failed: <error>` to `errors`.
    - It prints `no-model`: set `embeddings` to `no-model`. Never download the model during a refresh.
    - It prints `not-installed`: set `embeddings` to `not-installed`.
27. Work out the lag, as the document's "Embedding Lag" section says. CALL `shell__run` with the command `uv run scripts/lance_meta.py {{settings.CORPUS_PATH}}/index-embeddings.lance/`.
    - It exits with 2: there is no `_meta` table, and `embeddings_lag` is null.
    - It exits with another error: `embeddings_lag` is null and `embedding lag not computed: <error>` is added to `errors`.
    - Otherwise take `generated_at` from the JSON it printed and CALL `shell__run` with the command `EMB_AT=<generated_at> yq '[.entries[] | select(.last_indexed > env(EMB_AT))] | length' {{settings.CORPUS_PATH}}/index.yaml`, `<generated_at>` written out. The number it prints is `embeddings_lag`.
28. EXIT `done` with outputs `sources` (the records of the sources, in the order of `config.yaml`, with `error` only on a source that failed or was skipped), `index_changes`, `embeddings`, `embeddings_lag` and `errors`.

## Errors

| Error | Behaviour |
|-------|-----------|
| `error:` on `config.yaml` (step 2) | EXIT `failed` with output `reason` set to the error. |
| `error:` on `load` of a source document (step 6) | The source is `skipped-manual`, as step 6 says. |
| A clone, fetch, checkout or diff fails (steps 9 to 14) | That source is `failed` with the error; its entries stay as they were; the other sources go on. |
| A deepen (step 12) leaves the commit unresolved | The source is `failed`; the other sources go on. |
| An edit of the index fails (step 18, 19) | Add `index update failed: <error>` to `errors`; the changes saved stay. |
| An edit of `config.yaml` fails (step 20) | Add `config save failed: <error>` to `errors`. |
