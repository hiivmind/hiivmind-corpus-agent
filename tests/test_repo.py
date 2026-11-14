"""The repository steps: the template's Phase 2 (prepare) and Phase 4 (finish), as code. Every git command runs in the fixture clone."""

import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

from tests.helpers import gh_calls
from tools.repo import RepoError, repo_branch, repo_finish, repo_prepare


def test_a_dirty_tree_stops_before_anything_changes(corpus):                       # Review Focus 1
    corpus.write("stray.txt", "x")
    with pytest.raises(RepoError, match="dirty"):
        repo_prepare(corpus.settings)
    assert corpus.git("branch", "--show-current") == "main"


def test_a_clean_tree_on_a_feature_branch_returns_to_the_base_branch(corpus):
    corpus.git("checkout", "-b", "elsewhere")
    result = repo_prepare(corpus.settings)
    assert result == {"main_advanced": False, "stale_branches": []}
    assert corpus.git("branch", "--show-current") == "main" and gh_calls() == []


def test_prepare_reports_whether_main_advanced(corpus):
    other = corpus.next_dir("other")
    corpus.git("clone", "-q", str(corpus.origin), str(other))
    corpus.git("-C", str(other), "config", "user.name", "Test")
    corpus.git("-C", str(other), "config", "user.email", "test@example.com")
    (other / "new.txt").write_text("x")
    corpus.git("-C", str(other), "add", "new.txt")
    corpus.git("-C", str(other), "commit", "-q", "-m", "elsewhere")
    corpus.git("-C", str(other), "push", "-q", "origin", "main")
    assert repo_prepare(corpus.settings)["main_advanced"] is True
    assert repo_prepare(corpus.settings)["main_advanced"] is False


def test_prepare_lists_the_stale_branches_with_their_open_pull_requests(corpus):
    created = datetime.now(timezone.utc) - timedelta(days=4)
    corpus.set_gh_open_prs([{"number": 12, "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ")}])
    branch = f"automated/corpus-refresh-test-{(date.today() - timedelta(days=4)).isoformat()}"
    result = repo_prepare(corpus.settings)
    assert result["stale_branches"] == [{"branch": branch, "pr_number": 12, "pr_age_days": 4}]
    assert gh_calls() == [["pr", "list", "--repo", "test/test", "--head", branch, "--state", "open", "--json", "number,createdAt"]]


def _push_branch(corpus, name: str, *, with_commit: bool) -> None:
    """Give origin a branch `name`, from a second clone of origin, with a commit of its own or at main's head."""
    other = corpus.next_dir("other")
    subprocess.run(["git", "clone", "-q", str(corpus.origin), str(other)], check=True)
    for key, value in (("user.name", "Test"), ("user.email", "test@example.com"), ("commit.gpgsign", "false")):
        subprocess.run(["git", "-C", str(other), "config", key, value], check=True)
    subprocess.run(["git", "-C", str(other), "checkout", "-q", "-b", name], check=True)
    if with_commit:
        (other / "work.txt").write_text("work\n")
        subprocess.run(["git", "-C", str(other), "add", "work.txt"], check=True)
        subprocess.run(["git", "-C", str(other), "commit", "-q", "-m", "work"], check=True)
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", name], check=True)


def test_a_branch_with_commits_and_no_open_pull_request_is_listed_with_none(corpus, today):
    branch = f"automated/corpus-refresh-test-{today}-2"
    _push_branch(corpus, branch, with_commit=True)
    assert repo_prepare(corpus.settings)["stale_branches"] == [{"branch": branch, "pr_number": None, "pr_age_days": None}]


def test_a_branch_equal_to_main_with_no_open_pull_request_is_not_listed(corpus):
    corpus.set_gh_open_prs([])      # a branch of origin at main's head, and `gh pr list` printing nothing
    assert repo_prepare(corpus.settings)["stale_branches"] == []


