"""The `refresh` sequence through `agent-core job`, with the scripted backend over the fixture corpus: the checks are real,
every node is scripted, and every tool call of a script is real."""

import re
from pathlib import Path

import yaml

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


# --- the harder paths (Review Focus 1 to 5, examples 5, 7 and 8) ---------------------------------------------------------

def test_sixty_two_stale_entries_are_scanned_in_three_batches(corpus_many, job):
    code, out, record = job("many")
    assert code == 0, out
    assert [n for n in names(record) if n.startswith("scan[")] == ["scan[list]", "scan[1]", "scan[2]", "scan[3]"]
    committed = yaml.safe_load(corpus_many.git("show", f"{record['facts']['branch']}:hiivmind-corpus-test/index.yaml"))["entries"]
    assert len(committed) == 62 and not [e["id"] for e in committed if e["stale"]]
    assert all(e["summary"] == f"The file {e['path']}, scanned." for e in committed if e["id"] != "docs:a.md")   # verify rewrote a.md


def test_when_every_scan_fails_the_entries_are_skipped_with_the_reason(corpus, job):   # Review Focus 2, example 5
    code, out, record = job("scan_fails")
    assert code == 0, out
    assert outcomes(record)["scan"] == "failed" and outcomes(record)["index"] == "done" and outcomes(record)["publish"] == "committed"
    [failure] = record["facts"]["scans_failures"]
    assert failure["item"] == {"source": "docs", "files": ["a.md", "d.md"]} and failure["reason"] == "the test makes every scan fail"
    committed = yaml.safe_load(corpus.git("show", f"{record['facts']['branch']}:hiivmind-corpus-test/index.yaml"))["entries"]
    assert [e["id"] for e in committed if e["stale"]] == ["docs:a.md", "docs:d.md"]   # still stale: the next run scans them again


def test_a_dead_stale_entry_goes_when_no_source_moved(corpus_stale, job):              # Review Focus 1
    corpus_stale.set_last_sha(corpus_stale.upstream_head)   # current; upstream deleted c.md
    corpus_stale.mark_stale("docs:c.md")
    code, out, record = job("dead_stale")
    assert code == 0, out
    assert outcomes(record)["update-sources"] == "current" and "scan[1]" in names(record)
    committed = yaml.safe_load(corpus_stale.git("show", f"{record['facts']['branch']}:hiivmind-corpus-test/index.yaml"))["entries"]
    assert "docs:c.md" not in [e["id"] for e in committed]


def test_after_a_merged_refresh_the_corpus_is_already_current(corpus, job, today):     # Review Focus 3
    code, out, record = job()
    assert code == 0, out
    branch = record["facts"]["branch"]
    corpus.git("push", "-q", "origin", f"{branch}:main")   # the pull request, merged on origin
    code, out, record = job()
    assert code == 0 and "Already current." in out and record["model_calls"] == 0


def test_a_run_crashed_in_verify_resumes_there(corpus, job):                           # Review Focus 5, example 8
    code, out, record = job("crash")
    assert code != 0 and record is None, out   # killed: no record
    run_id = re.match(r"run (\S+)", out).group(1)
    code, out, record = job(resume=run_id)
    assert code == 0, out
    assert [run["node"] for run in record["runs"]] == ["verify", "embed", "publish"]
    assert names(record) == WALK and outcomes(record)["publish"] == "committed"


def test_a_stopped_node_ends_the_run_and_publishes_nothing(corpus, job, today):        # example 7
    code, out, record = job("stop")
    assert code == 0, out
    assert record["end_state"] == "stopped" and names(record)[-1] == "concepts" and "publish" not in names(record)
    assert corpus.git("branch", "--list", f"automated/corpus-refresh-test-{today}*") == ""
    assert corpus.git("status", "--porcelain") != ""   # the changes stay in the working tree
