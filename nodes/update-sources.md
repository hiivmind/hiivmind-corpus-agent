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
  excluded_paths: {type: array, items: {type: string}}
  update_errors: {type: array, items: {type: string}}
exits: [updated, current, declined, failed]
allowed-tools: [shell__run, files__read_text_file, source_freshness, apply_source_update, drop_missing]
preconditions:
  - {tool: index_is_v2, message: "The corpus has a v1 index: run the migrate sequence."}
  - {tool: corpus_ready, message: "The corpus has no config.yaml, no source, or no built v2 index."}
  - {tool: begin_update, message: "The totals could not be started."}
context: none
---
# Update sources

Brings the index of one corpus up to date with its sources. It finds the sources that are behind, updates their working copies, writes what git says changed in each, and has `apply_source_update` mark the index entries of changed files stale, add an entry for each new file, remove the entry of each deleted file, and record the commit each source is now at. It does not read the changed files: the `scan` node writes the metadata of the stale entries afterwards. The sources are worked one after another.

Corpus: {{settings.CORPUS_PATH}}.
Sources to update: {{input.sources}}.

Keep a list `update_errors`, empty to begin with, and one record for each source looked at: `id`, `type`, `status`, `old_sha`, `new_sha`, `files_changed` and, for a source that failed or was skipped, `error`. A sha in a record is the first seven characters of the commit; `<old_sha>` and `<new_sha>` in a command below are full shas, 40 characters. The tools keep the totals (`index_changes`, `removed_ids` and `excluded_paths`) themselves: the harness zeroed them before this node started, and you do not keep or give them.

A shell command's result has an exit code. A command went well when its exit code is 0; "the command fails" below means its exit code is not 0.

## Phase 1: Validate
Outputs: the sources to work on.

