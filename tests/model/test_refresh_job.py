"""The refresh sequence with a model: `agent-core job ... refresh --backend langgraph` on corpora built in a temporary directory.

These tests carry the marker `model`: they call a model provider, cost money and do not run by default. They use the model in
`AGENT_CORE_LANGGRAPH_MODEL` (develop on `claude-haiku-5-5`; the pass bar is one pass on `claude-sonnet-5-5`) and need
`ANTHROPIC_API_KEY` in the environment of the shell that starts pytest:

    set -a && . <file holding the key> && set +a && AGENT_CORE_LANGGRAPH_MODEL=claude-haiku-5-5 uv run pytest tests/model -m model -q

Nothing leaves the machine. A corpus's upstream and its origin are local git repositories, `PUSH` is false except in the second
test (which pushes to the test's own bare origin), and `gh` is the stand-in of `tests/conftest.py`.

The directory of every run (`record.json`, with the steps, the facts and the cost of each node run, and what the command printed) is kept under
`runs/model-tests/<date>/<model>/<test>/`, which git ignores.
"""

import shutil
import subprocess

import pytest
import yaml

from tests.helpers import gh_calls

pytestmark = pytest.mark.model

PENDING = "Pending re-scan"   # what the refresh writes as the summary of an entry it adds, until a scan replaces it
FIRST_SUMMARY = "The file a.md."


def shown(corpus, ref: str, name: str) -> str:
    """A file of the corpus as the commit `ref` has it."""
    relative = corpus.path.relative_to(corpus.clone).as_posix()
    return corpus.git("show", f"{ref}:{name if relative == '.' else f'{relative}/{name}'}")


def indexed(corpus, ref: str | None = None) -> dict[str, dict]:
    """The entries of the corpus's `index.yaml` by id: on disk now, or as the commit `ref` has it."""
    text = (corpus.path / "index.yaml").read_text() if ref is None else shown(corpus, ref, "index.yaml")
    return {e["id"]: e for e in yaml.safe_load(text)["entries"]}


def assert_refreshed(corpus, ran, source: str, today: str) -> None:
    """What a refresh of a fixture corpus must have done. `source` is the id of its one source. `publish` commits on a new
    branch and returns to the base branch, so the refreshed files are read from the branch."""
    assert ran.code == 0 and ran.record.get("end_state") == "done", ran.why()
    assert ran.record["model_calls"] > 0, "the run made no model call"
    facts = ran.facts
    branch = ran.record["summary"]["branch"]

    # One commit, on a new branch, and the checkout back on main.
    assert branch and branch.startswith(f"{corpus.branch_prefix}-{today}"), ran.why()
    assert corpus.git("branch", "--show-current") == "main" and corpus.git("status", "--porcelain") == ""
    assert corpus.git("rev-list", "--count", f"main..{branch}") == "1"
    assert corpus.git("for-each-ref", "--format=%(refname:short)", "refs/heads/automated/").splitlines() == [branch]

    # The source is updated, at the upstream's head.
    [found] = [s for s in facts["sources"] if s["id"] == source]
    assert found["status"] == "updated" and len(found["new_sha"]) >= 7 and corpus.upstream_head.startswith(found["new_sha"]), found
    config = yaml.safe_load(shown(corpus, branch, "config.yaml"))
    assert config["sources"][0]["last_commit_sha"] == corpus.upstream_head

    # The index: a.md re-scanned, d.md added, c.md gone.
    entries = indexed(corpus, branch)
    a = entries[f"{source}:a.md"]
    assert a["stale"] is False and a["summary"].strip() and a["summary"] not in (FIRST_SUMMARY, PENDING), a
    assert f"{source}:d.md" in entries and f"{source}:c.md" not in entries, sorted(entries)
    assert not [id for id, e in entries.items() if e.get("stale")], "entries still stale"

    # index.md was rendered again, and the commit holds it.
    rendered = shown(corpus, branch, "index.md")
    assert f"{source}:d.md" in rendered and f"{source}:c.md" not in rendered

    # The facts and the commit message list what was updated and what was enriched (CRP-11).
    assert [s["status"] for s in facts["sources"]] == ["updated"]
    assert {f"{source}:a.md", f"{source}:d.md"} <= set(facts["enriched_ids"]), facts.get("enriched_ids")
    message = corpus.git("log", "-1", "--format=%B", branch)
    assert f"Updated: `{source}`" in message and f"{source}:a.md" in message and f"{source}:d.md" in message, message


def test_the_fixture_corpus_is_refreshed_and_a_lost_commit_fails_its_source(corpus, run_job, today):
    first = run_job(corpus)
    assert_refreshed(corpus, first, "docs", today)
    assert first.outcome("publish") == "committed" and first.record["summary"]["pr_url"] is None and gh_calls() == []

    # The upstream's history is rewritten as a force-push would: one new root commit with the same files, and the old
    # commits, the one the corpus tracks among them, unreachable. The working copy of the source the first run left in the
    # corpus (`.source/`, which git ignores) is removed: it holds that commit, as the machine of a scheduler that has never
    # run the job does not.
    def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(corpus.upstream), *args], check=check, capture_output=True, text=True)

    git("checkout", "-q", "--orphan", "rewritten")
    git("commit", "-q", "-m", "docs: history rewritten")
    git("branch", "-M", "main")
    git("reflog", "expire", "--expire=now", "--all")
    git("gc", "-q", "--prune=now")
    assert git("cat-file", "-e", corpus.first_sha, check=False).returncode != 0, "the tracked commit is still in the upstream"
    shutil.rmtree(corpus.path / ".source")

    second = run_job(corpus)   # from main, which the first run's branch never reached
    assert second.code == 0 and second.record.get("end_state") == "done", second.why()
    facts = second.facts
    [lost] = facts["sources"]
    assert lost["id"] == "docs" and lost["status"] == "failed" and lost.get("error"), lost
    assert facts["update_errors"], "the run did not say that the source failed"
    # Its entries stay as they were, and nothing is committed.
    assert second.outcome("publish") == "nothing-to-publish", second.why()
    assert corpus.git("branch", "--show-current") == "main" and corpus.git("status", "--porcelain") == ""
    entries = indexed(corpus)
    assert sorted(entries) == ["docs:a.md", "docs:b.md", "docs:c.md"] and not any(e["stale"] for e in entries.values())


def test_the_same_nodes_refresh_a_second_corpus_and_its_pull_request_goes_where_the_parameter_says(corpus_second, run_job, today):
    ran = run_job(corpus_second, CORPUS_REPO="someone/other", PUSH="true")
    assert_refreshed(corpus_second, ran, "guide", today)
    assert ran.outcome("publish") == "published", ran.why()
    summary = ran.record["summary"]
    calls = gh_calls()
    created = [call for call in calls if call[:2] == ["pr", "create"]]
    assert len(created) == 1 and summary["pr_url"] == "https://github.com/test/test/pull/1", calls
    assert all(call[call.index("--repo") + 1] == "someone/other" for call in calls), calls
    assert created[0][created[0].index("--head") + 1] == summary["branch"]
    assert corpus_second.git("ls-remote", "--heads", "origin", summary["branch"]) != "", "the branch was not pushed"
