"""The `status` and `migrate` sequences with a model, on corpora built in a temporary directory (see `test_refresh_job.py` for
how to run them). Nothing leaves the machine: `PUSH` is false."""

import pytest
import yaml

pytestmark = pytest.mark.model


def test_status_on_the_fixture_corpus(corpus, run_job):
    ran = run_job(corpus, sequence="status")
    assert ran.code == 0 and ran.record.get("end_state") == "done", ran.why()
    assert ran.outcome("status") == "stale" and ran.facts["refresh_needed"] is True, ran.why()
    assert ran.facts["sources"] == [{"id": "docs", "type": "git", "freshness": "behind"}], ran.facts


def test_migrate_on_a_v1_fixture_corpus(corpus_v1_tiered, run_job, today):
    corpus = corpus_v1_tiered
    ran = run_job(corpus, sequence="migrate")
    assert ran.code == 0 and ran.record.get("end_state") == "done", ran.why()
    assert ran.outcome("migrate") == "migrated" and ran.outcome("publish") == "committed", ran.why()
    branch = ran.record["summary"]["branch"]
    entries = {e["id"]: e for e in yaml.safe_load(corpus.git("show", f"{branch}:hiivmind-corpus-test/index.yaml"))["entries"]}
    assert set(entries) == {"docs:a.md", "docs:b.md"} and not [id for id, e in entries.items() if e["stale"]], entries
    assert all(e["category"] != "unknown" for e in entries.values()), entries   # the scans wrote the metadata
    assert corpus.git("log", "-1", "--format=%s", branch) == f"corpus: migrate {today}"
    assert corpus.git("branch", "--show-current") == "main" and corpus.git("status", "--porcelain") == ""
