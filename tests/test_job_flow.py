"""The refresh job, as `agent-core job` runs it, on a corpus in a temporary directory and the scripted backend."""

import os
from datetime import datetime, timedelta, timezone


def test_nothing_to_do_makes_no_model_call(job, corpus):                      # criterion 1
    corpus.set_last_sha(corpus.upstream_head)
    code, out, record = job()
    assert code == 0 and record["summary"]["status"] == "already current" and record["model_calls"] == 0 and record["runs"] == []
    assert corpus.git("branch", "--list", "automated/*") == ""


def test_already_current_still_reports_the_open_pull_requests(job, corpus):
    corpus.set_last_sha(corpus.upstream_head)
    created = (datetime.now(timezone.utc) - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    corpus.set_gh_open_prs([{"number": 7, "createdAt": created}])
    code, out, record = job()
    assert record["summary"]["stale_prs"] == [{"pr_number": 7, "age_days": 4}]


def test_a_refresh_runs_each_stage_in_order_and_commits(job, corpus):
    code, out, record = job()
    assert code == 0 and [r["node"] for r in record["runs"]] == ["refresh", "scan", "enrich"]
    s = record["summary"]
    assert s["status"] == "refreshed" and s["enriched"] == 2 and s["needs_attention"] == [] and s["pr_url"] is None
    assert s["branch"].startswith("automated/corpus-refresh-test-") and corpus.git("log", "-1", "--format=%s").startswith("corpus: refresh ")


def test_the_summary_lists_what_was_enriched_and_what_the_refresh_found(job, corpus):
    code, out, record = job()
    s = record["summary"]
    assert s["enriched_ids"] == ["docs:a.md", "docs:d.md"] and s["skipped"] == 0 and s["skipped_entries"] == []
    assert s["index_changes"] == {"added": 1, "modified": 1, "removed": 1}
    assert [(x["id"], x["status"]) for x in s["sources"]] == [("docs", "updated")]
    assert s["verification"] == {"sampled": 1, "failed": 0, "drift_entries": []} and s["new_concept_candidates"] == []
    assert s["embeddings"] == "skipped" and s["embeddings_lag"] is None and s["superseded_prs"] == [] and s["errors"] == []
    assert s["stale_prs"] == []


def test_the_commit_message_is_the_report(job, corpus):
    code, out, record = job()
    message = corpus.git("log", "-1", "--format=%B")
    assert "Updated: `docs`" in message and "1 added, 1 modified, 1 removed" in message
    assert "Enriched: 2" in message and "Skipped: 0" in message and "Needs attention" not in message


def test_sixty_one_stale_files_are_scanned_in_three_runs(job, corpus_many):    # batches of 30
    code, out, record = job()
    assert [r["node"] for r in record["runs"]].count("scan") == 3


def test_the_scans_run_at_the_same_time(job, corpus_many, tmp_path):           # JOB-8
    barrier = tmp_path / "barrier"      # apart from the run directories, which are called run-<n> too
    barrier.mkdir()
    code, out, record = job("barrier", env={"BARRIER_DIR": str(barrier)})
    assert code == 0
    assert sorted((barrier / f).read_text() for f in os.listdir(barrier) if f.startswith("seen-")) == ["3", "3", "3"]


def test_a_refresh_with_no_result_fails_the_job(job, corpus):
    code, out, record = job("refresh_no_exit")
    assert code == 1 and "refresh did not produce a result: no_exit" in record["summary"]


def test_a_failed_scan_leaves_its_entries_under_needs_attention(job, corpus):
    code, out, record = job("scan_fails")
    s = record["summary"]
    assert code == 0 and s["needs_attention"] == ["docs:a.md", "docs:d.md"] and s["skipped"] == 2 and s["enriched"] == 0
    assert [e["id"] for e in s["skipped_entries"]] == ["docs:a.md", "docs:d.md"]
    assert all(e["reason"] == "no_exit" for e in s["skipped_entries"])
    assert "enrich" not in [r["node"] for r in record["runs"]]
    message = corpus.git("log", "-1", "--format=%B")
    assert "Needs attention" in message and "docs:a.md" in message and "docs:d.md" in message


def test_a_dirty_tree_fails_the_job_before_a_branch_is_made(job, corpus):
    corpus.write("stray.txt", "x")
    code, out, record = job()
    assert code == 1 and "dirty" in record["summary"] and corpus.git("branch", "--list", "automated/*") == ""


def test_a_failed_pre_check_does_not_stop_the_refresh(job, corpus):
    corpus.break_lance_dir()                       # lance_meta.py fails, so corpus_status raises
    code, out, record = job()
    assert code == 0 and record["summary"]["status"] == "refreshed" and any("corpus_status" in e for e in record["summary"]["errors"])



def test_a_refresh_that_commits_nothing_ends_as_no_changes(job, corpus):
    code, out, record = job("nothing_to_refresh")   # the pre-check says behind; the refresh finds nothing to write
    s = record["summary"]
    assert code == 0 and s["status"] == "no changes" and s["enriched"] == 0 and s["needs_attention"] == []
    assert [r["node"] for r in record["runs"]] == ["refresh"]
    assert corpus.git("branch", "--list", "automated/*") == "" and corpus.git("branch", "--show-current") == "main"


def test_the_lag_is_zero_after_an_enrich_that_updates_the_embeddings(job, corpus):
    code, out, record = job("embeddings_updated")   # the refresh deferred the embeddings and reported a lag of 5
    s = record["summary"]
    assert code == 0 and s["embeddings"] == "updated" and s["embeddings_lag"] == 0


def test_the_body_names_each_source_by_what_became_of_it(job, corpus):
    code, out, record = job("mixed_sources")
    message = corpus.git("log", "-1", "--format=%B")
    old, new = corpus.first_sha[:7], corpus.upstream_head[:7]
    assert f"- Updated: `docs` (git): {old} -> {new}, 3 files changed" in message
    assert "- Current: `same` (git)\n" in message
    assert "- Skipped as manual: `wiki` (web): source type `web` is not handled by this instance yet\n" in message
    assert "- Failed: `gone` (git): the tracked commit is gone\n" in message
    assert "- Failed: `odd` (git)\n" in message
    assert "None" not in message
