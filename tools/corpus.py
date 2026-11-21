"""The instance's tools: each a thin call of the corpus package's `Corpus`, opened on the corpus of the settings (`CORPUS_PATH`).

The harness fills `settings` and `state`; the model sees only the other arguments (TOOL-12). A `CorpusError` propagates to the
harness, which shows the model its class and message; only `embed` catches it. Tools stamp with the package's clock, and write
no rendering of their own: each package write renders itself.
"""

import dataclasses
from pathlib import Path

from hiivmind_corpus_lib import Corpus, CorpusError, Head, Listing, Unobserved, parse_name_status

NODE_KINDS = {"git"}   # the source types the nodes of this instance observe and diff


def _open(settings) -> Corpus:
    """The corpus of the settings, with an absolute path."""
    return Corpus.open(Path(settings.CORPUS_PATH).resolve())


def _observations(observed: list[dict]) -> dict:
    """`{"id", "head"}` is a `Head`; `{"id", "error"}` an `Unobserved`."""
    return {o["id"]: Head(o["head"]) if "head" in o else Unobserved(o.get("error") or "unobserved") for o in observed}


def _recorded(state, result: dict) -> dict:
    """Write each value of `result` to the node's state, so the node's outputs are what the tool found (P17); `result`."""
    state.update(result)
    return result


def _docs_root(corpus: Corpus, source_id: str) -> str | None:
    source = next((s for s in corpus.config.load().sources if s.id == source_id), None)
    return getattr(source, "docs_root", None)


def corpus_ready(settings) -> bool:
    """True when config.yaml has a source, index.yaml exists and index.md is not the build's placeholder."""
    return _open(settings).ready()


def index_is_v2(settings) -> bool:
    """True when the corpus has index.yaml."""
    return _open(settings).status.index_format() == "v2"


def index_is_v1(settings) -> bool:
    """True when the corpus has no index.yaml and has an index.md."""
    return _open(settings).status.index_format() == "v1"


def graph_exists(settings) -> bool:
    """True when the corpus has graph.yaml."""
    return _open(settings).graph.exists()


def sources_handled(settings) -> bool:
    """True when each source of config.yaml is of a kind this instance handles (git)."""
    return all(s.type in NODE_KINDS for s in _open(settings).config.load().sources)


def source_freshness(observed: list[dict], settings) -> list[dict]:
    """Each source of config.yaml, in its order: id, type, freshness (`current`, `behind` or `unknown`) and error (or null).
    `observed` is what git said of each source's upstream: `{"id", "head"}` for a head, `{"id", "error"}` for a failed look.
    Changes nothing."""
    found = _open(settings).sources.freshness(_observations(observed))
    return [{"id": s.id, "type": s.type, "freshness": str(s.freshness), "error": s.error} for s in found]


def corpus_status(observed: list[dict], settings, state) -> dict:
    """The corpus's status: sources (id, type, freshness), index_format, stale_count, embeddings_lag, refresh_needed (a source
    behind or unknown, a stale entry, or embeddings that lag) and status_errors. `observed` is what git said of each source's
    upstream: `{"id", "head"}` or `{"id", "error"}`. Records each in the node's outputs. Changes nothing."""
    report = _open(settings).status.report(_observations(observed))
    return _recorded(state, {
        "sources": [{"id": s.id, "type": s.type, "freshness": str(s.freshness)} for s in report.sources],
        "index_format": str(report.index_format),
        "stale_count": report.stale_entries,
        "embeddings_lag": report.embeddings_lag,
        "refresh_needed": report.refresh_needed,
        "status_errors": list(report.errors),
    })


def stale_batches(settings) -> list[dict]:
    """The stale files to scan, in batches of at most 30 files of one source: `[{"source", "files"}]`."""
    return [{"source": b.source, "files": list(b.files)} for b in _open(settings).index.stale_batches()]


def stale_entries(settings) -> list[str]:
    """The ids of the entries still marked stale."""
    return list(_open(settings).index.stale_ids())


def locate_files(source: str, files: list[str], settings) -> list[dict]:
    """For each path of the source's documents: `{"path", "file", "url"}`, the file in the checkout to read or the url to fetch;
    both null when the index has no entry for the path."""
    corpus = _open(settings)
    index = corpus.index.load()
    out = []
    for path in files:
        entry = index.find(source, path)
        where = corpus.sources.locate(entry) if entry is not None else None
        out.append({"path": path, "file": str(where.file) if where and where.file else None, "url": where.url if where else None})
    return out


def begin_update(state) -> bool:
    """Zero the totals of an update (index_changes, removed_ids, excluded_paths). Run by the harness before the update, never
    offered to a model."""
    _recorded(state, {
        "index_changes": {"added": 0, "modified": 0, "removed": 0, "stale_entries": []},
        "removed_ids": [], "excluded_paths": [],
    })
    return True


