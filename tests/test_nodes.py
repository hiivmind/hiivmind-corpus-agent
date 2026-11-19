"""The nodes of the instance, run with the scripted backend: each node's contract."""

import re
from datetime import datetime, timezone

import yaml
from tests.helpers import ROOT


async def filled_procedure(instructions, node: str, inputs: dict) -> str:
    """The procedure of a node as the model reads it for these inputs: the instructions after the line that names the node.

    (The rules before it carry examples such as "Sources to update: not given", so only this part says what the node was given.)
    """
    sent = await instructions(node, inputs)
    _, _, procedure = sent.partition(f"# Procedure of the node that is running: `{node}`")
    assert procedure, "the instructions have no procedure line"
    return procedure


def test_scan_declares_its_contract(instance):
    node = instance.nodes["scan"]
    assert set(node.contract.inputs) == {"batch"}
    assert node.output_schemas["entries"]["type"] == "array"
    assert node.output_schemas["entries"]["items"]["required"] == [
        "path", "title", "summary", "tags", "keywords", "category", "content_type", "size", "grep_hint", "headings",
    ]
    assert node.contract.exits == ("done", "failed") and node.context == "none"
    assert node.allowed_tools == ("files__read_text_file", "files__list_directory", "shell__run", "reference")


async def test_scan_contract(corpus_stale, run):
    assert (await run("scan", {"batch": {"source": "docs", "files": ["a.md"]}}))["outcome"] == "done"
    assert (await run("scan", {"batch": {"source": "docs", "files": ["a.md"]}}, case="scan_bad"))["reason"] == "invalid_output"   # an entry without summary, twice


async def test_scan_returns_the_entry_the_script_wrote_for_each_file(corpus_stale, run):
    result = await run("scan", {"batch": {"source": "docs", "files": ["a.md", "d.md"]}})
    entries = result["outputs"]["entries"]
    assert [e["path"] for e in entries] == ["a.md", "d.md"]
    assert all(e["content_type"] == "markdown" and e["size"] == "standard" for e in entries)


async def test_scan_sends_back_a_category_outside_the_enum(corpus_stale, run):
    result = await run("scan", {"batch": {"source": "docs", "files": ["a.md"]}}, case="scan_bad_category")   # wrong twice
    assert result["outcome"] == "failed" and result["reason"] == "invalid_output"
    assert any("category" in e and "essay" in e for e in result["errors"])


async def test_scan_takes_a_batch(corpus_stale, instructions):
    text = await filled_procedure(instructions, "scan", {"batch": {"source": "docs", "files": ["a.md", "b.md"]}})
    assert "'source': 'docs'" in text and "'files': ['a.md', 'b.md']" in text and "{{" not in text


# --- update-sources -----------------------------------------------------------------------------------------------------

def test_update_sources_declares_its_contract(instance):
    node = instance.nodes["update-sources"]
    assert set(node.contract.inputs) == {"sources"}
    assert set(node.contract.outputs) == {"sources", "index_changes", "removed_ids", "update_errors"}
    source = node.output_schemas["sources"]["items"]
    assert source["required"] == ["id", "type", "status", "old_sha", "new_sha", "files_changed"]
    assert source["properties"]["status"]["enum"] == ["current", "updated", "failed", "skipped-manual"]
    assert node.output_schemas["index_changes"]["required"] == ["added", "modified", "removed", "stale_entries"]
    assert node.contract.exits == ("updated", "current", "declined", "failed") and node.context == "none"


def test_update_sources_edits_no_yaml_by_text(instance):          # CRP-4
    tools = instance.nodes["update-sources"].allowed_tools
    assert "files__edit_file" not in tools and "files__write_file" not in tools
    assert {"source_freshness", "apply_source_update", "drop_missing", "reference"} <= set(tools)


async def test_update_sources_applies_a_change_through_the_tool(corpus, run):
    result = await run("update-sources", {"sources": "all"})
    assert result["outcome"] == "updated"
    assert result["outputs"] == {
        "sources": [{"id": "docs", "type": "git", "status": "updated", "old_sha": corpus.first_sha[:7], "new_sha": corpus.upstream_head[:7], "files_changed": 3}],
        "index_changes": {"added": 1, "modified": 1, "removed": 1, "stale_entries": ["docs:a.md", "docs:d.md"]},
        "removed_ids": ["docs:c.md"], "update_errors": [],
    }
    ids = [e["id"] for e in yaml.safe_load((corpus.path / "index.yaml").read_text())["entries"]]
    assert "docs:c.md" not in ids and corpus.entry("docs:a.md")["stale"] is True and corpus.entry("docs:d.md")["summary"] == "Pending re-scan"
    assert yaml.safe_load((corpus.path / "config.yaml").read_text())["sources"][0]["last_commit_sha"] == corpus.upstream_head
    rendered = (corpus.path / "index.md").read_text()   # rendered by the real render-index.sh
    assert "docs:d.md" in rendered and "docs:c.md" not in rendered


