"""The `run_job` fixture of the model tests: one sequence through `agent-core job ... --backend langgraph`, in a subprocess.

The model is `AGENT_CORE_LANGGRAPH_MODEL` (develop on `claude-haiku-5-5`); the directory of every run is kept under
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

MODEL = os.environ.get("AGENT_CORE_LANGGRAPH_MODEL", "claude-sonnet-5-5")


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

    def outcome(self, step: str) -> str | None:
        return next((s["outcome"] for s in self.record.get("steps") or [] if s["name"] == step), None)

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
            sys.executable, "-m", "agent_core.core.cli", "job", str(ROOT / "instance.yaml"), sequence,
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
