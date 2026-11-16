---
name: update-sources
description: Update the sources of the corpus named in the settings, mark the index entries of changed files stale, add and remove entries, record the new commits and report what changed. Handles git sources only.
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
  removed_ids: {type: array, items: {type: string}}
  update_errors: {type: array, items: {type: string}}
exits: [updated, current, declined, failed]
allowed-tools: [shell__run, files__read_text_file, source_freshness, apply_source_update, drop_missing, reference]
context: none
---
# Update sources

Brings the index of one corpus up to date with its sources. It finds the sources that are behind, updates their working copies, and has `apply_source_update` mark the index entries of changed files stale, add an entry for each new file, remove the entry of each deleted file, and record the commit each source is now at. It does not read the changed files: the `scan` node writes the metadata of the stale entries afterwards. The sources are worked one after another.

Corpus: {{settings.CORPUS_PATH}}.
Sources to update: {{input.sources}}.

Keep a list `update_errors`, empty to begin with; `index_changes` with `added` 0, `modified` 0, `removed` 0 and `stale_entries` empty; a list `removed_ids`, empty to begin with; and one record for each source looked at: `id`, `type`, `status`, `old_sha`, `new_sha`, `files_changed` and, for a source that failed or was skipped, `error`. A sha in a record is the first seven characters of the commit.

A shell command's result has an exit code. A command went well when its exit code is 0; "the command fails" below means its exit code is not 0.

## Phase 1: Validate
Outputs: the sources to work on.

