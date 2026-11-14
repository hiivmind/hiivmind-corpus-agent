"""The nodes of the instance, run with the scripted backend: each node's contract."""

from datetime import date

import yaml
from agent_core.backends.scripted import ScriptedBackend
from agent_core.core.job_runner import open_run

from tests.helpers import ROOT


class KeepingInstructions:
    """A scripted backend that keeps the instructions of the brief it was given: the filled procedure."""

    def __init__(self, script: list):
        self._inner = ScriptedBackend(script=script)
        self.instructions: str | None = None

    async def drive(self, brief, controller):
        self.instructions = brief.instructions
        return await self._inner.drive(brief, controller)


async def filled_procedure(corpus, node: str, inputs: dict) -> str:
    """The procedure of a node as the model reads it for these inputs: the instructions after the line that names the node.

    (The rules before it carry examples such as "Sources to update: not given", so only this part says what the node was given.)
    """
    backend = KeepingInstructions(["I have read the procedure."])
    async with open_run(ROOT / "instance.yaml", settings_files=[corpus.settings_file], run_dir=corpus.next_dir("run")) as opened:
        await opened.run_node(node, inputs, driver=backend)
    _, _, procedure = backend.instructions.partition(f"# Procedure of the node that is running: `{node}`")
    assert procedure, "the instructions have no procedure line"
    return procedure


def test_scan_declares_its_contract(instance):
    node = instance.nodes["scan"]
    assert set(node.inputs) == {"source", "files"}
    assert node.outputs["entries"]["type"] == "array"
    assert node.outputs["entries"]["items"]["required"] == [
        "path", "title", "summary", "tags", "keywords", "category", "content_type", "size", "grep_hint", "headings",
    ]
    assert node.exits == ("done", "failed") and node.context == "none"
    assert node.allowed_tools == ("files__read_text_file", "files__list_directory", "shell__run")


async def test_scan_contract(corpus_stale, run):
    assert (await run("scan", {"source": "docs", "files": ["a.md"]}))["outcome"] == "done"
    assert (await run("scan", {"source": "docs", "files": ["a.md"]}, case="scan_bad"))["reason"] == "invalid_output"   # an entry without summary, twice


async def test_scan_returns_the_entry_the_script_wrote_for_the_file(corpus_stale, run):
    result = await run("scan", {"source": "docs", "files": ["a.md"]})
    [entry] = result["outputs"]["entries"]
    assert entry["path"] == "a.md" and entry["content_type"] == "markdown" and entry["size"] == "standard"


async def test_scan_sends_back_a_category_outside_the_enum(corpus_stale, run):
    result = await run("scan", {"source": "docs", "files": ["a.md"]}, case="scan_bad_category")   # wrong twice
    assert result["outcome"] == "failed" and result["reason"] == "invalid_output"
    assert any("category" in e and "essay" in e for e in result["errors"])


def test_refresh_declares_its_contract(instance):
    node = instance.nodes["refresh"]
    assert set(node.inputs) == {"sources"}
    assert set(node.outputs) == {"sources", "index_changes", "embeddings", "embeddings_lag", "errors"}
    source = node.outputs["sources"]["items"]
    assert source["required"] == ["id", "type", "status", "old_sha", "new_sha", "files_changed"]
    assert source["properties"]["status"]["enum"] == ["current", "updated", "failed", "skipped-manual"]
    assert node.outputs["index_changes"]["required"] == ["added", "modified", "removed", "stale_entries"]
    assert node.outputs["embeddings"]["enum"] == ["updated", "skipped", "no-model", "not-installed", "deferred"]
    assert node.exits == ("done", "declined", "failed") and node.context == "none"
    assert node.allowed_tools == (
        "shell__run", "files__read_text_file", "files__write_file", "files__edit_file", "files__search_files",
        "files__list_directory",
    )
    assert len(node.preconditions) == 1


async def test_refresh_contract(corpus, run):
    result = await run("refresh", {"sources": "all"})
    assert result["outcome"] == "done"
    outputs = result["outputs"]
    assert outputs["sources"] == [{
        "id": "docs", "type": "git", "status": "updated",
        "old_sha": corpus.first_sha[:7], "new_sha": corpus.upstream_head[:7], "files_changed": 3,
    }]
    assert outputs["index_changes"] == {"added": 1, "modified": 1, "removed": 1, "stale_entries": ["docs:a.md", "docs:d.md"]}
    assert outputs["embeddings"] == "skipped" and outputs["embeddings_lag"] is None and outputs["errors"] == []


async def test_refresh_script_does_what_its_outputs_say(corpus, run):
    """The `ok` script's calls are real: the index and the config of the fixture corpus are what the outputs report."""
    await run("refresh", {"sources": "all"})
    assert corpus.entry("docs:a.md")["stale"] is True
    assert corpus.entry("docs:d.md")["stale"] is True and corpus.entry("docs:d.md")["summary"] == "Pending re-scan"
    ids = [e["id"] for e in yaml.safe_load((corpus.path / "index.yaml").read_text())["entries"]]
    assert "docs:c.md" not in ids
    config = yaml.safe_load((corpus.path / "config.yaml").read_text())
    assert config["sources"][0]["last_commit_sha"] == corpus.upstream_head
    assert (corpus.path / ".source" / "docs" / "docs" / "d.md").is_file()
    index = yaml.safe_load((corpus.path / "index.yaml").read_text())
    assert index["meta"]["entry_count"] == len(index["entries"]) and index["meta"]["generated_at"].startswith(date.today().isoformat())
    rendered = (corpus.path / "index.md").read_text()   # rendered by the real render-index.sh
    assert "docs:d.md" in rendered and "docs:c.md" not in rendered


