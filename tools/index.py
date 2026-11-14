"""`stale_files` and `apply_scan`: which files of the index are stale, and the merge of the scans of them into `index.yaml`.

`apply_scan` is `enrich-headless` Phase 2's merge as code. It is the only writer of `index.yaml` while the scans, which run
at the same time and change nothing, are going on.
"""

from datetime import datetime, timezone
from pathlib import Path

import yaml

REPLACED = ("title", "summary", "tags", "keywords", "category", "content_type", "size", "grep_hint", "headings")
NOT_RETURNED = "no scan returned for it"
NOT_INDEXED = "no entry in the index"


def load_index(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def save_index(path: Path, index: dict) -> None:
    """Keys in the order the file has them, text as written: an unchanged index is written back byte for byte."""
    path.write_text(yaml.safe_dump(index, sort_keys=False, allow_unicode=True))


def _source_of(entry: dict) -> str:
    return entry.get("source") or str(entry["id"]).partition(":")[0]


def _path_of(entry: dict) -> str:
    """The entry's `path`, or, when it has none (most of Polars's), its id without the `<source>:` prefix."""
    return entry.get("path") or str(entry["id"]).removeprefix(f"{_source_of(entry)}:")


def stale_files(settings) -> dict:
    """The file entries of the index marked stale: `by_source` (source id to relative paths) and `entry_ids`.

    A section entry (`tier: section`) is not a file to scan: its parent file is re-scanned when stale, and a section keeps
    its line range until the next build, as `enrich-headless` does.
    """
    entries = load_index(Path(settings.CORPUS_PATH) / "index.yaml").get("entries") or []
    by_source: dict[str, list[str]] = {}
    ids: list[str] = []
    for entry in entries:
        if entry.get("stale") is True and entry.get("tier") != "section":
            by_source.setdefault(_source_of(entry), []).append(_path_of(entry))
            ids.append(entry["id"])
    return {"by_source": by_source, "entry_ids": ids}


def apply_scan(scans: list, settings) -> dict:
    """Merge the scans into `index.yaml`.

    `scans` has one item for each scan run, done or not: `{"source": str, "files": [str], "entries": [dict], "error": str | None}`.
    For each file of a batch: its entry is skipped with the batch's `error` as the reason if there is one; else updated from the
    scanned entry whose `path` is that file; else skipped with the reason `no scan returned for it`. A scanned entry for a file
    the batch did not ask for is ignored. An updated entry takes the nine scanned fields and keeps `id`, `source`, `links_to`,
    `links_from`, `frontmatter` and `concepts`; `path` is set; `stale` is false, `stale_since` null, `last_indexed` now.

    Returns `enriched` (entry ids) and `skipped` (`id`, `reason`).
    """
    index_file = Path(settings.CORPUS_PATH) / "index.yaml"
    index = load_index(index_file)
    by_id = {entry["id"]: entry for entry in index.get("entries") or []}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    enriched: list[str] = []
    skipped: list[dict] = []
    for batch in scans:
        returned = {e.get("path"): e for e in reversed(batch.get("entries") or [])}   # the first of a file's entries wins
        for file in batch.get("files") or []:
            id = f"{batch['source']}:{file}"
            entry = by_id.get(id)
            if batch.get("error"):
                skipped.append({"id": id, "reason": batch["error"]})
            elif entry is None:
                skipped.append({"id": id, "reason": NOT_INDEXED})
            elif file not in returned:
                skipped.append({"id": id, "reason": NOT_RETURNED})
            else:
                for field in REPLACED:
                    entry[field] = returned[file].get(field)
                entry["path"] = file
                entry["stale"], entry["stale_since"], entry["last_indexed"] = False, None, now
                enriched.append(id)
    if enriched:
        save_index(index_file, index)
    return {"enriched": enriched, "skipped": skipped}