async def test_update_sources_procedure_is_filled_with_the_corpus_and_the_sources(corpus, instructions):
    text = await filled_procedure(instructions, "update-sources", {"sources": "all"})
    assert f"Corpus: {corpus.path}." in text and "Sources to update: all." in text and "{{" not in text
    assert f"cd {corpus.path} && bash ./render-index.sh index.yaml" in text   # the fragment, included and filled


async def test_update_sources_keeps_the_recipe_for_git_sources(corpus, instructions):
    """The steps for a git source keep the node's constraints in its words (the task's git constraints), the fragment's
    included."""
    text = await filled_procedure(instructions, "update-sources", {"sources": "all"})
    assert "git clone --filter=blob:none --sparse --depth=50" in text and "/.source/" in text
    assert "sparse-checkout set --skip-checks '<docs_root>'" in text   # atproto's docs_root is `src/app/[locale]`
    assert 0 < text.index("--shallow-since") < text.index("--unshallow")
    assert "Never use the GitHub compare API" in text
    assert "is not handled by this instance yet" in text


def test_update_sources_loops_over_sources_by_their_checkout_not_their_status():   # final review 1
    """A source is `updated` only after `apply_source_update` (step 14), so Phase 3's loop cannot take "updated" as done."""
    steps = {int(n): line for n, line in re.findall(r"(?m)^(\d+)\. (.*)$", (ROOT / "nodes" / "update-sources.md").read_text())}
    assert "checked out" in steps[11] and "updated" not in steps[11]
    assert "checked out" in steps[12] and "is now checked out" in (ROOT / "includes" / "sources" / "git.md").read_text()
    assert "checked out" in steps[13] and "updated" not in steps[13]


def test_a_node_that_fails_on_purpose_names_the_error_in_its_error_list():   # final review 2: `reason` is not a declared output
    for node, errors in (("index", "index_errors"), ("concepts", "concept_errors")):
        text = (ROOT / "nodes" / f"{node}.md").read_text()
        for line in text.splitlines():
            if "EXIT `failed`" in line and not line.startswith("|"):
                assert f"`{errors}`" in line, f"{node}: {line}"


# --- checkout-sources, status, migrate, graph-validate -------------------------------------------------------------------

def test_checkout_sources_declares_its_contract(instance):
    node = instance.nodes["checkout-sources"]
    assert set(node.contract.inputs) == set() and set(node.contract.outputs) == {"checkouts", "checkout_errors"}
    assert node.output_schemas["checkouts"]["items"]["required"] == ["id", "status"]
    assert node.output_schemas["checkouts"]["items"]["properties"]["status"]["enum"] == ["checked-out", "failed"]
    assert node.contract.exits == ("done", "failed") and node.context == "none"
    assert node.allowed_tools == ("shell__run", "files__read_text_file", "reference")


def test_status_declares_its_contract(instance):
    node = instance.nodes["status"]
    assert set(node.contract.inputs) == set()
    assert set(node.contract.outputs) == {"sources", "index_format", "stale_count", "embeddings_lag", "refresh_needed", "status_errors"}
    assert node.contract.exits == ("current", "stale", "failed") and node.allowed_tools == ("corpus_status",) and node.context == "none"


def test_migrate_declares_its_contract(instance):
    node = instance.nodes["migrate"]
    assert set(node.contract.inputs) == set()
    assert set(node.contract.outputs) == {"migrated", "migrate_skipped", "strategy", "sections", "migrate_errors"}
    assert node.contract.exits == ("migrated", "failed") and node.allowed_tools == ("migrate_index",) and node.context == "none"


def test_graph_validate_declares_its_contract(instance):
    node = instance.nodes["graph-validate"]
    assert set(node.contract.inputs) == set() and set(node.contract.outputs) == {"concepts", "relationships", "issues", "valid"}
    assert node.contract.exits == ("valid", "invalid", "failed") and node.allowed_tools == ("validate_graph",) and node.context == "none"


