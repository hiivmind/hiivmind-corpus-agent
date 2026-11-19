"""The `publish` node, run with the scripted backend over the fixture corpus.

These tests check what the scripted commands do to the repository, not what a model writes: the body a model writes is
checked by the model tests (`tests/model/`).
"""

import re
from datetime import date, timedelta

from tests.helpers import ROOT, gh_calls

INPUTS = (
    "sources", "index_changes", "removed_ids", "enriched_ids", "skipped_entries", "index_errors", "scans_failures",
    "concepts_assigned", "new_concept_candidates", "verification", "embeddings", "embeddings_lag",
    "update_errors", "concept_errors", "verify_errors", "embed_errors", "migrated", "migrate_skipped", "strategy",
)


def test_publish_declares_its_inputs_and_contract(instance):
    node = instance.nodes["publish"]
    assert set(node.contract.inputs) == set(INPUTS) and set(node.contract.outputs) == {"branch", "pr_url", "superseded_prs"}
    assert node.contract.exits == ("published", "committed", "nothing-to-publish", "failed")
    assert "files__edit_file" not in node.allowed_tools


async def test_publish_declares_its_inputs_as_optional(corpus, instructions):
    from tests.test_nodes import filled_procedure
    text = await filled_procedure(instructions, "publish", {})
    assert "not given" in text and "{{" not in text


async def test_publish_with_push_off_commits_and_returns_to_the_base_branch(corpus, run, today):
    corpus.write("index.yaml", corpus.path.joinpath("index.yaml").read_text() + "# refreshed\n")
    result = await run("publish", {})
    branch = f"automated/corpus-refresh-test-{today}"
    assert result["outcome"] == "committed" and result["outputs"] == {"branch": branch, "pr_url": None, "superseded_prs": []}
    assert corpus.git("branch", "--show-current") == "main" and corpus.git("status", "--porcelain") == ""
    assert corpus.git("show", "--name-only", "--format=%s", branch).split("\n") == [f"corpus: refresh {today}", "", "hiivmind-corpus-test/index.yaml"]
    assert corpus.git("ls-remote", "--heads", "origin", branch) == "" and gh_calls() == []   # nothing remote


async def test_publish_with_nothing_changed_is_nothing_to_publish(corpus, run, today):
    result = await run("publish", {}, case="publish_nothing")
    assert result["outcome"] == "nothing-to-publish"
    assert corpus.git("branch", "--list", f"automated/corpus-refresh-test-{today}*") == "" and corpus.git("branch", "--show-current") == "main"


async def test_publish_with_push_on_opens_the_pull_request_and_closes_the_superseded(corpus_pushing, run, today):
    old = f"automated/corpus-refresh-test-{(date.today() - timedelta(days=4)).isoformat()}"
    corpus_pushing.set_gh_open_prs([{"number": 12, "createdAt": "2026-11-12T02:00:00Z"}], branch=old)
    corpus_pushing.write("index.yaml", corpus_pushing.path.joinpath("index.yaml").read_text() + "# refreshed\n")
    result = await run("publish", {}, case="publish_push", OLD_BRANCH=old)
    branch = f"automated/corpus-refresh-test-{today}"
    assert result["outcome"] == "published"
    assert result["outputs"] == {"branch": branch, "pr_url": "https://github.com/test/test/pull/1", "superseded_prs": [12]}
    assert [c[:2] for c in gh_calls()] == [["pr", "list"], ["pr", "create"], ["pr", "close"]]
    create, close = gh_calls()[1], gh_calls()[2]
    assert create[2:8] == ["--repo", "test/test", "--base", "main", "--head", branch] and "--body-file" in create
    assert close[:5] == ["pr", "close", "12", "--repo", "test/test"] and "--delete-branch" in close
    assert corpus_pushing.git("ls-remote", "--heads", "origin", branch).split()[1] == f"refs/heads/{branch}"
    assert corpus_pushing.git("branch", "--show-current") == "main"


def test_publish_names_both_refusals_and_times_every_command():
    """The procedure is where the approved refusals live now (CRP-9), and every git and gh command has a time limit."""
    text = (ROOT / "nodes" / "publish.md").read_text()
    assert "staged outside" in text and "nothing was committed" in text
    assert "but CORPUS_REPO is" in text and "nothing was pushed" in text
    commands = re.findall(r"`([^`]*\b(?:git|gh) [^`]*)`", text)
    assert commands and all(re.search(r"(^|&& )timeout 120 (git|gh) ", c) for c in commands if re.match(r"(cd [^&]+&& )?(timeout 120 )?(git|gh) ", c)), commands
    assert not re.search(r"`(cd [^`&]+&& )?(git|gh) ", text)
    assert "50" in text   # at most 50 ids in a list


def test_publish_declares_the_migration_inputs(instance):
    node = instance.nodes["publish"]
    assert {"migrated", "migrate_skipped", "strategy"} <= set(node.contract.inputs)


async def test_publish_titles_from_the_facts(corpus, instructions):
    from tests.test_nodes import filled_procedure
    text = await filled_procedure(instructions, "publish", {})
    rules = ["`corpus: migrate <today>` when Migrated", "`corpus: refresh <today>` when Sources", "`corpus: enrich <today>`"]
    at = [text.find(rule) for rule in rules]
    assert -1 not in at and at == sorted(at), at
    assert '--title "<the title>"' in text and '--title "corpus: refresh' not in text
    assert "## Migration" in text and "Migrated: <migrated> entries (<strategy>)" in text
