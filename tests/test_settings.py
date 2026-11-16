import subprocess
import sys

from tests.helpers import ROOT


def test_two_settings_files_point_one_instance_at_two_corpora(load):
    assert load("config/polars.yaml").BRANCH_PREFIX == "automated/corpus-refresh-polars"
    assert load("config/ibis.yaml").BRANCH_PREFIX == "automated/corpus-refresh-ibis"


def test_param_overrides_the_repository(load):
    assert load("config/polars.yaml", {"CORPUS_REPO": "someone/fork"}).CORPUS_REPO == "someone/fork"


def test_a_missing_setting_stops_the_run_before_it_starts_and_names_it(tmp_path):
    settings = tmp_path / "s.yaml"
    settings.write_text("CORPUS_REPO: a/b\nBRANCH_PREFIX: x\n")
    r = subprocess.run(
        [sys.executable, "-m", "agent_core.core.cli", "job", "instance.yaml", "refresh", "--settings", str(settings), "--run-dir", str(tmp_path / "run")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 2 and r.stdout.startswith("error: ") and "CORPUS_PATH" in r.stdout and len(r.stdout.strip().splitlines()) == 1
    assert not (tmp_path / "run" / "record.json").exists()


def test_the_instance_loads(instance):
    assert set(instance.nodes) == {"scan"} and instance.backend == "langgraph"
