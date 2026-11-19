"""The instance's tools over the corpus package, as the harness offers them: their names and arguments (design §4.4), and
`merge_scans`, which reads the scans from its state and shows the model no argument (CRP-5)."""

from types import SimpleNamespace

from agent_core.core.checks import StateView
from agent_core.core.functions import import_declared

from tests.helpers import ROOT

SHOWN = {   # each tool and the arguments the model gives it
    "prepare_base": [], "corpus_ready": [], "refresh_needed": [], "source_freshness": [], "stale_batches": [],
    "apply_source_update": ["source", "old_sha", "new_sha"], "drop_missing": ["sources"], "merge_scans": [],
    "set_concepts": ["assignments"], "set_summary": ["entry_id", "summary"], "stale_entries": [],
    "verify_previews": ["entry_ids"], "embeddings_status": [], "embed": [], "embeddings_lag": [], "reference": ["doc", "section"],
    "corpus_status": [], "index_is_v2": [], "index_is_v1": [], "sources_handled": [], "graph_exists": [], "migrate_index": [],
    "validate_graph": [],
}


def scanned(path: str) -> dict:
    return {
        "path": path, "title": path, "summary": f"{path}, rescanned.", "tags": [], "keywords": [], "category": "guide",
        "content_type": "markdown", "size": "standard", "grep_hint": None, "headings": [],
    }


class Tools:
    """The instance's declared functions, called as the harness calls them: `settings` and `state` filled, the model's arguments given."""

    def __init__(self, instance, settings):
        self.settings = settings
        self.by_name = {tool.name: tool for tool in import_declared(ROOT, instance.functions)}

    def specs(self):
        return [tool.spec for tool in self.by_name.values()]

    async def call(self, name: str, arguments: dict, state: dict):
        tool = self.by_name[name]
        filled = {"settings": self.settings, "state": state}
        return tool.fn(**arguments, **{key: filled[key] for key in tool.filled})


def tools(instance, settings) -> Tools:
    return Tools(instance, settings)


async def test_each_declared_tool_is_offered_with_the_arguments_of_the_design(instance, corpus):
    specs = {spec.name: spec for spec in tools(instance, corpus.settings).specs()}
    assert {name: list(spec.schema["properties"]) for name, spec in specs.items()} == SHOWN
    assert specs["reference"].schema.get("required") == ["doc"]
    assert all(spec.description != spec.name for spec in specs.values())   # each says what it does


async def test_merge_scans_shows_the_model_no_arguments(instance, corpus):
    [spec] = [s for s in tools(instance, corpus.settings).specs() if s.name == "merge_scans"]
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


async def test_a_relative_corpus_path_is_the_corpus_under_the_working_directory(instance, corpus_stale, monkeypatch):   # final review 4
    monkeypatch.chdir(corpus_stale.path.parent)
    settings = SimpleNamespace(**{**vars(corpus_stale.settings), "CORPUS_PATH": corpus_stale.path.name})
    [preview] = await tools(instance, settings).call("verify_previews", {"entry_ids": ["docs:a.md"]}, {})
    assert preview["entry_id"] == "docs:a.md" and preview["content_preview"]


async def test_the_tools_behind_node_outputs_write_them_to_state(instance, corpus_v1_bullets):   # CJW-7
    source = tools(instance, corpus_v1_bullets.settings)
    outputs = {
        "migrate_index": {"migrated", "migrate_skipped", "strategy", "sections"},
        "corpus_status": {"sources", "index_format", "stale_count", "embeddings_lag", "refresh_needed", "status_errors"},
        "validate_graph": {"concepts", "relationships", "issues", "valid"},
    }
    for name, written in outputs.items():
        if name == "validate_graph":
            corpus_v1_bullets.write("graph.yaml", "schema_version: 2\nconcepts: {}\n")
        state = StateView()
        result = await source.call(name, {}, state)
        assert state.written == written and {key: state[key] for key in written} == result, name
    assert state["valid"] is False   # the graph has no `meta`
