"""`stale_files`, `apply_scan` and `drop_missing`: which files of the index are stale, the merge of the scans of them into
`index.yaml`, and the removal of the entries whose files are gone from the source.

`apply_scan` is `enrich-headless` Phase 2's merge as code. It is the only writer of `index.yaml` while the scans, which run
at the same time and change nothing, are going on.
"""

import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPLACED = ("title", "summary", "tags", "keywords", "category", "content_type", "size", "grep_hint", "headings")
NOT_RETURNED = "no scan returned for it (file unreadable or not in the source)"
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


def remove_entries(path: Path, ids: set[str]) -> None:
    """Remove the entries of the index file at `path` whose id is in `ids`, and nothing else: only the lines of those entries
    go. No entry removed leaves the file untouched."""
    if not ids:
        return
    text = path.read_text()
    head, blocks, tail = _split(text)
    kept = [block for block in blocks if yaml.safe_load("".join(block))[0]["id"] not in ids]
    if len(kept) < len(blocks):
        path.write_text("".join(head + [line for block in kept for line in block] + tail))


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
    scanned entry whose `path` is that file; else skipped with the reason `no scan returned for it (file unreadable or not in
    the source)`. A scanned entry for a file the batch did not ask for is ignored. An updated entry takes the nine scanned fields and keeps `id`, `source`, `links_to`,
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


def _scalar(text: str):
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def _drop_from_graph(path: Path, ids: set[str]) -> None:
    """Remove `ids` from the `entries` lists of the concepts of `graph.yaml` (schema version 1; version 2 has no such list),
    line by line: nothing else in the file changes. A file without such a list, or without those ids in it, is left alone."""
    if not path.is_file():
        return
    lines = path.read_text().splitlines(keepends=True)
    out: list[str] = []
    changed = False
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r"^( +)entries:[ \t]*(.*?)(\r?\n?)$", line)
        if not match:
            out.append(line)
            i += 1
            continue
        indent, rest, newline = match.groups()
        if rest.startswith("["):   # `entries: [a, b]`
            items = _scalar(rest)
            if isinstance(items, list) and any(item in ids for item in items):
                tokens = [t.strip() for t in rest[1:rest.rindex("]")].split(",")]   # the items as written, quotes and all
                if len(tokens) != len(items):   # a comma inside an item: write the list again
                    tokens = [yaml.safe_dump(item, default_flow_style=True, width=10**9).strip() for item in items]
                kept = [t for t, item in zip(tokens, items) if item not in ids]
                out.append(f"{indent}entries: [{', '.join(kept)}]{newline}")
                changed = True
            else:
                out.append(line)
            i += 1
            continue
        out.append(line)   # `entries:` and a block list, indented or not, under it
        i += 1
        while i < len(lines):
            item = re.match(r"^( *)- (.*?)\s*$", lines[i])
            if item is None and lines[i].strip():
                break
            if item is not None and len(item.group(1)) < len(indent):
                break
            if item is not None and _scalar(re.sub(r"\s+#.*$", "", item.group(2))) in ids:
                changed = True
            else:
                out.append(lines[i])
            i += 1
    if changed:
        path.write_text("".join(out))


def drop_missing(settings) -> dict:
    """Remove the entries whose file is gone from its git source: `{"removed": [entry ids]}`.

    For each file entry (not `tier: section`) of a `git` source of `config.yaml`, the file is `.source/<source id>/<docs_root>/<path>`
    (`docs_root` `.` or absent: none; `path` as `stale_files` takes it). When it does not exist in the checkout the refresh has
    just updated, the entry goes from `index.yaml`, and its id from the `entries` lists of `graph.yaml`, if it has any. A source
    with no checkout (the refresh failed or never cloned it) is left alone: nothing is removed on a checkout that is not there.
    """
    corpus = Path(settings.CORPUS_PATH)
    config = yaml.safe_load((corpus / "config.yaml").read_text()) or {}
    git = {s["id"]: s for s in config.get("sources") or [] if s.get("type") == "git"}
    index_file = corpus / "index.yaml"
    removed: list[str] = []
    for entry in load_index(index_file).get("entries") or []:
        source = git.get(_source_of(entry))
        checkout = corpus / ".source" / source["id"] if source else None
        if checkout is None or not checkout.is_dir() or entry.get("tier") == "section":
            continue
        docs_root = source.get("docs_root") or "."
        if not (checkout / docs_root / _path_of(entry)).exists():
            removed.append(entry["id"])
    remove_entries(index_file, set(removed))
    _drop_from_graph(corpus / "graph.yaml", set(removed))
    return {"removed": removed}
