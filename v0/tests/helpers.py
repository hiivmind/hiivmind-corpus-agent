"""Plain functions the tests share."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # the instance: the repository's root


def sh(command: str, cwd: Path | str | None = None) -> subprocess.CompletedProcess:
    """Run a shell command, by default in the instance's directory, as `shell__run` does."""
    return subprocess.run(command, shell=True, cwd=cwd or ROOT, capture_output=True, text=True)


def gh_calls() -> list[list[str]]:
    """The arguments of each call the stand-in `gh` has had in this test, oldest first."""
    log = Path(os.environ["GH_STANDIN_LOG"])
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
