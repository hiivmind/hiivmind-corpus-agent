# Embedding Patterns

An optional semantic layer: entry-level embeddings of each entry's title, summary, tags and concepts, made with fastembed (`BAAI/bge-small-en-v1.5`, 384 dimensions) and stored in Lance format.

## Dependencies

- `fastembed`: ONNX-based embedding library
- `lancedb`: Lance vector database (flat files, no server)
- `pyarrow`: columnar data (comes with lancedb)
- Model: `BAAI/bge-small-en-v1.5` (about 45MB). It is never downloaded by a refresh: it has to be in the fastembed cache already.

## Dependency Detection

`embeddings_status` returns one of four words:

| Word | Meaning |
|------|---------|
| `absent` | The corpus has no `index-embeddings.lance/` |
| `not-installed` | `fastembed`, `lancedb` or `pyarrow` is not available |
| `no-model` | Installed, but the model is not in the fastembed cache |
| `ready` | Installed and the model is cached: `embed` can run |

## Data Model

Each Lance dataset has a table `embeddings`:

| Column | Type | Description |
|---|---|---|
| `id` | string | Entry ID (e.g. `polars:user-guide/expressions.md`) |
| `source` | string | The entry's `source` |
| `title` | string | Entry title |
| `tags` | list[string] | Entry tags |
| `concepts` | list[string] | The entry's `concepts` |
| `metadata_text` | string | The text that was embedded |
| `vector` | vector[384] | Dense embedding |
| `updated_at` | string | ISO-8601 timestamp when the embedding was made |
| `text_hash` | string | SHA-256 of the embedded text with its `passage: ` prefix; decides whether the entry is embedded again |

A `_meta` table in the same database holds key-value pairs: `model`, `dimensions`, `generated_at` (an ISO-8601 timestamp) and `entry_count`.

## Embedding Strategy

The text of an entry is embedded with the prefix `passage: `, as bge-small is trained to tell document text from query text:

`passage: {title} | {summary} | {tags joined by ", "} | {concepts joined by ", "}`

Concept IDs are part of the text, so an entry assigned to a concept is found by the concept's name even when the words are not in its title or summary.

## Embedding Generation

### Per-corpus: index-embeddings.lance/

`embed` embeds the entries of `index.yaml` into `index-embeddings.lance/`, in the corpus root. The directory is committed to the repository: it is a distributable artifact, not a cache. Do not add it to `.gitignore`.

### Incremental updates

`embed` embeds again only the entries whose `text_hash` changed, adds new entries, and deletes the rows of entries no longer in the index. A table made before `text_hash` existed is rebuilt once.

## Staleness Detection

The embeddings are out of date when `index.yaml` has entries indexed after `_meta.generated_at`. Stale embeddings are still usable (stale is better than none); say so.

## Embedding Lag

`embeddings_lag` is the number of entries of `index.yaml` whose `last_indexed` is later than `_meta.generated_at`: a comparison of the two datetimes. An entry with no `last_indexed` is not counted. It measures the drift that builds up across runs, which a per-run status (`updated`, `skipped`, `no-model`, `deferred`) cannot see. It is null when there is no embeddings table or it has no `generated_at`. A lag above 0 with no stale entries means the embeddings should be made again.

## Graceful Degradation

| Condition | Behavior |
|---|---|
| No `index-embeddings.lance/` | Nothing is embedded; no change |
| `fastembed`, `lancedb` or `pyarrow` not installed | Nothing is embedded; the lag cannot be computed |
| No model in the cache | Nothing is embedded and nothing is downloaded |
| Stale embeddings | Use them and say so |