async def test_update_sources_and_checkout_sources_include_the_git_fragment(corpus, instructions):
    for node, inputs in (("update-sources", {"sources": "all"}), ("checkout-sources", {})):
        text = await filled_procedure(instructions, node, inputs)
        assert "git clone --filter=blob:none --sparse --depth=50" in text and "{{" not in text, node
        assert "checkout -q -B <branch> <commit>" in text and "--unshallow" in text, node


async def test_checkout_sources_checks_out_the_indexed_commit(corpus, run):
    result = await run("checkout-sources", {})
    assert result["outcome"] == "done" and result["outputs"]["checkouts"] == [{"id": "docs", "status": "checked-out"}]
    assert corpus.git("-C", str(corpus.path / ".source" / "docs"), "rev-parse", "HEAD") == corpus.first_sha


async def test_checkout_sources_checks_out_a_short_sha(corpus, run):                     # Review Focus 4: htmx's 749d5f2
    corpus.set_last_sha(corpus.first_sha[:7])
    assert (await run("checkout-sources", {}))["outcome"] == "done"
    assert corpus.git("-C", str(corpus.path / ".source" / "docs"), "rev-parse", "HEAD") == corpus.first_sha


async def test_status_exits_stale_with_the_outputs_the_tool_recorded(corpus, run):      # CJW-7
    result = await run("status", {})
    assert result["outcome"] == "stale"
    outputs = result["outputs"]
    assert outputs["refresh_needed"] is True and outputs["sources"] == [{"id": "docs", "type": "git", "freshness": "behind"}]
    assert outputs["stale_count"] == 0 and outputs["index_format"] == "v2" and outputs["status_errors"] == []


async def test_migrate_node_records_the_migration(corpus_v1_bullets, run):              # example 7e
    result = await run("migrate", {})
    assert result["outcome"] == "migrated"
    assert result["outputs"] == {"migrated": 2, "migrate_skipped": [], "strategy": "single", "sections": []}


async def test_migrate_node_reports_a_refusal(corpus_v1_bullets, run):                  # example 7
    corpus_v1_bullets.write("sections/extra.md", "See `docs:c.md`.\n")
    corpus_v1_bullets._save("test: an id the parser does not read")
    result = await run("migrate", {}, case="migrate_lost")
    assert result["outcome"] == "failed" and result["outputs"] == {"migrate_errors": ["ids lost in migration: docs:c.md"]}
    assert corpus_v1_bullets.git("status", "--porcelain") == ""


async def test_graph_validate_records_the_issues(corpus, run):
    corpus.write("graph.yaml", (corpus.path / "graph.yaml").read_text().replace("concepts:\n", 'concepts:\n  lonely:\n    label: "Lonely"\n    description: "Named by no entry"\n'))
    result = await run("graph-validate", {})
    assert result["outcome"] == "valid" and result["outputs"]["valid"] is True
    assert [(i["rule"], i["severity"]) for i in result["outputs"]["issues"]] == [("orphan-concept", "warning")]


# --- index ------------------------------------------------------------------------------------------------------------

def test_index_declares_its_contract(instance):
    node = instance.nodes["index"]
    assert set(node.contract.inputs) == {"scans", "scans_failures"}
    assert set(node.contract.outputs) == {"enriched_ids", "skipped_entries", "index_errors"}
    assert node.contract.exits == ("done", "failed") and node.allowed_tools == ("merge_scans", "shell__run")


async def test_index_merges_through_merge_scans_and_renders(corpus, run):
    await run("update-sources", {"sources": "all"})   # a.md and d.md stale
    scanned = (await run("scan", {"batch": {"source": "docs", "files": ["a.md", "d.md"]}}))["outputs"]
    result = await run("index", {"scans": [scanned], "scans_failures": []})
    assert result["outcome"] == "done" and result["outputs"]["enriched_ids"] == ["docs:a.md", "docs:d.md"]
    a = corpus.entry("docs:a.md")
    assert a["stale"] is False and a["summary"] == "The file a.md, changed in the second commit."
    assert "The file d.md, added in the second commit." in (corpus.path / "index.md").read_text()


async def test_the_index_procedure_shows_the_model_no_scan(corpus, instructions):
    text = await filled_procedure(instructions, "index", {"scans": [{"entries": [{"path": "secret-path.md"}]}], "scans_failures": []})
    assert "secret-path.md" not in text   # CRP-5: the scans reach merge_scans as facts only


