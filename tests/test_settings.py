from pathlib import Path

import agent_core
import pytest
from agent_core.core.settings import load_settings

from tests.helpers import ROOT

INSTANCE_YAML = ROOT / "instance.yaml"


def test_two_settings_files_point_one_instance_at_two_corpora(load):
    assert load("config/polars.yaml").BRANCH_PREFIX == "automated/corpus-refresh-polars"
    assert load("config/ibis.yaml").BRANCH_PREFIX == "automated/corpus-refresh-ibis"


def test_param_overrides_the_repository(load):
    assert load("config/polars.yaml", {"CORPUS_REPO": "someone/fork"}).CORPUS_REPO == "someone/fork"


def test_a_relative_corpus_path_is_absolute_under_the_working_directory(load, monkeypatch, tmp_path):
    # the files server resolves a relative path against its root, not the job's directory, so the settings hand it absolute
    monkeypatch.chdir(tmp_path)
    expected = (tmp_path.parent / "hiivmind-corpus-data" / "hiivmind-corpus-polars").resolve()
    assert load("config/polars.yaml").CORPUS_PATH == expected
    assert load("config/polars.yaml", {"CORPUS_PATH": "~/c"}).CORPUS_PATH == (Path.home() / "c").resolve()


def test_a_param_overrides_the_settings_file(instance, tmp_path):   # SET-3, Review Focus 5: a scratch clone's file says PUSH: true
    file = tmp_path / "s.yaml"
    file.write_text(f"CORPUS_PATH: {tmp_path}\nCORPUS_REPO: a/b\nBRANCH_PREFIX: x\nPUSH: true\n")
    assert load_settings(instance, [file]).PUSH is True
    assert load_settings(instance, [file], {"PUSH": "false"}).PUSH is False
    agent_core.open(INSTANCE_YAML, backend="scripted", settings=[file], params={"PUSH": "false"})   # `open` takes both


def test_a_missing_setting_stops_the_run_before_it_starts_and_names_it(tmp_path):
    settings = tmp_path / "s.yaml"
    settings.write_text("CORPUS_REPO: a/b\nBRANCH_PREFIX: x\n")
    with pytest.raises(agent_core.RunCannotStart, match="CORPUS_PATH"):
        agent_core.open(INSTANCE_YAML, backend="scripted", settings=[settings], runs=tmp_path / "runs")


def test_the_instance_loads(instance):
    assert set(instance.nodes) == {
        "update-sources", "scan", "index", "concepts", "verify", "embed", "publish", "checkout-sources", "status", "migrate",
        "graph-validate", "prepare-base", "check-upstream",
    } and instance.backend == "langgraph"


async def test_the_instance_loads_and_offers_each_declared_tool(corpus):
    async with agent_core.open(INSTANCE_YAML, backend="scripted", settings=[corpus.settings_file]) as harness:
        functions, servers = set(harness.instance.functions), set(harness.instance.servers)
        assert len(functions) == 22 and servers == {"shell", "files"}
        for name, node in harness.instance.nodes.items():
            for tool in node.allowed_tools:
                assert tool in functions or tool.partition("__")[0] in servers, f"{name}: {tool}"
