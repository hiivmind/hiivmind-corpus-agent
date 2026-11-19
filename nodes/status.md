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
        freshness: {enum: [current, behind, unknown]}
  index_format: {enum: [v2, v1, none]}
  stale_count: {type: integer}
  embeddings_lag: {type: [integer, "null"]}
  refresh_needed: {type: boolean}
  status_errors: {type: array, items: {type: string}}
exits: [current, stale, failed]
allowed-tools: [corpus_status]
context: none
---
# Status

Reports whether the corpus needs a refresh. `corpus_status` finds every figure and records it in this node's outputs itself: never give the outputs on EXIT, except `status_errors` after an error.

Corpus: {{settings.CORPUS_PATH}}.

## Steps

1. CALL `corpus_status`. If it returns an error, EXIT `failed` with output `status_errors` set to a list holding that error.
2. If its `refresh_needed` is `true`, EXIT `stale`; otherwise EXIT `current`. Give no outputs: the call recorded them.
