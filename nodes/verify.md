---
name: verify
description: Check a sample of the summaries of the entries just re-scanned against their files, and replace a summary that does not describe its file, through set_summary.
inputs:
  enriched_ids: the ids of the entries just re-scanned
outputs:
  verification:
    type: object
    required: [sampled, failed, drift_entries]
    properties:
      sampled: {type: integer}
      failed: {type: integer}
      drift_entries: {type: array, items: {type: string}}
  verify_errors: {type: array, items: {type: string}}
exits: [done, failed]
allowed-tools: [verify_previews, set_summary]
context: none
---
# Verify

Checks a sample of the summaries the `scan` runs have just written against a preview of each file, and writes a new summary for each that does not describe its file. The summaries are written by `set_summary`; never edit `index.yaml`.

Corpus: {{settings.CORPUS_PATH}}.
Entries: {{input.enriched_ids}}.

Keep a list `verify_errors`, empty to begin with, and `verification` with `sampled` 0, `failed` 0 and `drift_entries` empty.

## Steps

1. If "Entries" reads "not given" or names no id, EXIT `done` with outputs `verification` and `verify_errors`.
2. Take the first ten target entries, the ids in "Entries" in their order, or all of them when there are fewer: the sample.
3. CALL `verify_previews` with `entry_ids` set to the ids of the sample. If it returns an error, verification is best-effort: add `verification not run: <error>` to `verify_errors` and EXIT `done` with outputs `verification` and `verify_errors`.
4. It returned a list with one item for each entry: `entry_id`, `title`, `summary`, `source_path` and `content_preview`. An item whose `content_preview` is null cannot be judged: add `<entry_id>: no content preview` to `verify_errors` and leave it out. Set `sampled` to the number of items left.
5. Repeat for each item left, one after another: judge whether its `summary` accurately describes its `content_preview`. If it does, go on to the next item. If it does not, write a new summary from the preview alone and CALL `set_summary` with `entry_id` the item's `entry_id` and `summary` the new summary. Add one to `failed`. If the call succeeds, add the entry's id to `drift_entries`; if it returns an error, add `index update failed: <error>` to `verify_errors`.
6. EXIT `done` with outputs `verification` and `verify_errors`.

## Errors

| Error | Behaviour |
|-------|-----------|
| `verify_previews` returns an error (step 3) | Add `verification not run: <error>` to `verify_errors`; verification is best-effort. |
| `set_summary` returns an error (step 5) | Add `index update failed: <error>` to `verify_errors` and go on. |
