"""A corpus and its upstream built in a temporary directory, and a stand-in `gh`: the `Corpus` the instance's tests build on.
The corpus files are built from the package's frozen values and written with `dumps`; `index.md` is the package's render.

The layout of one corpus fixture, under `tmp_path`:

    upstream/      the documentation's own git repository (branch main): docs/a.md, b.md, c.md; a second commit
    origin.git/    the bare remote of the corpus repository
    clone/         a clone of origin holding hiivmind-corpus-test/ (the corpus) beside hiivmind-corpus-other/; `corpus_second`
                   holds hiivmind-corpus-second/ instead, whose source `guide` has its documents under manual/
    bin/gh         the stand-in `gh`, first on PATH

A v1 corpus (`v1="bullets" | "tiered"`) has the v1 index of that layout (`V1_INDEXES`) instead of `index.yaml`, `graph.yaml` and
the rendered `index.md`; its checkout of the source, when asked for, is at `first_sha`, where a.md, b.md and c.md exist.
`drafts=True` adds `drafts/e.md` under the documents' root to the upstream's second commit and skips the section `drafts`.
"""

import itertools
import json
import os
import stat
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import yaml

from hiivmind_corpus import NULL, Config, Corpus as Package, Entry, Graph, Index
from hiivmind_corpus.config import Build, CorpusInfo, IndexInfo, Settings
from hiivmind_corpus.graph import Concept, GraphMeta
from hiivmind_corpus.index import IndexMeta
from hiivmind_corpus.sources import SOURCE_KINDS, GitSource

BASE_SETTINGS = {"BASE_BRANCH": "main", "PUSH": False}   # the instance's config/base.yaml, under the generated settings file
THEN = datetime(2026, 1, 1, tzinfo=UTC)


