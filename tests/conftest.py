"""The corpus fixtures (the `Corpus` of the package's `corpus_fixture`), and `run` and `job` for the nodes and the sequence."""

import json
import os
import subprocess
import sys
from datetime import date

import pytest

from agent_core.backends.scripted import ScriptedBackend
from agent_core.core.instance import load_instance
from agent_core.core.job_runner import open_run
from agent_core.core.registry import provider
from agent_core.core.settings import load_settings

from corpus_fixture import Corpus, make_corpus
from tests.helpers import ROOT

INSTANCE_YAML = ROOT / "instance.yaml"
Corpus.SCRIPTS = ROOT / "tests" / "scripts"

@pytest.fixture
def _current():
    """The corpus fixture of this test, for `run` and `job` to find. One test uses one corpus fixture."""
    return {}


def _make(monkeypatch, current, tmp_path, *, at_root=False, push=False, extra_files=0, stale=(), checkout=False, **layout) -> Corpus:
    corpus = make_corpus(monkeypatch, tmp_path, at_root=at_root, push=push, extra_files=extra_files, stale=stale, checkout=checkout, **layout)
    current["corpus"] = corpus
    return corpus


@pytest.fixture
def corpus(monkeypatch, _current, tmp_path):
    """The corpus in `hiivmind-corpus-test/`, `PUSH: false`. One test uses one corpus fixture: they all build in `tmp_path`."""
    return _make(monkeypatch, _current, tmp_path)


@pytest.fixture
def corpus_pushing(monkeypatch, _current, tmp_path):
    """`corpus` with `PUSH: true`. One test uses one corpus fixture."""
    return _make(monkeypatch, _current, tmp_path, push=True)


@pytest.fixture
def corpus_stale(monkeypatch, _current, tmp_path):
    """`corpus` with `docs:a.md` and `docs:b.md` stale and `.source/docs/` checked out. One test uses one corpus fixture."""
    return _make(monkeypatch, _current, tmp_path, stale=("docs:a.md", "docs:b.md"), checkout=True)


@pytest.fixture
def corpus_many(monkeypatch, _current, tmp_path):
    """62 entries in the index, all stale, and 61 files in the source (`c.md` is deleted there, and the job drops its entry): three
    batches of at most 30. One test uses one corpus fixture."""
    names = ["docs:a.md", "docs:b.md", "docs:c.md"] + [f"docs:m{i:02d}.md" for i in range(1, 60)]
    return _make(monkeypatch, _current, tmp_path, extra_files=59, stale=tuple(names), checkout=True)


@pytest.fixture
def corpus_second(monkeypatch, _current, tmp_path):
    """A second corpus, `hiivmind-corpus-second/`, `PUSH: false`: its source is `guide`, its documents are under `manual/`, and
    its branches start `automated/corpus-refresh-second`. One test uses one corpus fixture."""
    return _make(monkeypatch, _current, tmp_path, corpus_name="second", source="guide", docs_root="manual")


@pytest.fixture
def corpus_v1_bullets(monkeypatch, _current, tmp_path):
    """A v1 corpus whose `index.md` lists `a.md` and `b.md` as bullets; `.source/docs/` checked out at `first_sha`. One test
    uses one corpus fixture."""
    return _make(monkeypatch, _current, tmp_path, checkout=True, v1="bullets")


@pytest.fixture
def corpus_v1_tiered(monkeypatch, _current, tmp_path):
    """A tiered v1 corpus: `index.md` with a Quick Reference listing `a.md`, and `index-guide.md` with `a.md` and `b.md`;
    `.source/docs/` checked out at `first_sha`. One test uses one corpus fixture."""
    return _make(monkeypatch, _current, tmp_path, checkout=True, v1="tiered")


@pytest.fixture
def corpus_v1_table(monkeypatch, _current, tmp_path):
    """A v1 corpus whose `index.md` lists `a.md` and `b.md` in a table; `.source/docs/` checked out at `first_sha`. One test
    uses one corpus fixture."""
    return _make(monkeypatch, _current, tmp_path, checkout=True, v1="table")


@pytest.fixture
def today() -> str:
    """Today's date as the branch names write it."""
    return date.today().isoformat()


@pytest.fixture
def instance():
    return load_instance(INSTANCE_YAML, provider("resources", "folder")(ROOT))


@pytest.fixture
def load(instance):
    """`load(file, params=None)`: the settings of the instance with `file` layered over `config/base.yaml`."""
    def load(file: str, params: dict | None = None):
        return load_settings(instance, [ROOT / "config" / "base.yaml", ROOT / file], params)
    return load


@pytest.fixture
def run(_current):
    """`await run(node, inputs, case=None, **tokens)`: one node of the instance, driven by `tests/scripts/<case or "ok">/<node>.json`
    filled with `tokens` too."""
    async def run(node: str, inputs: dict, case: str | None = None, **tokens: str) -> dict:
        corpus: Corpus = _current["corpus"]
        script = json.loads((corpus.scripts(case, **tokens) / f"{node}.json").read_text())
        run_dir = corpus.next_dir("run")
        async with open_run(INSTANCE_YAML, settings_files=[corpus.settings_file], run_dir=run_dir) as opened:
            return await opened.run_node(node, inputs, driver=ScriptedBackend(script=script))
    return run


@pytest.fixture
def job(_current):
    """`job(case="ok", resume=None)`: the refresh sequence in a subprocess; `(exit code, standard output, run record or None)`.
    Every run of a test keeps its directory beside the others, so one journal holds them all and `resume` (a run id) finds
    the run it names."""
    def job(case: str = "ok", resume: str | None = None):
        corpus: Corpus = _current["corpus"]
        run_dir = corpus.next_dir("run")
        command = [
            sys.executable, "-m", "agent_core.core.cli", "job", str(INSTANCE_YAML), "refresh",
            "--settings", str(corpus.settings_file), "--backend", "scripted", "--run-dir", str(run_dir),
        ]
        if resume:
            command += ["--resume", resume]
        environment = {**os.environ, **corpus.environment(), "AGENT_CORE_SCRIPTED_SCRIPTS": str(corpus.scripts(case))}
        r = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        record = run_dir / "record.json"
        return r.returncode, r.stdout, json.loads(record.read_text()) if record.exists() else None
    return job
