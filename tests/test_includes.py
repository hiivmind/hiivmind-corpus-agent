"""INS-8: the package's documents as includes, cut by heading; no include or node names a script or procedure that is not there."""

import re

from tests.helpers import ROOT

INCLUDES = ROOT / "includes"
ABSENT = ("search.py", "chunk.py", "detect_nav.py", "detect_large_files.py", "split_by_headings.py", "detect.py", "uv run",
          "render-index.sh", "${CLAUDE_PLUGIN_ROOT}")


def _text(name: str) -> str:
    return (INCLUDES / name).read_text()


def test_no_include_or_node_names_a_script_or_procedure_that_does_not_exist():
    for path in [*INCLUDES.rglob("*.md"), *(ROOT / "nodes").glob("*.md")]:
        text = path.read_text()
        for name in ABSENT:
            assert name not in text, f"{path}: {name}"
        assert not re.search(r"\byq\b", text), path


def test_entry_metadata_keeps_the_six_fields():
    text = _text("entry-metadata.md")
    assert "Entry Metadata Generation" in text
    for field in ("path", "title", "summary", "tags", "keywords", "category"):
        assert f"**{field}**" in text, field
    for gone in ("content_type", "Step 0", "Step 1b", "Section Entry Generation", "Chunk Generation", "Extraction", "Sampling"):
        assert gone not in text, gone


def test_graph_keeps_its_schema_and_vocabularies():
    text = _text("graph.md")
    for kept in ("## Purpose", "Schema Definition", "Concept ID Conventions", "Relationship Type Vocabulary", "Origin Types", "Validation Rules"):
        assert kept in text, kept
    for gone in ("Graph Generation from Extraction Output", "yq Query Patterns", "When to Use"):
        assert gone not in text, gone


def test_index_fields_keeps_the_field_tables():
    text = _text("index-fields.md")
    for kept in ("Field Definitions", "Section Entries", "Meta Section", "`standard` or `large`", "`stale_since`", "`last_indexed`"):
        assert kept in text, kept
    for gone in ("Schema Definition (Strict)", "yq Query Patterns"):
        assert gone not in text, gone


def test_embeddings_names_the_four_states_and_keeps_its_sections():
    text = _text("embeddings.md")
    for kept in ("absent", "not-installed", "no-model", "ready", "Dependencies", "Data Model", "Embedding Strategy", "Incremental updates",
                 "Staleness Detection", "Embedding Lag", "Graceful Degradation", "text_hash"):
        assert kept in text, kept
    for gone in ("Querying", "Reranking", "Hybrid", "Cross-corpus", "Remote", "Exit Codes", "chunks-embeddings"):
        assert gone not in text, gone


def test_freshness_keeps_only_the_write_time_check():
    text = _text("freshness.md")
    assert "Purpose" in text and "Write-Time" in text
    for gone in ("Read-Time", "Re-scan Dispatch", "Option A", "Option B"):
        assert gone not in text, gone


def test_the_git_fragment_keeps_the_clone_recipe():
    text = _text("sources/git.md")
    for kept in ("sparse-checkout set", "--skip-checks", "checkout -q -B <branch> <commit>"):
        assert kept in text, kept
    assert "Get Clone SHA" not in text


def test_the_render_include_and_the_documents_that_became_nothing_are_gone():
    assert not (INCLUDES / "render-index.md").exists()
    for name in ("index-updating.md", "paths.md", "sources/shared.md"):
        assert not (INCLUDES / name).exists(), name
