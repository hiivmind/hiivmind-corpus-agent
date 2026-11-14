"""`stale_files` and `apply_scan`: finding the stale entries, and merging the scans into `index.yaml`."""

import difflib
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agent_core.tools.function import FunctionSource
from tests.helpers import ROOT
from tools.index import apply_scan, load_index, stale_files, write_entries

CLONE = Path("/home/nathanielramm/git/hiivmind/hiivmind-corpus-data")
INDEX = "hiivmind-corpus-polars/index.yaml"
POLARS = CLONE / INDEX


def scanned(path: str, summary: str) -> dict:
    """A complete scan result for one file: `path` and the nine fields."""
    return {
        "path": path, "title": f"{path} rescanned", "summary": summary, "tags": ["rescanned"], "keywords": ["new"],
        "category": "guide", "content_type": "markdown", "size": "large", "grep_hint": "grep -n '^## ' FILE",
        "headings": [{"anchor": "intro", "title": "Intro"}],
    }


SCANNED_A = scanned("a.md", "A, rescanned.")
SCANNED_UNASKED = scanned("z.md", "Z, which no batch asked for.")


def test_stale_files_groups_by_source_and_skips_sections_under_a_stale_parent(corpus_stale):
    corpus_stale.add_entry({"id": "docs:a.md#intro", "tier": "section", "parent": "docs:a.md", "stale": True})
    assert stale_files(corpus_stale.settings) == {"by_source": {"docs": ["a.md", "b.md"]}, "entry_ids": ["docs:a.md", "docs:b.md"]}


def test_a_stale_entry_without_path_takes_it_from_its_id(corpus_stale):
    corpus_stale.add_entry({"id": "docs:guide/c.md", "source": "docs", "stale": True})
    corpus_stale.add_entry({"id": "other:x/y.md", "stale": True})   # no `source` either: the id's prefix names it
    found = stale_files(corpus_stale.settings)
    assert found["by_source"] == {"docs": ["a.md", "b.md", "guide/c.md"], "other": ["x/y.md"]}
    assert found["entry_ids"] == ["docs:a.md", "docs:b.md", "docs:guide/c.md", "other:x/y.md"]


def test_apply_replaces_the_scanned_fields_and_preserves_the_rest(corpus_stale):
    before = corpus_stale.entry("docs:a.md")
    r = apply_scan([{"source": "docs", "files": ["a.md"], "entries": [SCANNED_A], "error": None}], corpus_stale.settings)
    after = corpus_stale.entry("docs:a.md")
    assert r["enriched"] == ["docs:a.md"] and after["summary"] == "A, rescanned." and after["stale"] is False
    assert (after["id"], after["links_to"], after["concepts"]) == (before["id"], before["links_to"], before["concepts"])
    assert (after["source"], after["path"], after["links_from"], after["frontmatter"]) == (
        before["source"], before["path"], before["links_from"], before["frontmatter"]
    )
    for field in ("title", "tags", "keywords", "category", "content_type", "size", "grep_hint", "headings"):
        assert after[field] == SCANNED_A[field]
    assert after["stale_since"] is None and after["last_indexed"] > before["last_indexed"]


def test_an_entry_not_asked_for_is_ignored_and_a_missing_one_is_skipped(corpus_stale):   # Review Focus 5
    r = apply_scan([{"source": "docs", "files": ["a.md", "b.md"], "entries": [SCANNED_A, SCANNED_UNASKED], "error": None}], corpus_stale.settings)
    assert r["enriched"] == ["docs:a.md"] and r["skipped"] == [{"id": "docs:b.md", "reason": "no scan returned for it (file unreadable or not in the source)"}]
    assert corpus_stale.entry("docs:b.md")["stale"] is True
    assert [e["id"] for e in yaml.safe_load((corpus_stale.path / "index.yaml").read_text())["entries"] if e["id"].endswith("z.md")] == []


def test_a_failed_scan_skips_its_whole_batch_with_the_reason(corpus_stale):
    r = apply_scan([{"source": "docs", "files": ["a.md", "b.md"], "entries": [], "error": "no_exit"}], corpus_stale.settings)
    assert r == {"enriched": [], "skipped": [{"id": "docs:a.md", "reason": "no_exit"}, {"id": "docs:b.md", "reason": "no_exit"}]}
    assert corpus_stale.entry("docs:a.md")["stale"] is True


def test_a_batch_with_an_error_enriches_nothing_even_if_it_carries_entries(corpus_stale):
    r = apply_scan([{"source": "docs", "files": ["a.md"], "entries": [SCANNED_A], "error": "interrupted"}], corpus_stale.settings)
    assert r == {"enriched": [], "skipped": [{"id": "docs:a.md", "reason": "interrupted"}]}
    assert corpus_stale.entry("docs:a.md")["summary"] == "The file a.md."


def test_batches_are_merged_each_on_its_own(corpus_stale):
    r = apply_scan([
        {"source": "docs", "files": ["a.md"], "entries": [SCANNED_A], "error": None},
        {"source": "docs", "files": ["b.md"], "entries": [], "error": "invalid_output"},
    ], corpus_stale.settings)
    assert r == {"enriched": ["docs:a.md"], "skipped": [{"id": "docs:b.md", "reason": "invalid_output"}]}


def test_a_file_the_index_has_no_entry_for_is_skipped(corpus_stale):
    r = apply_scan([{"source": "docs", "files": ["z.md"], "entries": [SCANNED_UNASKED], "error": None}], corpus_stale.settings)
    assert r == {"enriched": [], "skipped": [{"id": "docs:z.md", "reason": "no entry in the index"}]}


