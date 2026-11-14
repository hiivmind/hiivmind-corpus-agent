"""The repository steps of a refresh: `repo_prepare` (the template's Phase 2) and `repo_finish` (Phase 4), with `repo_branch` between.

Every git command runs in `CORPUS_PATH`, which may be the repository's root or a directory inside it. Nothing here forces,
rewrites history, or touches a file outside `CORPUS_PATH`.
"""

import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

REMOTE = "origin"
TIMEOUT = 300   # seconds for one git or gh command
BRANCH_SUFFIX = re.compile(r"\d{4}-\d{2}-\d{2}(-\d+)?")   # what `repo_branch` appends to the prefix
GITHUB_URL = re.compile(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/*$", re.IGNORECASE)


class RepoError(RuntimeError):
    """A git or gh command failed or the repository is not ready. The message holds the command and what it said."""


def _run(command: list[str], cwd: Path, *, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RepoError(f"{' '.join(command)} (in {cwd}) did not finish in {TIMEOUT} s") from None
    except OSError as e:
        raise RepoError(f"{' '.join(command)}: cannot run: {e}") from None
    if done.returncode not in ok:
        why = " ".join((done.stderr or done.stdout).split()) or "no message"
        raise RepoError(f"{' '.join(command)} (in {cwd}) exited {done.returncode}: {why}")
    return done


def _git(settings, *args: str) -> str:
    return _run(["git", *args], Path(settings.CORPUS_PATH)).stdout.strip()


def _github_name(url: str) -> str | None:
    """`owner/name` of a GitHub remote URL (https, ssh or scp-like), else `None`: a path or another host."""
    found = GITHUB_URL.search(url.strip())
    return f"{found.group(1)}/{found.group(2)}" if found else None


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
    """Stop on a dirty tree; else check out `BASE_BRANCH`, fetch `origin` and fast-forward, and list the earlier refresh branches.

    Returns `main_advanced` (the pull moved `BASE_BRANCH`) and `stale_branches`: `branch`, `pr_number` and `pr_age_days`
    (both `None` when the branch has no open pull request): each `origin/<BRANCH_PREFIX>-*` branch with an open pull
    request, or with commits that `BASE_BRANCH` does not have.
    """
    dirty = _git(settings, "status", "--porcelain")
    if dirty:
        raise RepoError(f"the working tree is dirty: {'; '.join(line.strip() for line in dirty.splitlines())}")
    _git(settings, "checkout", settings.BASE_BRANCH)
    before = _git(settings, "rev-parse", "HEAD")
    _git(settings, "fetch", "--prune", REMOTE)   # every branch of origin, so that none is missed and deleted ones go
    _git(settings, "merge", "--ff-only", f"{REMOTE}/{settings.BASE_BRANCH}")
    ahead = int(_git(settings, "rev-list", "--count", f"{REMOTE}/{settings.BASE_BRANCH}..HEAD"))
    if ahead > 0:   # an ff-only merge says nothing when the local branch is ahead, and the pull request would carry these
        raise RepoError(f"{settings.BASE_BRANCH} has {ahead} commit(s) that {REMOTE}/{settings.BASE_BRANCH} does not have")
    advanced = _git(settings, "rev-parse", "HEAD") != before

    listed = _git(settings, "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{REMOTE}").splitlines()
    stale = []
    for ref in sorted(listed):
        prefix = f"{REMOTE}/{settings.BRANCH_PREFIX}-"
        if not ref.startswith(prefix) or not BRANCH_SUFFIX.fullmatch(ref.removeprefix(prefix)):   # not `...-testing-`, not `...-test-cloud-`
            continue
        branch = ref.removeprefix(f"{REMOTE}/")
        prs = _pull_requests(settings, branch)
        if prs:
            stale.append({"branch": branch, "pr_number": prs[0]["number"], "pr_age_days": _age_days(prs[0]["createdAt"])})
        elif int(_git(settings, "rev-list", "--count", f"{settings.BASE_BRANCH}..{ref}")) > 0:   # work no one has seen
            stale.append({"branch": branch, "pr_number": None, "pr_age_days": None})
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
    if settings.PUSH:   # the pull request goes to CORPUS_REPO: the branch must be pushed there
        origin = _github_name(_git(settings, "remote", "get-url", "--push", REMOTE))
        if origin is not None and origin.lower() != settings.CORPUS_REPO.lower():
            raise RepoError(f"{REMOTE} is {origin} but CORPUS_REPO is {settings.CORPUS_REPO}: nothing was pushed")
    _git(settings, "add", "-A", "--", ".")   # the corpus directory: git runs in it
    prefix = _git(settings, "rev-parse", "--show-prefix")   # the corpus directory relative to the repository's root
    outside = [p for p in _git(settings, "diff", "--cached", "--name-only", "-z").split("\0") if p and not p.startswith(prefix)]
    if outside:
        raise RepoError(f"staged outside {settings.CORPUS_PATH}, nothing was committed: {', '.join(outside)}")
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
        try:
            _run(
                ["gh", "pr", "close", str(number), "--repo", settings.CORPUS_REPO, "--comment",
                 f"Superseded by {url} (regenerated from current upstream).", "--delete-branch"],
                corpus,
            )
        except RepoError as e:
            raise RepoError(f"{e}; the new pull request is {url}; pull requests already closed: {superseded or 'none'}") from None
        superseded.append(number)
    return {"has_changes": True, "commit_sha": sha, "pr_url": url, "superseded_prs": superseded}
