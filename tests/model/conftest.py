"""The `run_job` fixture of the model tests: one sequence through `agent-core job`, on the LangGraph backend, in a subprocess.

The model is `anthropic:claude-haiku-5-5`, set as `AGENT_CORE_LANGGRAPH_MODEL` unless the shell already sets it; the directory of every run is kept under
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

from tests.helpers import ROOT

MODEL_ID = os.environ.get("AGENT_CORE_LANGGRAPH_MODEL", "anthropic:claude-haiku-5-5")
MODEL = MODEL_ID.split(":")[-1]


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
    def facts(self) -> dict:
        """What every node of the sequence gave, by name (the record's `facts`)."""
        return self.record.get("facts") or {}

    @property
    def model_calls(self) -> int:
        return sum(note.get("model_calls", 0) for note in self.record.get("notes") or [])

    def outcome(self, step: str) -> str | None:
        """The outcome of the last step named `step`, looking inside a fragment's trail entry (`steps`) too."""
        def walk(steps):
            for s in steps or []:
                yield s
                yield from walk(s.get("steps"))
        return next((s.get("outcome") for s in reversed(list(walk(self.record.get("steps")))) if s.get("name") == step), None)

    def why(self) -> str:
        """What to show when an assertion about this run fails."""
        record = self.record
        return (
            f"exit code {self.code}; end {record.get('end_state')}; steps {record.get('steps')}; summary {record.get('summary')}\n"
            f"failures {json.dumps(record.get('failures'), indent=1)}\nstdout: {self.out[-2000:]}\nstderr: {self.err[-2000:]}\n"
            f"run directory: {self.dir}"
        )


@pytest.fixture
def run_job(request):
    """`run_job(corpus, *, sequence="refresh", **params)`: the sequence, `agent-core job instance.yaml <sequence>`, with the
    corpus's settings file and the LangGraph backend, once, in a subprocess whose `PATH` starts with the stand-in `gh`; each
    `--param` as `KEY=value`."""
    name = re.sub(r"[^\w.-]", "_", request.node.name)
    where = ROOT / "runs" / "model-tests" / date.today().isoformat() / MODEL / name
    shutil.rmtree(where, ignore_errors=True)
    runs = itertools.count(1)

    def run_job(corpus, *, sequence: str = "refresh", **params: str) -> Ran:
        run_dir = where / f"run-{next(runs)}"
        run_dir.mkdir(parents=True)
        command = [
            sys.executable, "-m", "agent_core.cli", "job", str(ROOT / "instance.yaml"), sequence,
            "--settings", str(corpus.settings_file), "--no-ask", "--backend", "langgraph", "--run-dir", str(run_dir),
        ]
        for key, value in params.items():
            command += ["--param", f"{key}={value}"]
        done = subprocess.run(
            command, cwd=ROOT, env={**os.environ, "AGENT_CORE_LANGGRAPH_MODEL": MODEL_ID, **corpus.environment()}, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=1800,
        )
        (run_dir / "stdout.txt").write_text(done.stdout)
        (run_dir / "stderr.txt").write_text(done.stderr)
        return Ran(done.returncode, done.stdout, done.stderr, run_dir)

    return run_job
