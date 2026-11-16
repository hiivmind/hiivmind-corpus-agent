"""The instance's tools: each a thin client of the corpus package, passing the corpus of the settings (`CORPUS_PATH`).

The harness fills `settings` and `state`; the model sees only the other arguments (TOOL-12). A tool that writes passes the
time now, in UTC.
"""

from datetime import datetime, timezone
from pathlib import Path

from hiivmind_corpus import index, refresh, repo
from hiivmind_corpus import reference as documents


def _corpus(settings) -> Path:
    """The corpus directory, absolute: the package runs its scripts in its own directory."""
    return Path(settings.CORPUS_PATH).resolve()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def prepare_base(settings) -> bool:
    """Check out the base branch, fetch origin and fast-forward. True; a dirty tree, a failed fetch or fast-forward, or a
    base branch with commits origin lacks raises, naming what it found."""
    return repo.prepare_base(_corpus(settings), settings.BASE_BRANCH)


def corpus_ready(settings) -> bool:
    """True when config.yaml has a source, index.yaml exists and index.md is not the build's placeholder."""
    return refresh.corpus_ready(_corpus(settings))


def refresh_needed(settings) -> bool:
    """False only when every source is current, no entry is stale and the embeddings do not lag."""
    return refresh.refresh_needed(_corpus(settings))


def source_freshness(settings) -> list[dict]:
    """Each source of config.yaml, in its order: id, type, freshness (`current`, `behind` or `unknown`) and error (or null).
    Clones nothing and changes nothing."""
    return refresh.source_freshness(_corpus(settings))


def stale_batches(settings) -> list[dict]:
    """The stale files to scan, in batches of at most 30 files of one source: `[{"source", "files"}]`."""
    return refresh.stale_batches(_corpus(settings))


def apply_source_update(source: str, old_sha: str, new_sha: str, settings) -> dict:
    """Apply the diff old_sha..new_sha of the source's clone to the index: M stale, A added stale, D removed (from index.yaml
    and graph.yaml); then record new_sha in config.yaml and set meta. Returns added, modified, removed (counts), removed_ids
    and excluded (added paths the build skips). Give the full commits."""
    return refresh.apply_source_update(_corpus(settings), source, old_sha, new_sha, _now())


def drop_missing(sources: list[dict], settings) -> dict:
    """Remove the entries whose files git says are gone from their source's checkout, for each source given as
    `{"id", "status"}` with status `updated` or `current`; renders index.md when any went. Returns `{"removed": [ids]}`."""
    return index.drop_missing(sources, _corpus(settings))


def merge_scans(settings, state) -> dict:
    """Merge the scans of this run into index.yaml. Takes no argument: the scans are the run's facts. Returns enriched
    (entry ids) and skipped (id and reason)."""
    return refresh.merge_scans(_corpus(settings), state.get("scans") or [], state.get("scans_failures") or [], _now())


def set_concepts(assignments: dict[str, list[str]], settings) -> dict:
    """Set the concepts of entries: `{entry id: [concept ids]}`. Returns `{"assigned": <entries changed>}`."""
    return refresh.set_concepts(_corpus(settings), assignments, _now())


def set_summary(entry_id: str, summary: str, settings) -> dict:
    """Replace the summary of one entry. Returns `{"ok": true}`; an unknown id is an error."""
    return refresh.set_summary(_corpus(settings), entry_id, summary, _now())


def stale_entries(settings) -> list[str]:
    """The ids of the entries still marked stale."""
    return refresh.stale_entries(_corpus(settings))


def verify_previews(entry_ids: list[str], settings) -> list[dict]:
    """A content preview of each entry, to check its summary against: entry_id, title, summary, source_path and
    content_preview (null when the file cannot be read)."""
    return refresh.verify_previews(_corpus(settings), entry_ids)


def embeddings_status(settings) -> str:
    """`absent` when the corpus has no embeddings; else what detect.py prints: `ready`, `no-model`, `not-installed`, or
    anything else it says (empty when nothing)."""
    return refresh.embeddings_status(_corpus(settings))


def embed(settings) -> dict:
    """Embed index.yaml into index-embeddings.lance/ again (only changed entries). Never downloads a model. Returns ok and error."""
    return refresh.embed(_corpus(settings))


def embeddings_lag(settings) -> int | None:
    """How many entries were indexed after the embeddings were made; null without an embeddings table."""
    return refresh.embeddings_lag(_corpus(settings))


def reference(doc: str, section: str | None = None) -> str:
    """A reference document, whole or one `##`/`###` section: doc is its name, as `graph`, `source-scanner` or `sources/git`.
    An unknown document or section is an error that lists the ones there are."""
    return documents.reference(doc, section)
