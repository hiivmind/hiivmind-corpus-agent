# SHA-Gated Freshness and Stale Flagging

## Purpose

Detect whether a corpus index is current with its upstream sources, and flag the entries a change makes stale.

## The Write-Time Check

A refresh compares each source's `last_commit_sha` in `config.yaml` with the head of its upstream. When they match there is nothing to do. When they differ, the files changed between the two commits are applied to `index.yaml` without any model work:

- **Added file**: a placeholder entry with its `path`, `stale: true`, `stale_since` now, `category: unknown`, `summary: "Pending re-scan"`, empty `tags`, `keywords` and `concepts`, and its `section` when sources are rendered by section. The rest of its metadata (title, content type, size and so on) comes from the scan that is merged.
- **Modified file**: `stale: true` and `stale_since` now on the existing entry. Its summary, tags and keywords stay (they may be outdated, which is better than nothing).
- **Deleted file**: the entry is removed from `index.yaml` and from the `concepts` of `graph.yaml` that name it.

Then `config.yaml` records the new `last_commit_sha`, and `index.yaml` records `meta.generated_at` and `meta.entry_count`. A stale entry stays stale until a scan of its file is merged.

## Embedding Freshness

The embeddings lag the index when entries were indexed after the embeddings were generated; see the embeddings document.