GH_STANDIN = """#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["GH_STANDIN_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["pr", "list"]:
    canned = os.environ.get("GH_STANDIN_PRS", "")
    print(open(canned).read() if canned and os.path.exists(canned) else "[]")
elif args[:2] == ["pr", "create"]:
    print("https://github.com/test/test/pull/1")
"""


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)} (in {cwd}) failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _init(path: Path, *args: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", *args, str(path)], check=True)
    if "--bare" not in args:
        for key, value in (("user.name", "Test"), ("user.email", "test@example.com"), ("commit.gpgsign", "false")):
            _git(path, "config", key, value)
    return path


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    if subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet"]).returncode:
        _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


V1_INDEXES = {   # each v1 layout: its files, as found in the corpora (flyio's bare GREP, atproto's dates, htmx's table)
    "bullets": {
        "index.md": (
            "# Test Documentation Corpus\n\n> Two files.\n\n---\n\n## Basics\n\n"
            "- **Alpha** `docs:a.md` - The file a.md, in v1.\n"
            "- **Beta** (2023-06-08) `docs:b.md` ⚡ GREP - The file b.md, in v1.\n"
        ),
    },
    "tiered": {
        "index.md": (
            "# Test Documentation Corpus\n\n---\n\n## Quick Reference\n\n### Start here\n"
            "- **Alpha** `docs:a.md` - Alpha, in short.\n\n---\n\n"
            "## The Guide\n*The guide to the test documents.*\n\n→ See [index-guide.md](index-guide.md)\n"
        ),
        "index-guide.md": (
            "# Guide - Detailed Index\n\n> Back to [main index](index.md)\n\n---\n\n## Basics\n\n"
            "- **Alpha** `docs:a.md` - The file a.md, in v1.\n"
            "  Keywords: `alpha`\n"
            "- **Beta** `docs:b.md` - The file b.md, in v1. ⚡ GREP - `grep -n \"^## \" FILE` ⏳ STALE\n"
        ),
    },
}


def _entry(source: str, name: str) -> Entry:
    stem = name.removesuffix(".md")
    return Entry(
        id=f"{source}:{name}", source=source, path=name, title=stem.upper(), summary=f"The file {name}.", tags=("test",),
        keywords=(stem,), concepts=("concept",), category="reference", content_type="markdown", size="standard",
        grep_hint=NULL, headings=(), links_to=(), links_from=(), frontmatter={}, stale=False, stale_since=NULL, last_indexed=THEN,
    )



class Corpus:
    """A corpus repository clone and everything around it. Every helper that changes the corpus commits and pushes, so the tree stays clean and main is not ahead of origin."""

    SCRIPTS: Path | None = None   # the scripted-backend scripts `scripts()` fills: an instance's `tests/scripts/`

    def __init__(
        self, base: Path, *, at_root: bool, push: bool, extra_files: int, stale: tuple[str, ...], checkout: bool,
        corpus_name: str = "test", source: str = "docs", docs_root: str = "docs", v1: str | None = None, drafts: bool = False,
    ):
        self.base = base
        self.upstream = _init(base / "upstream")
        self.origin = _init(base / "origin.git", "--bare")
        self.clone = _init(base / "clone")
        self.bin = base / "bin"
        self.gh_log = base / "gh.log"
        self.gh_prs = base / "gh-prs.json"
        self._counter = itertools.count(1)
        self.branch_prefix = f"automated/corpus-refresh-{corpus_name}"

        names = ["a.md", "b.md", "c.md"] + [f"m{i:02d}.md" for i in range(1, extra_files + 1)]
        docs = self.upstream / docs_root
        docs.mkdir(exist_ok=True)
        for name in names:
            (docs / name).write_text(f"# {name}\n\nFirst version of {name}.\n")
        self.first_sha = _commit(self.upstream, "docs: first")
        (docs / "a.md").write_text("# a.md\n\nChanged.\n")
        (docs / "d.md").write_text("# d.md\n\nNew.\n")
        (docs / "c.md").unlink()
        if drafts:
            (docs / "drafts").mkdir()
            (docs / "drafts" / "e.md").write_text("# e.md\n\nA draft.\n")
        self.upstream_head = _commit(self.upstream, "docs: change a, add d, delete c")

        self.path = self.clone if at_root else self.clone / f"hiivmind-corpus-{corpus_name}"
        self.path.mkdir(exist_ok=True)
        config = Config(
            schema_version=2,
            corpus=CorpusInfo(name=corpus_name, display_name=corpus_name.title(), created_at=THEN, keywords=(corpus_name,)),
            sources=(GitSource(
                id=source, repo_url=str(self.upstream), branch="main", docs_root=docs_root,
                last_commit_sha=self.first_sha, last_indexed_at=THEN,
            ),),
            index=IndexInfo(format="markdown", last_updated_at=THEN),
            settings=Settings(include_patterns=("**/*.md",), exclude_patterns=("**/_*.md",)),
            build=Build(skip_sections=("drafts",)) if drafts else None,
        )
        (self.path / "config.yaml").write_text(config.dumps())
        if v1:
            for name, text in V1_INDEXES[v1].items():
                (self.path / name).write_text(text)
        else:
            entries = tuple(_entry(source, name) for name in names)
            (self.path / "index.yaml").write_text(Index(
                meta=IndexMeta(generated_at=THEN, entry_count=len(entries)), entries=entries).dumps())
            (self.path / "graph.yaml").write_text(Graph(
                schema_version=2,
                concepts={"concept": Concept(label="Concept", description="The one concept of the test corpus", tags=("test",))},
                relationships=(), meta=GraphMeta(generated_at=THEN, concept_count=1, relationship_count=0)).dumps())
            Package.open(self.path).render.write()
        if not at_root:
            other = self.clone / "hiivmind-corpus-other"
            other.mkdir()
            (other / "config.yaml").write_text("schema_version: 2\n")
        (self.clone / ".gitignore").write_text("**/.source/\n**/.cache/\n")
        _commit(self.clone, "corpus: first")
        _git(self.clone, "remote", "add", "origin", str(self.origin))
        _git(self.clone, "push", "-q", "-u", "origin", "main")

        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(GH_STANDIN.format(python=sys.executable))
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        self.settings_file = base / "settings.yaml"
        written = {"CORPUS_PATH": str(self.path), "CORPUS_REPO": "test/test", "BRANCH_PREFIX": self.branch_prefix, "PUSH": push}
        self.settings_file.write_text(json.dumps(written))   # JSON is YAML
        self.settings = SimpleNamespace(**{**BASE_SETTINGS, **written, "CORPUS_PATH": self.path})

        if checkout:  # the working copy of the source, at the upstream's head, where the scanner reads its files
            source_clone = self.path / ".source" / source
            source_clone.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "-q", str(self.upstream), str(source_clone)], check=True)
            if v1:
                _git(source_clone, "checkout", "-q", self.first_sha)
        if stale:
            self.mark_stale(*stale)

    def next_dir(self, label: str) -> Path:
        """A path under the fixture's directory that no one has been given before; not created."""
        return self.base / f"{label}-{next(self._counter)}"

    # --- the environment the stand-in `gh` needs -------------------------------------------------------------------
    def environment(self) -> dict[str, str]:
        return {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GH_STANDIN_LOG": str(self.gh_log),
            "GH_STANDIN_PRS": str(self.gh_prs),
        }

    # --- reading and writing the clone -----------------------------------------------------------------------------
    def git(self, *args: str) -> str:
        """Run git in the clone; the standard output, stripped."""
        return _git(self.clone, *args)

    def write(self, path: str, text: str) -> None:
        """Write a file, relative to the corpus directory. Does not commit."""
        target = (self.path / path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def entry(self, id: str) -> dict:
        """The entry of `index.yaml` with this id, as it is on disk now, as the mapping the file holds."""
        found = [e for e in yaml.safe_load((self.path / "index.yaml").read_text())["entries"] if e["id"] == id]
        assert len(found) == 1, f"{len(found)} entries with id {id}"
        return found[0]

    def _save(self, message: str) -> None:
        """Commit on main and push it: `repo_prepare` refuses a main that is ahead of origin's."""
        _commit(self.clone, message)
        _git(self.clone, "push", "-q", "origin", "HEAD:refs/heads/main")

    def _edit_config(self, change, message: str) -> None:
        package = Package.open(self.path)
        config = change(package.config.load())
        index = config.index or IndexInfo()
        (self.path / "config.yaml").write_text(replace(config, index=replace(index, last_updated_at=package.now())).dumps())
        self._save(message)

    def _edit_index(self, change, message: str) -> None:
        package = Package.open(self.path)
        index = change(package.index.load())
        meta = index.meta or IndexMeta()
        (self.path / "index.yaml").write_text(replace(index, meta=replace(meta, generated_at=package.now())).dumps())
        package.render.write()
        self._save(message)

    # --- helpers that set up state; each commits --------------------------------------------------------------------
    def set_last_sha(self, sha: str) -> None:
        self._edit_config(
            lambda c: replace(c, sources=(replace(c.sources[0], last_commit_sha=sha), *c.sources[1:])), "test: set last_commit_sha")

    def set_repo_url(self, url: str) -> None:
        self._edit_config(
            lambda c: replace(c, sources=(replace(c.sources[0], repo_url=url), *c.sources[1:])), "test: set repo_url")

    def add_source(self, source: dict) -> None:
        """Add a source given as the mapping a `config.yaml` holds, read through its kind's `parse`."""
        parsed = SOURCE_KINDS[source["type"]].parse(source)
        self._edit_config(lambda c: replace(c, sources=(*c.sources, parsed)), "test: add a source")

    def add_entry(self, entry: Entry) -> None:
        self._edit_index(lambda i: replace(i, entries=(*i.entries, entry)), "test: add an entry")

    def mark_stale(self, *ids: str) -> None:
        def change(index: Index) -> Index:
            assert {e.id for e in index.entries} >= set(ids), f"no such entries: {ids}"
            now = Package.open(self.path).now()
            return replace(index, entries=tuple(
                replace(e, stale=True, stale_since=now) if e.id in ids else e for e in index.entries))
        self._edit_index(change, "test: mark entries stale")

    def set_concepts(self, id: str, concepts: list[str]) -> None:
        def change(index: Index) -> Index:
            assert any(e.id == id for e in index.entries), f"no such entry: {id}"
            return replace(index, entries=tuple(
                replace(e, concepts=tuple(concepts)) if e.id == id else e for e in index.entries))
        self._edit_index(change, "test: set concepts")

    def set_gh_open_prs(self, prs: list[dict], branch: str | None = None) -> None:
        """Make `gh pr list` print `prs`, and give origin the branch those pull requests are from (four days old by default)."""
        self.gh_prs.write_text(json.dumps(prs))
        branch = branch or f"{self.branch_prefix}-{(date.today() - timedelta(days=4)).isoformat()}"
        _git(self.clone, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")

    def advance_origin(self) -> str:
        """Commit outside the corpus directory to origin's `main` from a second clone; the new sha. The clone does not have it."""
        other = self.base / f"other-{next(self._counter)}"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(other)], check=True)
        for key, value in (("user.name", "Test"), ("user.email", "test@example.com"), ("commit.gpgsign", "false")):
            _git(other, "config", key, value)
        (other / f"advance-{next(self._counter)}.txt").write_text("Someone else's commit.\n")
        sha = _commit(other, "other: advance origin")
        _git(other, "push", "-q", "origin", "HEAD:refs/heads/main")
        return sha

    def make_ahead(self) -> str:
        """Commit on the clone's `main` and do not push it; the new sha."""
        (self.clone / f"ahead-{next(self._counter)}.txt").write_text("A local commit.\n")
        return _commit(self.clone, "test: ahead of origin")

    # --- scripted-backend scripts -----------------------------------------------------------------------------------
    def scripts(self, case: str | None = None, **tokens: str) -> Path:
        """A filled copy of `tests/scripts/<case or ok>/`, in a temporary directory; its path.

        A node the case has no file for is played from `tests/scripts/ok/`.

        A script is a template. `@CORPUS@` becomes the corpus directory, `@CLONE@` the clone, `@UPSTREAM@` the upstream,
        `@OLD_SHA@` the `last_commit_sha` the corpus holds now, `@NEW_SHA@` the upstream's head, `@OLD_SHA7@` and `@NEW_SHA7@` their first seven characters, `@TODAY@` today's date;
        `tokens` add or replace tokens: `scripts("ok", FILE="a.md")` fills `@FILE@`.
        """
        case = case or "ok"
        old = Config.loads((self.path / "config.yaml").read_text()).sources[0].last_commit_sha
        fill = {
            "CORPUS": str(self.path), "CLONE": str(self.clone), "UPSTREAM": str(self.upstream), "OLD_SHA": old,
            "NEW_SHA": self.upstream_head, "OLD_SHA7": old[:7], "NEW_SHA7": self.upstream_head[:7],
            "TODAY": date.today().isoformat(), **tokens,
        }
        out = self.next_dir(f"scripts-{case}")
        out.mkdir()
        files = {file.name: file for file in sorted((self.SCRIPTS / "ok").glob("*.json"))}
        files.update({file.name: file for file in sorted((self.SCRIPTS / case).glob("*.json"))})
        for name, file in files.items():
            text = file.read_text()
            for token, value in fill.items():
                text = text.replace(f"@{token}@", json.dumps(value)[1:-1])
            (out / name).write_text(text)
        return out


def make_corpus(monkeypatch, *args, **kwargs) -> Corpus:
    """A `Corpus`, with the environment its stand-in `gh` needs set for the test."""
    corpus = Corpus(*args, **kwargs)
    for key, value in corpus.environment().items():
        monkeypatch.setenv(key, value)
    return corpus
