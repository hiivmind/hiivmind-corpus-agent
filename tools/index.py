"""`stale_files` and `apply_scan`: which files of the index are stale, and the merge of the scans of them into `index.yaml`.

`apply_scan` is `enrich-headless` Phase 2's merge as code. It is the only writer of `index.yaml` while the scans, which run
at the same time and change nothing, are going on.
"""

import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPLACED = ("title", "summary", "tags", "keywords", "category", "content_type", "size", "grep_hint", "headings")
NOT_RETURNED = "no scan returned for it"
NOT_INDEXED = "no entry in the index"


def load_index(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


ENTRY_START = re.compile(r"^( *)- ")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _split(text: str) -> tuple[list[str], list[list[str]], list[str]]:
    """The lines of an index file as `(head, entry blocks, tail)`: `head` runs to the first entry, `tail` starts at the first
    line after the entries that is not one of them. Entries are the items of the `entries:` list, at whatever indent it has."""
    lines = text.splitlines(keepends=True)
    after = next((i + 1 for i, line in enumerate(lines) if line.rstrip() == "entries:"), len(lines))
    first = next((i for i in range(after, len(lines)) if ENTRY_START.match(lines[i])), len(lines))
    base = _indent(lines[first]) if first < len(lines) else 0
    blocks: list[list[str]] = []
    end = len(lines)
    for i in range(first, len(lines)):
        line = lines[i]
        if ENTRY_START.match(line) and _indent(line) == base:
            blocks.append([line])
        elif line.strip() and _indent(line) <= base:
            end = i
            break
        else:
            blocks[-1].append(line)
    return lines[:first], blocks, lines[end:]


def _renderer(blocks: list[list[str]]):
    """A function that writes one entry in the layout the file has: its indent, whether a list under a key is indented, and
    whether long text is wrapped (at 80, as PyYAML does) or left on one line."""
    base = _indent(blocks[0][0]) if blocks else 0
    lines = [line for block in blocks for line in block]
    nested = any(
        prev.rstrip().endswith(":") and line.lstrip().startswith("- ") and _indent(line) > _indent(prev)
        for prev, line in zip(lines, lines[1:])
    )
    width = 4096 if any(len(line) > 120 for line in lines) else 80

    class Dumper(yaml.SafeDumper):
        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow, False if nested else indentless)

    def render(entry: dict) -> list[str]:
        dumped = yaml.dump([entry], Dumper=Dumper, sort_keys=False, allow_unicode=True, width=width)
        return textwrap.indent(dumped, " " * base).splitlines(keepends=True)

    return render


def write_entries(path: Path, changed: dict[str, dict]) -> None:
    """Rewrite the entries of the index file at `path` whose id is in `changed`, and nothing else: every other line, and the
    layout (indent, list style, line wrapping) the file has, stay as they are. No entry changed leaves the file untouched."""
    if not changed:
        return
    text = path.read_text()
    head, blocks, tail = _split(text)
    render = _renderer(blocks)
    out = list(head)
    for block in blocks:
        entry = yaml.safe_load("".join(block))[0]
        out += render(changed[entry["id"]]) if entry["id"] in changed else block
    path.write_text("".join(out + tail))


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
    write_entries(index_file, {id: by_id[id] for id in enriched})
    return {"enriched": enriched, "skipped": skipped}
