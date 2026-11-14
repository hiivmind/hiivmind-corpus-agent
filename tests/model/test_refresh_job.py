"""The refresh job with a model: `agent-core job ... --backend langgraph` on corpora built in a temporary directory.

These tests carry the marker `model`: they call a model provider, cost money and do not run by default. They use the model in
`AGENT_CORE_LANGGRAPH_MODEL` (develop on `claude-haiku-5-5`; the pass bar is one pass on `claude-sonnet-5-5`) and need
`ANTHROPIC_API_KEY` in the environment of the shell that starts pytest:

    set -a && . <file holding the key> && set +a && AGENT_CORE_LANGGRAPH_MODEL=claude-haiku-5-5 uv run pytest tests/model -m model -q

Nothing leaves the machine. A corpus's upstream and its origin are local git repositories, `PUSH` is false except in the second
test (which pushes to the test's own bare origin), and `gh` is the stand-in of `tests/conftest.py`.

The directory of every job run (`record.json`, with the cost of each node run, and what the command printed) is kept under
`runs/model-tests/<date>/<model>/<test>/`, which git ignores.
"""

import itertools
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
import yaml

from tests.helpers import ROOT, gh_calls

pytestmark = pytest.mark.model

MODEL = os.environ.get("AGENT_CORE_LANGGRAPH_MODEL", "claude-sonnet-5-5")
PENDING = "Pending re-scan"   # what the refresh writes as the summary of an entry it adds, until a scan replaces it
FIRST_SUMMARY = "The file a.md."


@dataclass
class Ran:
    """One run of the command: its exit code, what it printed, and its run directory."""

    code: int
    out: str
    err: str
    dir: Path

    @property
    def record(self) -> dict:
        file = self.dir / "record.json"
        return json.loads(file.read_text()) if file.exists() else {}

    @property
    def summary(self) -> dict:
        summary = self.record.get("summary")
        return summary if isinstance(summary, dict) else {}

    def why(self) -> str:
        """What to show when an assertion about this run fails."""
        record = self.record
        return (
            f"exit code {self.code}; status {record.get('status')}; summary {record.get('summary')}\n"
            f"failures {json.dumps(record.get('failures'), indent=1)}\nstdout: {self.out[-2000:]}\nstderr: {self.err[-2000:]}\n"
            f"run directory: {self.dir}"
        )


@pytest.fixture
def run_job(request):
    """`run_job(corpus, **params)`: `agent-core job instance.yaml refresh` with the corpus's settings file and the LangGraph
    backend, once, in a subprocess whose `PATH` starts with the stand-in `gh`; each `--param` as `KEY=value`."""
    name = re.sub(r"[^\w.-]", "_", request.node.name)
    where = ROOT / "runs" / "model-tests" / date.today().isoformat() / MODEL / name
    shutil.rmtree(where, ignore_errors=True)
    runs = itertools.count(1)

    def run_job(corpus, **params: str) -> Ran:
        run_dir = where / f"run-{next(runs)}"
        run_dir.mkdir(parents=True)
        command = [
            sys.executable, "-m", "agent_core.core.cli", "job", str(ROOT / "instance.yaml"), "refresh",
            "--settings", str(corpus.settings_file), "--backend", "langgraph", "--run-dir", str(run_dir),
        ]
        for key, value in params.items():
            command += ["--param", f"{key}={value}"]
        done = subprocess.run(
            command, cwd=ROOT, env={**os.environ, **corpus.environment()}, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=1800,
        )
        (run_dir / "stdout.txt").write_text(done.stdout)
        (run_dir / "stderr.txt").write_text(done.stderr)
        return Ran(done.returncode, done.stdout, done.stderr, run_dir)

    return run_job


def indexed(corpus) -> dict[str, dict]:
    """The entries of the corpus's `index.yaml` as it is on disk now, by id."""
    return {e["id"]: e for e in yaml.safe_load((corpus.path / "index.yaml").read_text())["entries"]}


