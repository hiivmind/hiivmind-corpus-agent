---
name: embed
description: Bring the corpus's embeddings up to date with the index, unless entries are still stale; never download a model. Reports the embedding lag.
inputs: {}
outputs:
  embeddings: {enum: [updated, skipped, no-model, not-installed, deferred]}
  embeddings_lag: {type: [integer, "null"]}
  embed_errors: {type: array, items: {type: string}}
exits: [done, deferred, failed]
allowed-tools: [embeddings_status, stale_entries, embed, embeddings_lag]
context: none
---
# Embed

Brings `index-embeddings.lance/` up to date with `index.yaml`, which embeds again only the entries whose text changed. It embeds nothing while entries are stale: stale entries have placeholder or outdated summaries, and embedding them would poison the semantic search. It never downloads a model.

Corpus: {{settings.CORPUS_PATH}}.

Keep a list `embed_errors`, empty to begin with. The outcome is `done` unless step 3 defers.

## Steps

1. Read the reference at the end of this node.
2. CALL `embeddings_status`, which returns one of the four words of "Dependency Detection". If it returns `absent`, the corpus has no embeddings: set `embeddings` to `skipped` and go to step 5.
3. CALL `stale_entries`. If the list it returns is not empty, set `embeddings` to `deferred`, embed nothing, and go to step 5; the outcome is `deferred`.
4. What `embeddings_status` returned in step 2:
   - `ready`: CALL `embed`. If it returns `ok` true, set `embeddings` to `updated`; otherwise set it to `skipped` and add `embedding failed: <error>` to `embed_errors`, `<error>` being the `error` it returned.
   - `no-model`: set `embeddings` to `no-model`. Never download the model here.
   - `not-installed`: set `embeddings` to `not-installed`.
5. CALL `embeddings_lag`. It returns a number, which is `embeddings_lag`, or null when there is no embeddings table. If it returns an error, `embeddings_lag` is null and `embedding lag not computed: <error>` is added to `embed_errors`.
6. EXIT with the outcome (`deferred` when step 3 deferred, otherwise `done`) and outputs `embeddings`, `embeddings_lag` and `embed_errors`.

## Errors

| Error | Behaviour |
|-------|-----------|
| `embed` fails (step 4) | `embeddings` is `skipped`; add `embedding failed: <error>` to `embed_errors`. |
| `embeddings_lag` returns an error (step 5) | `embeddings_lag` is null; add `embedding lag not computed: <error>` to `embed_errors`. |

## Reference

{{include includes/embeddings.md}}