1. If "Sources to update" reads "not given", ASK "Which sources should I update?". When the person answers, STATE.set `sources` to the answer. If the answer says that no source is to be updated, EXIT `declined` with output `reason` saying so.
2. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/config.yaml`. If it returns an error, EXIT `failed` with output `reason` set to the error.
3. If `config.yaml` has no `sources` or the list is empty, EXIT `failed` with output `reason` set to "config.yaml has no sources".
4. CALL `shell__run` with the command `if [ ! -f {{settings.CORPUS_PATH}}/index.yaml ]; then echo v1; elif grep -qs "Run hiivmind-corpus-build" {{settings.CORPUS_PATH}}/index.md; then echo placeholder; else echo built; fi`.
   - It prints `v1`: EXIT `failed` with output `reason` set to "v1-index: read-only, run hiivmind-corpus-migrate".
   - It prints `placeholder`: EXIT `failed` with output `reason` set to "index.md is a placeholder: the index is not built".
5. Choose the sources to work on, from the sources of `config.yaml`. When "Sources to update" is `all` (or the answer to step 1 is), take every source. Otherwise take the ids it names, which are separated by commas or spaces. An id that is not a source of `config.yaml` is left out and `unknown source: <id>` is added to `update_errors`. If no source is left, EXIT `failed` with output `reason` set to "none of the sources named is in config.yaml".

## Phase 2: Check freshness
Outputs: the status of each source, and which sources are behind.

6. CALL `source_freshness`. It returns one item for each source of `config.yaml`: `id`, `type`, `freshness` (`current`, `behind` or `unknown`) and `error`. Use the items of the sources chosen in step 5 only, in the order of `config.yaml`.
7. For each chosen source whose `type` is not `git`: this instance does not handle that kind of source. Its record is `status: skipped-manual`, `old_sha` and `new_sha` null, `files_changed` 0, and `error` set to "source type `<type>` is not handled by this instance yet". Leave it alone in every later step.
8. For each chosen git source:
   - Its `freshness` is `unknown`: its record is `status: failed` with `error` set to the item's `error`, `old_sha` the first seven characters of `last_commit_sha`, `new_sha` null, `files_changed` 0. Add `<id>: <error>` to `update_errors`.
   - Its `freshness` is `current`: its record is `status: current`, `old_sha` and `new_sha` both the first seven characters of `last_commit_sha`, `files_changed` 0.
   - Its `freshness` is `behind`: it is to be updated, and its `old_sha` is the first seven characters of `last_commit_sha`.

## Phase 3: Update sources
Outputs: the new commit of each source that is behind.

Update each source that is behind, one after the other. A source that fails does not stop the others: its record is `status: failed` with `error` set to what went wrong, its `new_sha` null and `files_changed` 0, `<id>: <error>` is added to `update_errors`, its entries are left as they were, and you go to step 17.

The working copy of a source is `<clone>` = `{{settings.CORPUS_PATH}}/.source/<id>`, where `<id>` is the source's `id`. It is a sparse clone, as the "Sparse Checkout for Large Repositories" section of the `sources/git` document says. Never use the GitHub compare API to find the changed files (`gh api repos/<owner>/<repo>/compare/...`): it stops at 300 files and drops the rest without saying so. The changed files are found with a local `git diff` in the clone, which `apply_source_update` runs.

9. If no source is behind, there is nothing to apply: go to step 19.
10. CALL `reference` with `doc` `sources/git` and `section` `Sparse Checkout for Large Repositories`.
11. Take the first source that is behind, in the order of `config.yaml`, that has not been updated or failed yet.
12. CALL `shell__run` with the command `test -d <clone>/.git && echo cloned || echo missing`, the path written out.
13. If it printed `missing`, CALL `shell__run` with the command `mkdir -p {{settings.CORPUS_PATH}}/.source && git clone --filter=blob:none --sparse --depth=50 --branch <branch> <repo_url> <clone>`. Then CALL `shell__run` with `git -C <clone> sparse-checkout set <docs_root>`; when the source's `docs_root` is `.` or none, use `git -C <clone> sparse-checkout disable` instead. If a command fails, the source fails.
14. CALL `shell__run` with the command `git -C <clone> fetch --depth=50 origin <branch>`. If it fails, the source fails.
15. Make sure the commit the index was built at can be resolved, so that it can be diffed. CALL `shell__run` with `git -C <clone> cat-file -e <last_commit_sha>^{commit}`. If it fails:
    1. CALL `shell__run` with `git -C <clone> rev-parse --is-shallow-repository`. If it prints `false`, the commit is not in the history of the branch: the source fails with the error "commit <last_commit_sha> is not in the history of <branch>".
    2. Otherwise deepen the clone: CALL `shell__run` with `git -C <clone> fetch --shallow-since=<last_indexed_at> origin <branch>`, then try `cat-file -e` again.
    3. If it still fails, CALL `shell__run` with `git -C <clone> fetch --unshallow origin <branch>`, then try `cat-file -e` again. If it still fails, the source fails with the error "commit <last_commit_sha> cannot be resolved, even with the full history".
16. CALL `shell__run` with `git -C <clone> checkout -q -B <branch> FETCH_HEAD`, then CALL `shell__run` with `git -C <clone> rev-parse HEAD`. If a command fails, the source fails. The commit it prints is the source's new commit, `<new_sha>`; its record's `new_sha` is its first seven characters.
17. If a source that is behind has not been updated or failed yet, go to step 11.

## Phase 4: Apply changes to the index
Outputs: `index_changes`, `removed_ids`.

18. For each source that is behind and did not fail, in the order of `config.yaml`, CALL `apply_source_update` with `source` its `id`, `old_sha` its `last_commit_sha` in full and `new_sha` its `<new_sha>` of step 16 in full. It applies the diff to `index.yaml` and `graph.yaml`, records the new commit in `config.yaml`, and returns `files_changed`, `added`, `modified`, `removed`, `removed_ids`, `stale_entries` and `excluded`.
    - It returns an error: the source fails with that error, as Phase 3 says; its entries stay as they were.
    - Otherwise its record is `status: updated` with `files_changed` from the result. Add `added`, `modified` and `removed` to those of `index_changes`, its `stale_entries` to `index_changes`'s `stale_entries`, and its `removed_ids` to `removed_ids`. For each path in `excluded`, add `excluded-by-config: <path>` to `update_errors`.
19. CALL `drop_missing` with `sources` set to `{"id": <id>, "status": <status>}` for each source looked at, from its record. It removes the entries whose files git says are gone from the source, and renders `index.md` when any went. Add the ids of its `removed` to `removed_ids`. If it returns an error, add `drop_missing failed: <error>` to `update_errors`.
20. If a source has the status `updated`, render the index; the node's error list is `update_errors`. {{include fragments/render-index.md}}
21. If a source has the status `updated`, EXIT `updated`; otherwise EXIT `current`. The outputs are `sources` (the records of the sources, in the order of `config.yaml`, with `error` only on a source that failed or was skipped), `index_changes`, `removed_ids` and `update_errors`.

## Errors

| Error | Behaviour |
|-------|-----------|
| `error:` on `config.yaml` (step 2) | EXIT `failed` with output `reason` set to the error. |
| A source that is not `git` (step 7) | The source is `skipped-manual`, as step 7 says. |
| A source whose freshness is unknown (step 8) | The source is `failed` with its error; the other sources go on. |
| A clone, fetch or checkout command fails (steps 13 to 16) | That source is `failed` with the error; its entries stay as they were; the other sources go on. |
| A deepen leaves the commit unresolved (step 15) | The source is `failed`; the other sources go on. |
| `apply_source_update` returns an error (step 18) | That source is `failed` with the error; its entries stay as they were. |
| `drop_missing` returns an error (step 19) | Add `drop_missing failed: <error>` to `update_errors`. |