def assert_refreshed(corpus, ran: Ran, source: str, today: str) -> None:
    """What a refresh of a fixture corpus must have done (Task 10, step 1). `source` is the id of its one source."""
    assert ran.code == 0 and ran.record.get("status") == "ok", ran.why()
    assert ran.record["model_calls"] > 0, "the job made no model call"
    summary = ran.summary

    # The source is updated, at the upstream's head.
    [found] = [s for s in summary["sources"] if s["id"] == source]
    assert found["status"] == "updated" and len(found["new_sha"]) >= 7 and corpus.upstream_head.startswith(found["new_sha"]), found
    config = yaml.safe_load((corpus.path / "config.yaml").read_text())
    assert config["sources"][0]["last_commit_sha"] == corpus.upstream_head

    # The index: a.md re-scanned, d.md added, c.md gone.
    entries = indexed(corpus)
    a = entries[f"{source}:a.md"]
    assert a["stale"] is False and a["summary"].strip() and a["summary"] not in (FIRST_SUMMARY, PENDING), a
    assert f"{source}:d.md" in entries and f"{source}:c.md" not in entries, sorted(entries)

    # index.md was rendered again, and the commit holds it.
    rendered = (corpus.path / "index.md").read_text()
    assert f"{source}:d.md" in rendered and f"{source}:c.md" not in rendered
    relative = corpus.path.relative_to(corpus.clone)
    assert f"{relative}/index.md" in corpus.git("diff", "--name-only", "main", "HEAD").splitlines()

    # One commit, on a new branch.
    branch = corpus.git("branch", "--show-current")
    assert branch == summary["branch"] and branch.startswith(f"{corpus.branch_prefix}-{today}"), branch
    assert corpus.git("rev-list", "--count", "main..HEAD") == "1"
    assert corpus.git("for-each-ref", "--format=%(refname:short)", "refs/heads/automated/").splitlines() == [branch]

    # The run record lists what was updated and what was enriched.
    assert [s["status"] for s in summary["sources"]] == ["updated"]
    assert {f"{source}:a.md", f"{source}:d.md"} <= set(summary["enriched_ids"]) and summary["enriched"] == len(summary["enriched_ids"])
    assert summary["needs_attention"] == [], summary["needs_attention"]


def test_the_fixture_corpus_is_refreshed_and_a_lost_commit_fails_its_source(corpus, run_job, today):
    first = run_job(corpus)
    assert_refreshed(corpus, first, "docs", today)
    assert first.summary["pr_url"] is None and not [c for c in gh_calls() if c[:2] == ["pr", "create"]]

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

    second = run_job(corpus)
    assert second.code == 0 and second.record.get("status") == "ok", second.why()
    summary = second.summary
    [lost] = summary["sources"]
    assert lost["id"] == "docs" and lost["status"] == "failed" and lost.get("error"), lost
    assert summary["errors"], "the job did not say that the source failed"
    # Its entries stay as they were, and nothing is committed.
    assert summary["status"] == "no changes", summary
    assert corpus.git("branch", "--show-current") == "main" and corpus.git("status", "--porcelain") == ""
    entries = indexed(corpus)
    assert sorted(entries) == ["docs:a.md", "docs:b.md", "docs:c.md"] and not any(e["stale"] for e in entries.values())


def test_the_same_nodes_refresh_a_second_corpus_and_its_pull_request_goes_where_the_parameter_says(corpus_second, run_job, today):
    ran = run_job(corpus_second, CORPUS_REPO="someone/other", PUSH="true")
    assert_refreshed(corpus_second, ran, "guide", today)
    summary = ran.summary
    calls = gh_calls()
    created = [call for call in calls if call[:2] == ["pr", "create"]]
    assert len(created) == 1 and summary["pr_url"] == "https://github.com/test/test/pull/1", calls
    assert all(call[call.index("--repo") + 1] == "someone/other" for call in calls), calls
    assert created[0][created[0].index("--head") + 1] == summary["branch"]
    assert corpus_second.git("ls-remote", "--heads", "origin", summary["branch"]) != "", "the branch was not pushed"