def apply_source_update(source: str, new_sha: str, changes_file: str, settings, state) -> dict:
    """Apply the changes of `git diff --name-status -z` (the NUL-separated file `changes_file`) to the index: M stale, A added
    stale, D removed (from index.yaml and graph.yaml); then record new_sha in config.yaml. Adds to the run's totals. Returns
    files_changed, added, modified, removed, removed_ids, stale_entries, excluded and outside_docs_root."""
    corpus = _open(settings)
    changes = parse_name_status(Path(changes_file).read_text(encoding="utf-8"), _docs_root(corpus, source))
    result = corpus.sources.apply_update(source, changes, Head(new_sha))
    totals = state["index_changes"]
    _recorded(state, {
        "index_changes": {
            "added": totals["added"] + result.added, "modified": totals["modified"] + result.modified,
            "removed": totals["removed"] + result.removed, "stale_entries": [*totals["stale_entries"], *result.stale_entries],
        },
        "removed_ids": [*state["removed_ids"], *result.removed_ids],
        "excluded_paths": [*state["excluded_paths"], *result.excluded],
    })
    return {
        "files_changed": result.files_changed, "added": result.added, "modified": result.modified, "removed": result.removed,
        "removed_ids": list(result.removed_ids), "stale_entries": list(result.stale_entries),
        "excluded": list(result.excluded), "outside_docs_root": result.outside_docs_root,
    }


def drop_missing(source: str, head: str, listing_file: str, settings, state) -> dict:
    """Remove the entries of the source whose files its checkout at `head` no longer lists. `listing_file` holds the
    NUL-separated paths of `git ls-tree -r -z --name-only`. Adds the ids to removed_ids. Returns removed_ids, skipped (null,
    `empty-listing` or `head-mismatch`) and outside_docs_root."""
    corpus = _open(settings)
    paths = [p for p in Path(listing_file).read_text(encoding="utf-8").split("\0") if p]
    result = corpus.sources.drop_missing(source, Listing.of(head, paths, _docs_root(corpus, source)))
    _recorded(state, {"removed_ids": [*state["removed_ids"], *result.removed_ids]})
    return {"removed_ids": list(result.removed_ids), "skipped": result.skipped, "outside_docs_root": result.outside_docs_root}


def merge_scans(settings, state) -> dict:
    """Merge the scans of this run into index.yaml. Takes no argument: the scans are the run's facts. Returns enriched
    (entry ids) and skipped (id and reason)."""
    result = _open(settings).index.merge_scans(state.get("scans") or [], state.get("scans_failures") or [])
    return {"enriched": list(result.enriched), "skipped": [{"id": s.id, "reason": s.reason} for s in result.skipped]}


def set_concepts(assignments: dict[str, list[str]], settings) -> dict:
    """Set the concepts of entries: `{entry id: [concept ids]}`. Returns `{"assigned": <entries changed>}`."""
    return {"assigned": len(_open(settings).index.set_concepts(assignments).assigned)}


def set_summary(entry_id: str, summary: str, settings) -> dict:
    """Replace the summary of one entry. Returns `{"ok": true}`; an unknown id is an error."""
    _open(settings).index.set_summary(entry_id, summary)
    return {"ok": True}


def verify_previews(entry_ids: list[str], settings) -> list[dict]:
    """A content preview of each entry, to check its summary against: entry_id, title, summary, source_path, content_preview
    (null when the file cannot be read) and estimated_tokens."""
    return [dataclasses.asdict(p) for p in _open(settings).previews.of(entry_ids)]


def embeddings_status(settings) -> str:
    """`absent` when the corpus has no embeddings; else `ready`, `no-model` or `not-installed`."""
    return str(_open(settings).embeddings.status())


def embeddings_lag(settings) -> int | None:
    """How many entries were indexed after the embeddings were made; null without an embeddings table."""
    return _open(settings).embeddings.lag()


def embed(settings) -> dict:
    """Embed index.yaml into index-embeddings.lance/ again (only changed entries). Never downloads a model. Returns ok and error."""
    try:
        _open(settings).embeddings.embed()
    except CorpusError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "error": None}


def migrate_index(settings, state) -> dict:
    """Migrate the v1 index (index.md, index-*.md) to index.yaml, every entry stale, and render it. Records migrated,
    migrate_skipped, strategy and sections in the node's outputs. A refusal is an error that says why."""
    result = _open(settings).migration.migrate()
    return _recorded(state, {
        "migrated": result.migrated, "migrate_skipped": [{"id": s.id, "reason": s.reason} for s in result.skipped],
        "strategy": result.strategy, "sections": list(result.sections),
    })


def validate_graph(settings, state) -> dict:
    """Check graph.yaml against the graph rules. Records concepts, relationships, issues (severity, rule, detail) and valid
    (no issue is an error) in the node's outputs."""
    report = _open(settings).graph.validate()
    return _recorded(state, {
        "concepts": report.concepts, "relationships": report.relationships,
        "issues": [dataclasses.asdict(i) for i in report.issues], "valid": report.valid,
    })
