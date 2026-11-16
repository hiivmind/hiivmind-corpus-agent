"""The `refresh` sequence through `agent-core job`, with the scripted backend over the fixture corpus: the checks are real,
every node is scripted, and every tool call of a script is real."""

from pathlib import Path

from tests.helpers import ROOT

WALK = ["checks", "update-sources", "scan[list]", "scan[1]", "scan", "index", "concepts", "verify", "embed", "publish"]


def names(record: dict) -> list[str]:
    return [step["name"] for step in record["steps"]]


def outcomes(record: dict) -> dict[str, str]:
    return {step["name"]: step["outcome"] for step in record["steps"]}


def test_nothing_to_do_makes_no_model_call(corpus, job):             # criterion 1, CRP-2
    corpus.set_last_sha(corpus.upstream_head)
    code, out, record = job()
    assert code == 0 and "Already current." in out
    assert record["summary"] == "Already current." and record["end_state"] == "done" and record["model_calls"] == 0
    assert names(record) == ["checks"] and outcomes(record)["checks"] == "current"


def test_a_refresh_walks_every_node_in_order_and_commits(corpus, job, today):
    code, out, record = job()
    assert code == 0, out
    assert names(record) == WALK and record["end_state"] == "done" and outcomes(record)["publish"] == "committed"
    branch = f"automated/corpus-refresh-test-{today}"
    assert corpus.git("branch", "--show-current") == "main" and corpus.git("status", "--porcelain") == ""
    assert corpus.git("log", "-1", "--format=%s", branch) == f"corpus: refresh {today}"
    committed = corpus.git("show", f"{branch}:hiivmind-corpus-test/index.yaml")
    assert "docs:c.md" not in committed and "The file d.md, added in the second commit." in committed
    facts = record["facts"]
    assert facts["enriched_ids"] == ["docs:a.md", "docs:d.md"] and facts["scans_failures"] == [] and facts["branch"] == branch


def test_a_dirty_tree_fails_before_any_node(corpus, job):            # example 4
    corpus.write("stray.txt", "x")
    code, out, record = job()
    assert code == 1 and "the working tree is dirty" in out and "stray.txt" in out
    assert record["end_state"] == "failed" and names(record) == ["checks"] and record["model_calls"] == 0


def test_a_v1_index_is_not_ready(corpus, job):                       # example 6
    (corpus.path / "index.yaml").unlink()
    corpus._save("test: a v1 corpus")
    code, out, record = job()
    assert code == 1 and "The corpus has no config.yaml, no source, or no built v2 index." in out
    assert record["end_state"] == "failed" and record["model_calls"] == 0


def test_a_failed_verify_still_publishes(corpus, job):
    code, out, record = job("verify_fails")
    assert code == 0, out
    assert outcomes(record)["verify"] == "failed" and outcomes(record)["embed"] == "done" and outcomes(record)["publish"] == "committed"


def test_nothing_names_the_deleted_files():
    files = [*Path(ROOT, "skills").glob("*/SKILL.md"), *Path(ROOT, "fragments").glob("*.md"), ROOT / "instance.yaml", ROOT / "topology.yaml"]
    for file in files:
        text = file.read_text()
        for gone in ("jobs/", "tools/repo.py", "tools/index.py", "tools/status.py", "scripts/", "reference/"):
            assert gone not in text, f"{file.name}: {gone}"