def test_a_branch_a_second_clone_pushed_is_found(corpus, today):
    branch = f"automated/corpus-refresh-test-{today}-2"
    assert corpus.git("branch", "-r", "--list", f"origin/{branch}") == ""      # this clone has never heard of it
    _push_branch(corpus, branch, with_commit=True)
    assert [b["branch"] for b in repo_prepare(corpus.settings)["stale_branches"]] == [branch]


def test_a_branch_deleted_on_origin_is_not_listed(corpus, today):
    branch = f"automated/corpus-refresh-test-{today}-2"
    _push_branch(corpus, branch, with_commit=True)
    corpus.git("fetch", "-q", "origin")
    assert branch in corpus.git("branch", "-r")                                 # this clone knows it
    subprocess.run(["git", "-C", str(corpus.origin), "branch", "-D", branch], check=True, capture_output=True)
    assert repo_prepare(corpus.settings)["stale_branches"] == []


def test_a_longer_prefix_is_another_prefix(corpus, today):
    mine, other = f"automated/corpus-refresh-test-{today}-2", f"automated/corpus-refresh-testing-{today}"
    _push_branch(corpus, mine, with_commit=True)
    _push_branch(corpus, other, with_commit=True)
    assert [b["branch"] for b in repo_prepare(corpus.settings)["stale_branches"]] == [mine]


def test_a_second_branch_on_one_day_gets_a_suffix(corpus, today):                  # Review Focus 3
    assert repo_branch(corpus.settings)["branch"] == f"automated/corpus-refresh-test-{today}"
    assert corpus.git("branch", "--show-current") == f"automated/corpus-refresh-test-{today}"
    corpus.git("checkout", "main")
    assert repo_branch(corpus.settings)["branch"] == f"automated/corpus-refresh-test-{today}-2"
    corpus.git("checkout", "main")
    assert repo_branch(corpus.settings)["branch"] == f"automated/corpus-refresh-test-{today}-3"


def test_a_branch_name_taken_on_origin_is_not_reused(corpus, today):
    corpus.git("push", "-q", "origin", f"HEAD:refs/heads/automated/corpus-refresh-test-{today}")
    corpus.git("fetch", "-q", "origin")
    assert repo_branch(corpus.settings)["branch"] == f"automated/corpus-refresh-test-{today}-2"


def test_with_push_off_it_commits_and_stops(corpus):
    b = repo_branch(corpus.settings)["branch"]; corpus.write("index.yaml", "changed: true\n")
    r = repo_finish(b, "corpus: refresh", "body", [], corpus.settings)
    assert r["has_changes"] and r["commit_sha"] and r["pr_url"] is None and gh_calls() == []
    assert corpus.git("rev-parse", "HEAD") == r["commit_sha"]
    assert corpus.git("log", "-1", "--format=%s%n%b").split("\n")[:2] == ["corpus: refresh", "body"]
    assert b not in corpus.git("branch", "-r", "--list", f"origin/{b}")


def test_with_push_on_it_opens_the_pull_request_then_closes_the_superseded_ones(corpus_pushing):
    b = repo_branch(corpus_pushing.settings)["branch"]; corpus_pushing.write("index.yaml", "changed: true\n")
    old_branch = f"automated/corpus-refresh-test-{(date.today() - timedelta(days=13)).isoformat()}"
    r = repo_finish(b, "corpus: refresh", "body", [{"branch": old_branch, "pr_number": 12, "pr_age_days": 13}], corpus_pushing.settings)
    assert [c[:2] for c in gh_calls()] == [["pr", "create"], ["pr", "close"]] and r["superseded_prs"] == [12] and r["pr_url"].startswith("https://")
    create, close = gh_calls()
    assert ["--repo", "test/test", "--base", "main", "--head", b] == create[2:8] and "corpus: refresh" in create and "body" in create
    assert close[:5] == ["pr", "close", "12", "--repo", "test/test"] and "--delete-branch" in close
    assert any(f"Superseded by {r['pr_url']}" in part for part in close)
    assert corpus_pushing.git("ls-remote", "--heads", "origin", b).split()[1] == f"refs/heads/{b}"


