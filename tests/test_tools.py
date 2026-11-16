"""The instance's tools over the corpus package, as the harness offers them: their names and arguments (design §4.4), and
`merge_scans`, which reads the scans from its state and shows the model no argument (CRP-5)."""

from agent_core.tools.function import FunctionSource

from tests.helpers import ROOT

SHOWN = {   # each tool and the arguments the model gives it
    "prepare_base": [], "corpus_ready": [], "refresh_needed": [], "source_freshness": [], "stale_batches": [],
    "apply_source_update": ["source", "old_sha", "new_sha"], "drop_missing": ["sources"], "merge_scans": [],
    "set_concepts": ["assignments"], "set_summary": ["entry_id", "summary"], "stale_entries": [],
    "verify_previews": ["entry_ids"], "embeddings_status": [], "embed": [], "embeddings_lag": [], "reference": ["doc", "section"],
}


def scanned(path: str) -> dict:
    return {
        "path": path, "title": path, "summary": f"{path}, rescanned.", "tags": [], "keywords": [], "category": "guide",
        "content_type": "markdown", "size": "standard", "grep_hint": None, "headings": [],
    }


def tools(instance, settings) -> FunctionSource:
    return FunctionSource(instance.functions, settings, ROOT)


async def test_each_declared_tool_is_offered_with_the_arguments_of_the_design(instance, corpus):
    specs = {spec.name: spec for spec in await tools(instance, corpus.settings).tools()}
    assert {name: list(spec.schema["properties"]) for name, spec in specs.items()} == SHOWN
    assert specs["reference"].schema.get("required") == ["doc"]
    assert all(spec.description != spec.name for spec in specs.values())   # each says what it does


async def test_merge_scans_shows_the_model_no_arguments(instance, corpus):
    [spec] = [s for s in await tools(instance, corpus.settings).tools() if s.name == "merge_scans"]
    assert spec.schema["properties"] == {} and "required" not in spec.schema


async def test_merge_scans_reads_the_scans_from_its_state(instance, corpus_stale):
    source = tools(instance, corpus_stale.settings)
    state = {"scans": [{"entries": [scanned("a.md")]}], "scans_failures": [], "enriched_ids": "not this"}
    assert await source.call("merge_scans", {}, state) == {"enriched": ["docs:a.md"], "skipped": [{"id": "docs:b.md", "reason": "no scan returned for it (file unreadable or not in the source)"}]}
    assert corpus_stale.entry("docs:a.md")["summary"] == "a.md, rescanned."


async def test_a_tool_passes_the_corpus_of_the_settings(instance, corpus_stale):
    source = tools(instance, corpus_stale.settings)
    assert await source.call("stale_entries", {}, {}) == ["docs:a.md", "docs:b.md"]
    assert await source.call("stale_batches", {}, {}) == [{"source": "docs", "files": ["a.md", "b.md"]}]
    assert await source.call("prepare_base", {}, {}) is True
