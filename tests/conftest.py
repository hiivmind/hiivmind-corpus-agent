"""The corpus fixtures (the `Corpus` of `tests/corpus_fixture.py`), and `run` and `job` for the nodes and the sequence, on the facade and the scripted backend."""

import json
from datetime import date

import pytest

import agent_core
from agent_core.contracts.events import ModelRequested, ToolReturned
from agent_core.core.instance import load_instance
from agent_core.core.registry import provider
from agent_core.core.settings import load_settings

from tests.corpus_fixture import Corpus, make_corpus
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
def corpus_drafts(monkeypatch, _current, tmp_path):
    """`corpus` whose upstream also has `docs/drafts/e.md` and whose config skips the section `drafts`. One test uses one corpus fixture."""
    return _make(monkeypatch, _current, tmp_path, drafts=True)


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


def _scripted(monkeypatch, corpus: Corpus, case: str | None, **tokens: str) -> None:
    """The environment of a scripted run: the stand-in `gh`, and the scripts of `case` as the backend's `SCRIPTS` setting."""
    for name, value in {**corpus.environment(), "AGENT_CORE_SCRIPTED_SCRIPTS": str(corpus.scripts(case, **tokens))}.items():
        monkeypatch.setenv(name, value)


def _open(corpus: Corpus, params: dict | None = None):
    return agent_core.open(
        INSTANCE_YAML, backend="scripted", settings=[corpus.settings_file], params=params, runs=corpus.base / "runs",
    )


@pytest.fixture
def run(_current, monkeypatch):
    """`await run(node, inputs, case=None, **tokens)`: one node of the instance, driven by `tests/scripts/<case or "ok">/<node>.json`
    filled with `tokens` too. A dict: `outcome` (the exit), `outputs`, `reason` and the harness's `detail` (`errors`, ...)."""
    async def run(node: str, inputs: dict, case: str | None = None, **tokens: str) -> dict:
        _scripted(monkeypatch, _current["corpus"], case, **tokens)
        async with _open(_current["corpus"]) as harness:
            outcome = await harness.nodes.run(node, inputs)
        return {"outcome": outcome.exit, "outputs": outcome.outputs, "reason": outcome.reason, **outcome.detail}
    return run


@pytest.fixture
def instructions(_current, monkeypatch):
    """`await instructions(node, inputs)`: the instructions the scripted backend was sent for the node: its filled procedure."""
    async def instructions(node: str, inputs: dict) -> str:
        _scripted(monkeypatch, _current["corpus"], None)
        async with _open(_current["corpus"]) as harness:
            await harness.nodes.run(node, inputs)
            sent = [e for e in harness.events.record() if isinstance(e, ModelRequested)]
        return next(part.text for part in sent[0].parts if part.kind == "instructions")
    return instructions


@pytest.fixture
def job(_current, monkeypatch):
    """`await job(case="ok", resume=None, *, sequence="refresh", params=None)`: the sequence on the facade, the `SequenceResult`.
    `sent(node)` then gives what the backend was sent. Every run of a test keeps its directory in one `runs/`, so one journal holds them all and `resume` (a run id) finds the
    run it names."""
    async def job(case: str = "ok", resume: str | None = None, *, sequence: str = "refresh", params: dict | None = None):
        corpus: Corpus = _current["corpus"]
        _scripted(monkeypatch, corpus, case)
        async with _open(corpus, params) as harness:
            try:
                if resume:
                    return await harness.sequences.resume(resume)
                return await harness.sequences.run(sequence, {})
            finally:
                sent: dict[str, list[str]] = {}
                _current["tools"] = [event for event in harness.events.record() if isinstance(event, ToolReturned)]
                for event in harness.events.record():
                    if isinstance(event, ModelRequested):
                        for part in event.parts:
                            if part.kind == "instructions":
                                sent.setdefault(event.label.partition("#")[0], []).append(part.text)
                _current["sent"] = sent
    return job


@pytest.fixture
def sent(_current):
    """`sent(node) -> list[str]`: the instruction texts the scripted backend was sent for the node in the last `job` of this test."""
    def sent(node: str) -> list[str]:
        return _current["sent"].get(node, [])
    return sent


@pytest.fixture
def tool_results(_current):
    """`tool_results(name) -> list[(args, result)]`: each call of the tool in the last `job` of this test, with the result it returned
    (the JSON of its first line when that is JSON, else its text; a tool that records outputs adds a trailer after a blank line)."""
    def tool_results(name: str) -> list[tuple[dict, object]]:
        found = []
        for event in _current["tools"]:
            if event.call.name == name:
                try:
                    result = json.loads(event.text.partition("\n\n(recorded by this call")[0])
                except ValueError:
                    result = event.text
                found.append((event.call.args, result))
        return found
    return tool_results
