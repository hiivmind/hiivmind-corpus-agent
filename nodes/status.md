---
name: status
description: Report the status of the corpus named in the settings - each source's freshness, the index format, the stale entries and the embeddings' lag - and whether it needs a refresh. Reads the corpus; fetches nothing and changes nothing.
outputs:
  sources:
    type: array
    items:
      type: object
      required: [id, type, freshness]
      properties:
        freshness: {enum: [current, behind, unknown, manual]}
  index_format: {enum: [v2, v1, none]}
  stale_count: {type: [integer, "null"]}
  embeddings_lag: {type: [integer, "null"]}
  refresh_needed: {type: boolean}
  status_errors: {type: array, items: {type: string}}
exits: [current, stale, failed]
allowed-tools: [shell__run, files__read_text_file, corpus_status]
context: none
---
# Status

Reports whether the corpus needs a refresh. `corpus_status` finds every figure and records it in this node's outputs itself: never give the outputs on EXIT, except `status_errors` after an error.

Corpus: {{settings.CORPUS_PATH}}.

A shell command's result has an exit code. A command went well when its exit code is 0.

## Steps

1. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/config.yaml`. If it returns an error, EXIT `failed` with output `status_errors` set to a list holding that error.
2. Look at the upstream of each source.
{{include includes/sources/upstream-head.md}}
3. CALL `corpus_status` with `observed`. If it returns an error, EXIT `failed` with output `status_errors` set to a list holding that error.
4. If its `refresh_needed` is `true`, EXIT `stale`; otherwise EXIT `current`. Give no outputs: the call recorded them.