def test_an_entry_without_path_is_found_by_id_and_given_its_path(corpus_stale):                 # R11
    corpus_stale.add_entry({"id": "docs:guide/c.md", "source": "docs", "title": "C", "summary": "Old.", "tags": ["old"], "stale": True})
    r = apply_scan([{"source": "docs", "files": ["guide/c.md"], "entries": [scanned("guide/c.md", "C, rescanned.")], "error": None}], corpus_stale.settings)
    after = corpus_stale.entry("docs:guide/c.md")
    assert r["enriched"] == ["docs:guide/c.md"] and after["path"] == "guide/c.md" and after["summary"] == "C, rescanned."
    assert after["stale"] is False and after["stale_since"] is None and after["id"] == "docs:guide/c.md"


def test_nothing_enriched_leaves_the_index_file_alone(corpus_stale):
    index = corpus_stale.path / "index.yaml"
    before = index.stat().st_mtime_ns, index.read_bytes()
    apply_scan([{"source": "docs", "files": ["a.md"], "entries": [], "error": "no_exit"}], corpus_stale.settings)
    assert (index.stat().st_mtime_ns, index.read_bytes()) == before


def polars_on_main(tmp_path: Path) -> Path | None:
    """The Polars index as `origin/main` of the owner's corpus clone has it, copied into `tmp_path`; read only."""
    shown = subprocess.run(["git", "-C", str(CLONE), "show", f"origin/main:{INDEX}"], capture_output=True, text=True)
    if shown.returncode:
        return None
    copy = tmp_path / "main" / "index.yaml"
    copy.parent.mkdir()
    copy.write_text(shown.stdout)
    return copy


def polars_working_copy(tmp_path: Path) -> Path | None:
    if not POLARS.is_file():
        return None
    copy = tmp_path / "working" / "index.yaml"
    copy.parent.mkdir()
    shutil.copy(POLARS, copy)
    return copy


def either_polars(tmp_path: Path, which: str) -> Path:
    copy = (polars_on_main if which == "main" else polars_working_copy)(tmp_path)
    if copy is None:
        pytest.skip(f"the {which} version of the Polars index is not on this machine")
    return copy


@pytest.mark.parametrize("which", ["main", "working"])
def test_an_unchanged_polars_index_is_written_back_byte_identical(tmp_path, which):               # R12
    copy = either_polars(tmp_path, which)
    before = copy.read_bytes()
    write_entries(copy, {})
    assert copy.read_bytes() == before
    r = apply_scan([{"source": "polars", "files": ["index.md"], "entries": [], "error": "no_exit"}], SimpleNamespace(CORPUS_PATH=copy.parent))
    assert r["enriched"] == [] and copy.read_bytes() == before


@pytest.mark.parametrize("which", ["main", "working"])
def test_merging_into_the_polars_index_changes_only_the_scanned_entry(tmp_path, which):
    copy = either_polars(tmp_path, which)
    before_text = copy.read_text()
    before = load_index(copy)
    r = apply_scan([{"source": "polars", "files": ["index.md"], "entries": [scanned("index.md", "Rescanned.")], "error": None}], SimpleNamespace(CORPUS_PATH=copy.parent))
    after = load_index(copy)
    assert r == {"enriched": ["polars:index.md"], "skipped": []}
    assert after["meta"] == before["meta"] and after["entries"][1:] == before["entries"][1:]
    assert after["entries"][0]["path"] == "index.md" and after["entries"][0]["summary"] == "Rescanned."
    changed = [d for d in difflib.unified_diff(before_text.splitlines(), copy.read_text().splitlines(), lineterm="", n=0) if d[0] in "+-" and d[:3] not in ("+++", "---")]
    assert 0 < len(changed) < 40, f"{len(changed)} lines changed"


def test_an_updated_entry_is_written_in_the_layout_of_the_file(tmp_path):
    copy = either_polars(tmp_path, "main")
    apply_scan([{"source": "polars", "files": ["index.md"], "entries": [scanned("index.md", "Rescanned.")], "error": None}], SimpleNamespace(CORPUS_PATH=copy.parent))
    lines = copy.read_text().splitlines()
    first = lines.index("  - id: polars:index.md")
    assert lines[first + 1] == "    source: polars" and "      - rescanned" in lines[first : first + 40]   # indented sequences, entries two in
    assert any(line.startswith("    summary: Rescanned.") for line in lines[first : first + 40])


async def test_the_function_tools_take_their_arguments_as_json_values(corpus_stale):
    source = FunctionSource(
        {"stale_files": "tools.index:stale_files", "apply_scan": "tools.index:apply_scan"}, corpus_stale.settings, ROOT
    )
    shown = {spec.name: spec.schema for spec in await source.tools()}
    assert shown["stale_files"]["properties"] == {} and shown["apply_scan"]["required"] == ["scans"]
    assert shown["apply_scan"]["properties"]["scans"]["type"] == "array"
    assert await source.call("stale_files", {}, {}) == {"by_source": {"docs": ["a.md", "b.md"]}, "entry_ids": ["docs:a.md", "docs:b.md"]}
    r = await source.call("apply_scan", {"scans": [{"source": "docs", "files": ["a.md"], "entries": [SCANNED_A], "error": None}]}, {})
    assert r == {"enriched": ["docs:a.md"], "skipped": []}
