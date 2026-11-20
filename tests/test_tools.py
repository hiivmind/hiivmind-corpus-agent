"""The instance's tools over the corpus package, as the harness offers them: their names and arguments (design §4.4), and
`merge_scans`, which reads the scans from its state and shows the model no argument (CRP-5)."""

from types import SimpleNamespace

import pytest
import yaml

from hiivmind_corpus import CorpusError, ExtraMissing

from agent_core.core.checks import StateView
from agent_core.core.functions import import_declared

from tests.helpers import ROOT

SHOWN = {   # each tool and the arguments the model gives it
    "corpus_ready": [], "index_is_v2": [], "index_is_v1": [], "graph_exists": [], "sources_handled": [],
    "source_freshness": ["observed"], "corpus_status": ["observed"], "stale_batches": [], "stale_entries": [],
    "locate_files": ["source", "files"], "begin_update": [],
    "apply_source_update": ["source", "new_sha", "changes_file"], "drop_missing": ["source", "head", "listing_file"],
    "merge_scans": [], "set_concepts": ["assignments"], "set_summary": ["entry_id", "summary"],
    "verify_previews": ["entry_ids"], "embeddings_status": [], "embeddings_lag": [], "embed": [],
    "migrate_index": [], "validate_graph": [],
}


def scanned(path: str) -> dict:
    return {
        "path": path, "title": path, "summary": f"{path}, rescanned.", "tags": [], "keywords": [], "category": "guide",
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
            corpus_v1_bullets.write("graph.yaml", "schema_version: 2\nconcepts: {}\nrelationships:\n  - {from: x, to: y, type: related}\n")
        state = StateView()
        result = await source.call(name, {"observed": []} if name == "corpus_status" else {}, state)
        assert state.written == written and {key: state[key] for key in written} == result, name
    assert state["valid"] is False   # a relationship whose ends are no concept (§7.4)


def head_of(corpus):
    return [{"id": "docs", "head": corpus.upstream_head}]


async def test_the_status_tool_records_exactly_the_declared_outputs_of_status(instance, corpus):   # INS-15
    state = StateView()
    await tools(instance, corpus.settings).call("corpus_status", {"observed": head_of(corpus)}, state)
    assert state.written == set(instance.nodes["status"].contract.outputs)
    assert state["refresh_needed"] is True and state["status_errors"] == []


async def test_corpus_status_reports_an_unobserved_source_without_raising(instance, corpus):
    state = StateView()
    observed = [{"id": "docs", "error": "git ls-remote x failed: boom"}]
    await tools(instance, corpus.settings).call("corpus_status", {"observed": observed}, state)
    assert state["sources"] == [{"id": "docs", "type": "git", "freshness": "unknown"}]
    assert state["refresh_needed"] is True and any("boom" in e for e in state["status_errors"])


async def test_a_failed_ls_remote_is_unknown_not_raised(instance, corpus):
    source = tools(instance, corpus.settings)
    [row] = await source.call("source_freshness", {"observed": [{"id": "docs", "error": "git ls-remote x failed: boom"}]}, {})
    assert row["freshness"] == "unknown" and "boom" in row["error"]
    [row] = await source.call("source_freshness", {"observed": [{"id": "docs", "head": corpus.first_sha}]}, {})
    assert row["freshness"] == "current"
    [row] = await source.call("source_freshness", {"observed": head_of(corpus)}, {})
    assert row == {"id": "docs", "type": "git", "freshness": "behind", "error": None}


async def test_a_v1_corpus_has_a_null_stale_count(instance, corpus_v1_bullets):
    state = StateView()
    await tools(instance, corpus_v1_bullets.settings).call("corpus_status", {"observed": []}, state)
    assert state["stale_count"] is None and state["index_format"] == "v1"


async def test_begin_update_records_the_zero_totals(instance, corpus):
    state = StateView()
    assert await tools(instance, corpus.settings).call("begin_update", {}, state) is True
    assert state.written == {"index_changes", "removed_ids", "excluded_paths"}
    assert state["index_changes"] == {"added": 0, "modified": 0, "removed": 0, "stale_entries": []}


def write_input(corpus, text: str, name: str = "docs.changes") -> str:
    folder = corpus.path / ".source"
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(text)
    return str(folder / name)


async def update(source, corpus, state, text):
    return await source.call("apply_source_update", {"source": "docs", "new_sha": corpus.upstream_head, "changes_file": write_input(corpus, text)}, state)


async def test_apply_source_update_reads_the_file_and_adds_to_the_totals(instance, corpus):   # INS-3, 4, 5
    source, state = tools(instance, corpus.settings), {}
    await source.call("begin_update", {}, state)
    result = await update(source, corpus, state, "M\0docs/a.md\0A\0docs/d.md\0D\0docs/c.md\0")
    assert result == {"files_changed": 3, "added": 1, "modified": 1, "removed": 1, "removed_ids": ["docs:c.md"],
                      "stale_entries": ["docs:a.md", "docs:d.md"], "excluded": [], "outside_docs_root": 0}
    assert state["index_changes"] == {"added": 1, "modified": 1, "removed": 1, "stale_entries": ["docs:a.md", "docs:d.md"]}
    assert state["removed_ids"] == ["docs:c.md"] and state["excluded_paths"] == []
    assert yaml.safe_load((corpus.path / "config.yaml").read_text())["sources"][0]["last_commit_sha"] == corpus.upstream_head
    assert "docs:c.md" not in (corpus.path / "index.md").read_text()
    await update(source, corpus, state, "M\0docs/b.md\0")
    assert state["index_changes"]["modified"] == 2


async def test_a_path_outside_docs_root_is_counted_and_changes_nothing(instance, corpus):
    source, state = tools(instance, corpus.settings), {}
    await source.call("begin_update", {}, state)
    result = await update(source, corpus, state, "M\0README.md\0")
    assert result["outside_docs_root"] == 1 and result["added"] == result["modified"] == result["removed"] == 0


async def test_a_truncated_changes_file_is_an_error_and_records_nothing(instance, corpus):   # E6
    source, state = tools(instance, corpus.settings), {}
    await source.call("begin_update", {}, state)
    before = (corpus.path / "config.yaml").read_text()
    with pytest.raises(CorpusError) as raised:
        await update(source, corpus, state, "M\0docs/a.md\0D")
    assert raised.value.code == "invalid-changes"
    assert state["index_changes"] == {"added": 0, "modified": 0, "removed": 0, "stale_entries": []}
    assert (corpus.path / "config.yaml").read_text() == before


async def test_an_unknown_source_is_an_error(instance, corpus):   # E4
    source, state = tools(instance, corpus.settings), {}
    await source.call("begin_update", {}, state)
    with pytest.raises(CorpusError) as raised:
        await source.call("apply_source_update", {"source": "nope", "new_sha": "x", "changes_file": write_input(corpus, "M\0docs/a.md\0")}, state)
    assert raised.value.code == "unknown-source"


async def test_a_docs_root_of_dot_reads_root_paths(instance, monkeypatch, tmp_path, _current):
    from tests.conftest import _make
    corpus = _make(monkeypatch, _current, tmp_path, docs_root=".")
    source, state = tools(instance, corpus.settings), {}
    await source.call("begin_update", {}, state)
    assert (await update(source, corpus, state, "M\0a.md\0"))["modified"] == 1


async def test_locate_files_normalises_docs_root(instance, corpus_stale):
    config = yaml.safe_load((corpus_stale.path / "config.yaml").read_text())
    config["sources"][0]["docs_root"] = "docs/"
    (corpus_stale.path / "config.yaml").write_text(yaml.safe_dump(config))
    [row] = await tools(instance, corpus_stale.settings).call("locate_files", {"source": "docs", "files": ["a.md"]}, {})
    assert row["file"] == str(corpus_stale.path / ".source" / "docs" / "docs" / "a.md")


async def test_drop_missing_reads_the_listing_and_adds_the_ids(instance, corpus):   # INS-13
    source, state = tools(instance, corpus.settings), {}
    await source.call("begin_update", {}, state)
    listing = write_input(corpus, "docs/a.md\0docs/b.md\0", "docs.listing")
    result = await source.call("drop_missing", {"source": "docs", "head": corpus.first_sha, "listing_file": listing}, state)
    assert result["removed_ids"] == ["docs:c.md"] and state["removed_ids"] == ["docs:c.md"]
    assert state["index_changes"]["removed"] == 0


async def test_drop_missing_for_another_head_removes_nothing(instance, corpus):
    source, state = tools(instance, corpus.settings), {}
    await source.call("begin_update", {}, state)
    listing = write_input(corpus, "docs/a.md\0", "docs.listing")
    result = await source.call("drop_missing", {"source": "docs", "head": "deadbee", "listing_file": listing}, state)
    assert result["skipped"] == "head-mismatch" and result["removed_ids"] == [] and state["removed_ids"] == []


async def test_locate_files_names_the_file_of_each_path(instance, corpus_stale):
    source = tools(instance, corpus_stale.settings)
    assert await source.call("locate_files", {"source": "docs", "files": ["a.md"]}, {}) == [
        {"path": "a.md", "file": str(corpus_stale.path / ".source" / "docs" / "docs" / "a.md"), "url": None}]
    assert await source.call("locate_files", {"source": "docs", "files": ["zz.md"]}, {}) == [{"path": "zz.md", "file": None, "url": None}]


async def test_set_concepts_returns_a_count(instance, corpus):
    assert await tools(instance, corpus.settings).call("set_concepts", {"assignments": {"docs:a.md": ["concept"]}}, {}) == {"assigned": 1}


async def test_embed_returns_ok_and_error_from_a_caught_corpus_error(instance, corpus, monkeypatch):
    def refuse():
        raise ExtraMissing("install hiivmind-corpus-lib[embeddings]")
    source = tools(instance, corpus.settings)
    monkeypatch.setitem(source.by_name["embed"].fn.__globals__, "_open", lambda settings: SimpleNamespace(embeddings=SimpleNamespace(embed=refuse)))   # the module the harness loaded
    assert await source.call("embed", {}, {}) == {"ok": False, "error": "install hiivmind-corpus-lib[embeddings]"}
