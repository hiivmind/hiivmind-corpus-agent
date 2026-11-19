---
name: index
description: Merge the scans of this run into index.yaml through merge_scans, and render index.md. Reads no file and edits none by text.
inputs:
  scans: the outputs of the scan runs that ended done, in the order of their batches (a fact; the tool reads it)
  scans_failures: the scan runs that did not end done, with their batch and reason (a fact; the tool reads it)
outputs:
  enriched_ids: {type: array, items: {type: string}}
  skipped_entries:
    type: array
    items:
      type: object
      required: [id, reason]
      properties:
        id: {type: string}
        reason: {type: string}
  index_errors: {type: array, items: {type: string}}
exits: [done, failed]
allowed-tools: [merge_scans, shell__run]
context: none
---
# Index

Merges the metadata the `scan` runs wrote into `index.yaml`. The merge is `merge_scans`, which reads the scans of this run itself: never pass it the scans, and never edit `index.yaml`. An entry whose batch failed, or whose file a scan did not return, is skipped with the reason and stays stale.

Corpus: {{settings.CORPUS_PATH}}.

Keep a list `index_errors`, empty to begin with.

## Steps

1. CALL `merge_scans`, with no arguments. It returns `enriched` (the ids of the entries it updated) and `skipped` (each with `id` and `reason`). If it returns an error, EXIT `failed` with outputs `reason` set to the error and `index_errors` set to `merge_scans failed: <error>`, so that `publish` reports it.
2. If `enriched` is not empty, render the index; the node's error list is `index_errors`. {{include fragments/render-index.md}}
3. EXIT `done` with outputs `enriched_ids` set to `enriched`, `skipped_entries` set to `skipped`, and `index_errors`.

## Errors

| Error | Behaviour |
|-------|-----------|
| `merge_scans` returns an error (step 1) | EXIT `failed` with the error in `reason` and in `index_errors`. |
| `render-index.sh` exits with a code that is not 0 (step 2) | Add `index.md not rendered: <error>` to `index_errors`. |