async def test_refresh_that_does_not_exit_fails(corpus, run):
    result = await run("refresh", {"sources": "all"}, case="refresh_no_exit")
    assert result["outcome"] == "failed" and result["reason"] == "no_exit"


async def test_refresh_procedure_is_filled_with_the_corpus_and_the_sources(corpus):
    text = await filled_procedure(corpus, "refresh", {"sources": "all"})
    assert f"Corpus: {corpus.path}." in text
    assert "Sources to update: all." in text
    assert "Sources to update: not given" not in text
    assert "{{" not in text


async def test_refresh_procedure_says_not_given_when_no_sources_are(corpus):
    text = await filled_procedure(corpus, "refresh", {})
    assert "Sources to update: not given." in text


def test_refresh_keeps_the_recipe_for_git_sources():
    """The steps for a git source keep the skill's constraints in its words (the task's git constraints)."""
    text = (ROOT / "skills" / "refresh" / "SKILL.md").read_text()
    assert "git clone --filter=blob:none --sparse --depth=50" in text and "/.source/" in text
    assert "sparse-checkout set <docs_root>" in text
    assert 0 < text.index("--shallow-since") < text.index("--unshallow")
    assert "git -C <clone> diff --name-status" in text
    assert "Never use the GitHub compare API" in text
    assert "the source's `type` is not `git`" in text and "is not handled by this instance yet" in text


def test_enrich_declares_its_contract(instance):
    node = instance.nodes["enrich"]
    assert set(node.inputs) == {"entries"}
    assert set(node.outputs) == {"concepts_assigned", "new_concept_candidates", "verification", "embeddings", "errors"}
    assert node.outputs["concepts_assigned"]["type"] == "integer"
    assert node.outputs["new_concept_candidates"]["items"]["required"] == ["label", "evidence"]
    assert node.outputs["verification"]["required"] == ["sampled", "failed", "drift_entries"]
    assert node.outputs["embeddings"]["enum"] == ["updated", "skipped", "no-model", "not-installed"]
    assert node.exits == ("done", "failed") and node.context == "none"
    assert node.allowed_tools == ("shell__run", "files__read_text_file", "files__edit_file", "files__write_file")


async def test_enrich_contract(corpus_stale, run):
    corpus_stale.set_concepts("docs:a.md", [])
    result = await run("enrich", {"entries": ["docs:a.md"]})
    assert result["outcome"] == "done"
    assert result["outputs"] == {
        "concepts_assigned": 1, "new_concept_candidates": [],
        "verification": {"sampled": 1, "failed": 0, "drift_entries": []}, "embeddings": "skipped", "errors": [],
    }


async def test_enrich_script_does_what_its_outputs_say(corpus_stale, run):
    """The `ok` script's calls are real: the concept is in the index, the metadata is saved, `index.md` is rendered."""
    corpus_stale.set_concepts("docs:a.md", [])
    await run("enrich", {"entries": ["docs:a.md"]})
    assert corpus_stale.entry("docs:a.md")["concepts"] == ["concept"]
    assert corpus_stale.entry("docs:b.md")["concepts"] == ["concept"]
    index = yaml.safe_load((corpus_stale.path / "index.yaml").read_text())
    assert index["meta"]["entry_count"] == len(index["entries"]) and index["meta"]["generated_at"].startswith(date.today().isoformat())
    rendered = (corpus_stale.path / "index.md").read_text()   # rendered by the real render-index.sh
    assert f"Generated: {date.today().isoformat()}" in rendered


async def test_enrich_procedure_is_filled_with_the_corpus_and_the_entries(corpus_stale):
    text = await filled_procedure(corpus_stale, "enrich", {"entries": ["docs:a.md", "docs:b.md"]})
    assert f"Corpus: {corpus_stale.path}." in text
    assert "docs:a.md" in text.partition("Entries:")[2].partition("\n")[0] and "docs:b.md" in text.partition("Entries:")[2].partition("\n")[0]
    assert "{{" not in text
    assert f"--index {corpus_stale.path}/index.yaml --source-root {corpus_stale.path}/.source/ --config {corpus_stale.path}/config.yaml" in text


def test_enrich_keeps_the_recipe_of_enrich_headless():
    """Phases 3 to 5 keep their constraints in the skill's words."""
    text = (ROOT / "skills" / "enrich" / "SKILL.md").read_text()
    assert "Do not write them to `graph.yaml`" in text and "at least two tag overlaps" in text
    assert "Take the first ten target entries" in text and "uv run scripts/verify_entries.py" in text
    assert "bash ./render-index.sh index.yaml" in text
    assert 0 < text.index("uv run scripts/detect.py") < text.index("uv run scripts/embed.py")
    assert "Never download the model" in text
    assert "LOAD" not in text and "CALL `load` with the path `reference/graph.md`" in text