1. If "Sources to update" reads "not given", ASK "Which sources should I update?". When the person answers, STATE.set `sources` to the answer. If the answer says that no source is to be updated, EXIT `declined` with output `reason` saying so.
2. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/config.yaml`. If it returns an error, EXIT `failed` with output `reason` set to the error.
3. If `config.yaml` has no `sources` or the list is empty, EXIT `failed` with output `reason` set to "config.yaml has no sources".
4. Choose the sources to work on, from the sources of `config.yaml`. When "Sources to update" is `all` (or the answer to step 1 is), take every source. Otherwise take the ids it names, which are separated by commas or spaces. An id that is not a source of `config.yaml` is left out and `unknown source: <id>` is added to `update_errors`. If no source is left, EXIT `failed` with output `reason` set to "none of the sources named is in config.yaml".

## Phase 2: Check freshness
Outputs: the status of each source, and which sources are behind.

5. Look at the upstream of each chosen git source.
{{include includes/sources/upstream-head.md}}
6. CALL `source_freshness` with `observed`. It returns one item for each source of `config.yaml`: `id`, `type`, `freshness` (`current`, `behind` or `unknown`) and `error`. Use the items of the sources chosen in step 4 only, in the order of `config.yaml`.
7. For each chosen source whose `type` is not `git`: this instance does not handle that kind of source. Its record is `status: skipped-manual`, `old_sha` and `new_sha` null, `files_changed` 0, and `error` set to "source type `<type>` is not handled by this instance yet". Leave it alone in every later step.
8. For each chosen git source:
   - Its `freshness` is `unknown`: its record is `status: failed` with `error` set to the item's `error`, `old_sha` the first seven characters of `last_commit_sha`, `new_sha` null, `files_changed` 0. Add `<id>: <error>` to `update_errors`.
   - Its `freshness` is `current`: its record is `status: current`, `old_sha` and `new_sha` both the first seven characters of `last_commit_sha`, `files_changed` 0.
   - Its `freshness` is `behind`: it is to be updated, and its `old_sha` is the first seven characters of `last_commit_sha`.

## Phase 3: Update sources
Outputs: the new commit of each source that is behind.

Update each source that is behind, one after the other. A source that fails does not stop the others: its record is `status: failed` with `error` set to what went wrong, its `new_sha` null and `files_changed` 0, `<id>: <error>` is added to `update_errors`, its entries are left as they were, and you go to step 12.

The working copy of a source is `<clone>` = `{{settings.CORPUS_PATH}}/.source/<id>`, where `<id>` is the source's `id`.

9. If no source is behind, there is nothing to apply: go to step 14.
10. Take the first source that is behind, in the order of `config.yaml`, that has not been checked out or failed yet.
11. Update its working copy and check out the head of its branch: `<commit>` is `FETCH_HEAD`, what step c fetches. When the steps below end with the source checked out, the commit `rev-parse` printed (in full) is the source's new commit, `<new_sha>`; its record's `new_sha` is its first seven characters.
{{include includes/sources/git.md}}
12. If a source that is behind has not been checked out or failed yet, go to step 10.

## Phase 4: Apply changes to the index
Outputs: `index_changes`, `removed_ids`.

13. For each source that is checked out, in order of `config.yaml`, do a and b. `<old_sha>` is the source's `last_commit_sha` in full, as `config.yaml` writes it; `<new_sha>` is the commit of step 11, in full. Write the file next to the clone, as the path says.
    a. CALL `shell__run` with the command `git -C <clone> diff --name-status -z --no-renames <old_sha>..<new_sha> -- ':(literal)<docs_root>' > <clone>.changes`, `<docs_root>` being the source's `docs_root` and the path written out. When the source's `docs_root` is `.` or it has none, leave out ` -- ':(literal)<docs_root>'`. (`:(literal)` keeps a `docs_root` such as `src/app/[locale]` from being read as a glob.) If the command fails, the source fails.
    b. CALL `apply_source_update` with `source` its `id`, `new_sha` its `<new_sha>` and `changes_file` the path `<clone>.changes`. It applies the changes to `index.yaml` and `graph.yaml`, records the new commit in `config.yaml`, adds to the totals and returns `files_changed`, `added`, `modified`, `removed`, `removed_ids`, `stale_entries`, `excluded` and `outside_docs_root`.
       - It returns an error: the source fails with that error, as Phase 3 says; its entries stay as they were.
       - Otherwise its record is `status: updated` with `files_changed` from the result.

## Phase 5: Drop the entries whose files are gone
Outputs: the entries removed that the diff could not show.

14. For each source whose status is `updated` or `current`, in the order of `config.yaml`, do a to c.
    a. CALL `shell__run` with the command `git -C <clone> rev-parse HEAD`. If it fails, or the source has no clone, leave the source alone: go on to the next. Otherwise the commit it printed is `<head>`, in full.
    b. CALL `shell__run` with the command `git -C <clone> ls-tree -r -z --name-only HEAD -- ':(literal)<docs_root>' > <clone>.listing`, as in step 13, a: no pathspec when `docs_root` is `.` or none. If it fails, leave the source alone.
    c. CALL `drop_missing` with `source` its `id`, `head` its `<head>` and `listing_file` the path `<clone>.listing`. It removes the entries whose files git says are gone from the source, and adds their ids to the totals. If it returns an error, add `drop_missing failed: <error>` to `update_errors`.
15. If a source has the status `updated`, EXIT `updated`; otherwise EXIT `current`. EXIT with `sources` and `update_errors` only: `sources` holds the records of the sources, in the order of `config.yaml`, with `error` only on a source that failed or was skipped. `index_changes`, `removed_ids` and `excluded_paths` are recorded by the tools; do not give them.

## Errors

| Error | Behaviour |
|-------|-----------|
| `error:` on `config.yaml` (step 2) | EXIT `failed` with output `reason` set to the error. |
| A source that is not `git` (step 7) | The source is `skipped-manual`, as step 7 says. |
| A source whose freshness is unknown (step 8) | The source is `failed` with its error; the other sources go on. |
| A clone, fetch or checkout command fails (step 11) | That source is `failed` with the error; its entries stay as they were; the other sources go on. |
| A deepen leaves the commit unresolved (step 11, d) | The source is `failed`; the other sources go on. |
| The diff command fails, or `apply_source_update` returns an error (step 13) | That source is `failed` with the error; its entries stay as they were. |
| `rev-parse` or `ls-tree` fails (step 14) | The source is left alone. |
| `drop_missing` returns an error (step 14) | Add `drop_missing failed: <error>` to `update_errors`. |