# --- concepts, verify, embed -------------------------------------------------------------------------------------------

def test_concepts_declares_its_contract(instance):
    node = instance.nodes["concepts"]
    assert set(node.contract.inputs) == {"enriched_ids"}
    assert set(node.contract.outputs) == {"concepts_assigned", "new_concept_candidates", "concept_errors"}
    assert node.output_schemas["new_concept_candidates"]["items"]["required"] == ["label", "evidence"]
    assert node.contract.exits == ("done", "failed") and "files__edit_file" not in node.allowed_tools and "set_concepts" in node.allowed_tools


async def test_concepts_writes_through_set_concepts(corpus_stale, run):
    corpus_stale.set_concepts("docs:a.md", [])
    result = await run("concepts", {"enriched_ids": ["docs:a.md"]})
    assert result["outcome"] == "done" and result["outputs"]["concepts_assigned"] == 1
    assert corpus_stale.entry("docs:a.md")["concepts"] == ["concept"]
    utc_today = datetime.now(timezone.utc).date().isoformat()   # the tools stamp `meta` in UTC
    assert yaml.safe_load((corpus_stale.path / "index.yaml").read_text())["meta"]["generated_at"].startswith(utc_today)


def test_concepts_keeps_the_matching_rules():
    text = (ROOT / "nodes" / "concepts.md").read_text()
    assert "Do not write them to `graph.yaml`" in text and "at least two tag overlaps" in text
    assert "directory groups, one for each directory" in text and "directory `.`" in text


def test_verify_declares_its_contract(instance):
    node = instance.nodes["verify"]
    assert set(node.contract.inputs) == {"enriched_ids"} and set(node.contract.outputs) == {"verification", "verify_errors"}
    assert node.output_schemas["verification"]["required"] == ["sampled", "failed", "drift_entries"]
    assert node.contract.exits == ("done", "failed") and {"verify_previews", "set_summary"} <= set(node.allowed_tools)


async def test_verify_replaces_a_drifting_summary_through_set_summary(corpus_stale, run):
    result = await run("verify", {"enriched_ids": ["docs:a.md"]})
    assert result["outcome"] == "done" and result["outputs"]["verification"] == {"sampled": 1, "failed": 1, "drift_entries": ["docs:a.md"]}
    assert corpus_stale.entry("docs:a.md")["summary"] == "The file a.md, as it reads now: changed."
    assert "The file a.md, as it reads now: changed." in (corpus_stale.path / "index.md").read_text()


def test_verify_keeps_the_sample_of_ten():
    assert "Take the first ten target entries" in (ROOT / "nodes" / "verify.md").read_text()


def test_embed_declares_its_contract(instance):
    node = instance.nodes["embed"]
    assert set(node.contract.inputs) == set() and set(node.contract.outputs) == {"embeddings", "embeddings_lag", "embed_errors"}
    assert node.output_schemas["embeddings"]["enum"] == ["updated", "skipped", "no-model", "not-installed", "deferred"]
    assert node.contract.exits == ("done", "deferred", "failed")
    assert {"embeddings_status", "stale_entries", "embed", "embeddings_lag"} <= set(node.allowed_tools)


async def test_embed_with_no_lance_directory_is_skipped(corpus, run):
    result = await run("embed", {})
    assert result["outcome"] == "done" and result["outputs"] == {"embeddings": "skipped", "embeddings_lag": None, "embed_errors": []}


async def test_embed_defers_while_entries_are_stale(corpus_stale, run):
    (corpus_stale.path / "index-embeddings.lance").mkdir()
    result = await run("embed", {}, case="embed_deferred")
    assert result["outcome"] == "deferred" and result["outputs"]["embeddings"] == "deferred"


def test_embed_with_an_unexpected_detect_output_is_skipped_and_says_so():   # design review A8
    text = (ROOT / "nodes" / "embed.md").read_text()
    assert "anything else, or nothing" in text and "`detect.py printed <output>`" in text and "Never download the model" in text
    assert text.index("`stale_entries`") < text.index("CALL `embed`")   # stale entries are never embedded


# --- every node -------------------------------------------------------------------------------------------------------

def test_no_node_loads_a_reference_file():
    for node in sorted((ROOT / "nodes").glob("*.md")):
        text = node.read_text()
        assert "reference/" not in text and "scripts/" not in text and "CALL `load`" not in text, node