def test_a_stale_branch_without_a_pull_request_is_not_closed(corpus_pushing):
    b = repo_branch(corpus_pushing.settings)["branch"]; corpus_pushing.write("index.yaml", "changed: true\n")
    r = repo_finish(b, "corpus: refresh", "body", [{"branch": "x", "pr_number": None, "pr_age_days": None}], corpus_pushing.settings)
    assert [c[:2] for c in gh_calls()] == [["pr", "create"]] and r["superseded_prs"] == []


def test_only_the_corpus_directory_is_committed(corpus):
    b = repo_branch(corpus.settings)["branch"]; corpus.write("index.yaml", "changed: true\n"); corpus.write("../hiivmind-corpus-other/stray.txt", "x")
    repo_finish(b, "corpus: refresh", "body", [], corpus.settings)
    assert corpus.git("show", "--name-only", "--format=", "HEAD").split() == ["hiivmind-corpus-test/index.yaml"]


def test_a_corpus_at_the_repository_root_works_the_same(corpus_at_root):
    repo_prepare(corpus_at_root.settings); b = repo_branch(corpus_at_root.settings)["branch"]; corpus_at_root.write("index.yaml", "changed: true\n")
    assert repo_finish(b, "corpus: refresh", "body", [], corpus_at_root.settings)["has_changes"]
    assert corpus_at_root.git("show", "--name-only", "--format=", "HEAD").split() == ["index.yaml"]


def test_no_changes_means_no_commit_no_pull_request_and_no_branch(corpus_pushing):
    b = repo_branch(corpus_pushing.settings)["branch"]
    r = repo_finish(b, "corpus: refresh", "body", [{"branch": "x", "pr_number": 12, "pr_age_days": 3}], corpus_pushing.settings)
    assert r == {"has_changes": False, "commit_sha": None, "pr_url": None, "superseded_prs": []} and gh_calls() == []
    assert corpus_pushing.git("branch", "--show-current") == "main" and b not in corpus_pushing.git("branch", "--list")


def test_a_failed_push_names_the_command_and_leaves_the_branch(corpus_pushing):    # Review Focus 4
    corpus_pushing.break_origin()
    b = repo_branch(corpus_pushing.settings)["branch"]; corpus_pushing.write("index.yaml", "changed: true\n")
    with pytest.raises(RepoError, match="git push"):
        repo_finish(b, "corpus: refresh", "body", [], corpus_pushing.settings)
    assert b in corpus_pushing.git("branch", "--list") and gh_calls() == []


def test_a_failed_close_names_the_pull_requests_already_closed(corpus_pushing, monkeypatch):
    gh = corpus_pushing.bin / "gh"
    refuser = corpus_pushing.next_dir("refusing-bin")
    refuser.mkdir()
    (refuser / "gh").write_text(
        f"#!{sys.executable}\nimport subprocess, sys\n"
        f"if sys.argv[1:3] == ['pr', 'close'] and sys.argv[3] == '13':\n    sys.exit('cannot close 13')\n"
        f"sys.exit(subprocess.run(['{gh}', *sys.argv[1:]]).returncode)\n"
    )
    (refuser / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{refuser}{os.pathsep}{os.environ['PATH']}")
    b = repo_branch(corpus_pushing.settings)["branch"]; corpus_pushing.write("index.yaml", "changed: true\n")
    stale = [{"branch": "x", "pr_number": n, "pr_age_days": 1} for n in (12, 13, 14)]
    with pytest.raises(RepoError, match=r"gh pr close 13.*already closed: \[12\]") as e:
        repo_finish(b, "corpus: refresh", "body", stale, corpus_pushing.settings)
    assert "https://github.com/test/test/pull/1" in str(e.value)
    assert [c[2] for c in gh_calls() if c[:2] == ["pr", "close"]] == ["12"]
