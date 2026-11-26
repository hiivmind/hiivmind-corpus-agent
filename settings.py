"""The settings of the corpus instance: which corpus, where its pull request goes, and whether to push."""

from pathlib import Path

from mountainash_settings import MountainAshBaseSettings
from pydantic import field_validator


class CorpusSettings(MountainAshBaseSettings):  # env prefix HIIVMIND_CORPUS_
    CORPUS_PATH: Path        # the corpus root: the directory holding config.yaml
    CORPUS_REPO: str         # owner/name on GitHub; where the pull request goes
    BRANCH_PREFIX: str       # e.g. automated/corpus-refresh-polars
    BASE_BRANCH: str = "main"
    PUSH: bool = True        # false: commit on the local branch and stop; no push, no pull request

    @field_validator("CORPUS_PATH")
    @classmethod
    def _absolute(cls, path: Path) -> Path:
        """Absolute against the working directory: the nodes hand the path to tool servers that resolve it elsewhere."""
        return path.expanduser().resolve()
