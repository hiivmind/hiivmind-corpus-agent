"""The repository steps of a refresh: `repo_prepare` (the template's Phase 2) and `repo_finish` (Phase 4), with `repo_branch` between.

Every git command runs in `CORPUS_PATH`, which may be the repository's root or a directory inside it. Nothing here forces,
rewrites history, or touches a file outside `CORPUS_PATH`.
"""

import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

REMOTE = "origin"


class RepoError(RuntimeError):
    """A git or gh command failed or the repository is not ready. The message holds the command and what it said."""


def _run(command: list[str], cwd: Path, *, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except OSError as e:
        raise RepoError(f"{' '.join(command)}: cannot run: {e}") from None
    if done.returncode not in ok:
        why = " ".join((done.stderr or done.stdout).split()) or "no message"
        raise RepoError(f"{' '.join(command)} (in {cwd}) exited {done.returncode}: {why}")
    return done


def _git(settings, *args: str) -> str:
    return _run(["git", *args], Path(settings.CORPUS_PATH)).stdout.strip()


def _pull_requests(settings, branch: str) -> list[dict]:
    command = ["gh", "pr", "list", "--repo", settings.CORPUS_REPO, "--head", branch, "--state", "open", "--json", "number,createdAt"]
    out = _run(command, Path(settings.CORPUS_PATH)).stdout
    try:
        return json.loads(out)
    except ValueError as e:
        raise RepoError(f"{' '.join(command)} printed something that is not JSON: {e}") from None


def _age_days(created_at: str) -> int:
    created = datetime.fromisoformat(created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).days


def repo_prepare(settings) -> dict:
    """Stop on a dirty tree; else check out `BASE_BRANCH`, pull it, and list the earlier refresh branches and their open pull requests.

    Returns `main_advanced` (the pull moved `BASE_BRANCH`) and `stale_branches`: `branch`, `pr_number` and `pr_age_days`
    (both `None` when the branch has no open pull request), one per `origin/<BRANCH_PREFIX>*` branch.
    """
    dirty = _git(settings, "status", "--porcelain")
    if dirty:
        raise RepoError(f"the working tree is dirty: {'; '.join(line.strip() for line in dirty.splitlines())}")
    _git(settings, "checkout", settings.BASE_BRANCH)
    before = _git(settings, "rev-parse", "HEAD")
    _git(settings, "pull", "--ff-only", "--prune", REMOTE, settings.BASE_BRANCH)
    advanced = _git(settings, "rev-parse", "HEAD") != before

    listed = _git(settings, "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{REMOTE}").splitlines()
    stale = []
    for ref in sorted(listed):
        if not ref.startswith(f"{REMOTE}/{settings.BRANCH_PREFIX}"):
            continue
        branch = ref.removeprefix(f"{REMOTE}/")
        prs = _pull_requests(settings, branch)
        stale.append({
            "branch": branch,
            "pr_number": prs[0]["number"] if prs else None,
            "pr_age_days": _age_days(prs[0]["createdAt"]) if prs else None,
        })
    return {"main_advanced": advanced, "stale_branches": stale}


def repo_branch(settings) -> dict:
    """Create and check out `<BRANCH_PREFIX>-<today>`, with `-2`, `-3` ... when a local or `origin` branch has the name."""
    taken = set(_git(settings, "for-each-ref", "--format=%(refname:short)", "refs/heads", f"refs/remotes/{REMOTE}").splitlines())
    base = f"{settings.BRANCH_PREFIX}-{date.today().isoformat()}"
    branch, n = base, 1
    while branch in taken or f"{REMOTE}/{branch}" in taken:
        n += 1
        branch = f"{base}-{n}"
    _git(settings, "checkout", "-b", branch)
    return {"branch": branch}


def repo_finish(branch: str, title: str, body: str, stale_branches: list, settings) -> dict:
    """Commit what the refresh changed under `CORPUS_PATH`; with `PUSH`, push, open the pull request, then close the superseded ones.

    Without changes: back to `BASE_BRANCH`, `branch` deleted, `has_changes` false, other pull requests left open.
    Returns `has_changes`, `commit_sha`, `pr_url` (`None` unless a pull request was opened) and `superseded_prs`.
    """
    corpus = Path(settings.CORPUS_PATH)
    _git(settings, "add", "-A", "--", str(corpus))
    if _run(["git", "diff", "--cached", "--quiet"], corpus, ok=(0, 1)).returncode == 0:
        _git(settings, "checkout", settings.BASE_BRANCH)
        _git(settings, "branch", "-d", branch)
        return {"has_changes": False, "commit_sha": None, "pr_url": None, "superseded_prs": []}

    _git(settings, "commit", "-m", title, "-m", body)
    sha = _git(settings, "rev-parse", "HEAD")
    if not settings.PUSH:
        return {"has_changes": True, "commit_sha": sha, "pr_url": None, "superseded_prs": []}

    _git(settings, "push", "-u", REMOTE, branch)
    created = _run(
        ["gh", "pr", "create", "--repo", settings.CORPUS_REPO, "--base", settings.BASE_BRANCH, "--head", branch,
         "--title", title, "--body", body],
        corpus,
    )
    printed = created.stdout.split()
    if not printed:
        raise RepoError(f"gh pr create printed no pull request URL; the branch {branch} is pushed")
    url = printed[-1]
    superseded = []
    for stale in stale_branches:
        number = stale.get("pr_number")
        if number is None:
            continue
        _run(
            ["gh", "pr", "close", str(number), "--repo", settings.CORPUS_REPO, "--comment",
             f"Superseded by {url} (regenerated from current upstream).", "--delete-branch"],
            corpus,
        )
        superseded.append(number)
    return {"has_changes": True, "commit_sha": sha, "pr_url": url, "superseded_prs": superseded}
