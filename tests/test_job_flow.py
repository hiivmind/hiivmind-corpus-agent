"""The refresh job, as `agent-core job` runs it, on a corpus in a temporary directory and the scripted backend."""

import os
import subprocess
from datetime import date, datetime, timedelta, timezone

import yaml


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


def _yesterday() -> str:
    return (date.today() - timedelta(days=1)).isoformat() + "T00:00:00Z"


def test_the_lag_is_read_again_after_an_enrich_that_leaves_no_model(job, corpus):
    corpus.make_lance(_yesterday())   # the embeddings are newer than every entry: lag 0 before the refresh
    code, out, record = job("embeddings_no_model")
    s = record["summary"]
    assert code == 0 and s["embeddings"] == "no-model" and s["enriched_ids"] == ["docs:a.md", "docs:d.md"]
    assert s["embeddings_lag"] == 2   # the two entries `apply_scan` has just indexed
    assert "\n- no-model, lag 2" in corpus.git("log", "-1", "--format=%B")


def test_the_lag_is_not_guessed_to_be_zero_when_the_enrich_says_updated(job, corpus):
    corpus.make_lance(_yesterday())   # the script says "updated" and leaves the embeddings as they were
    code, out, record = job("embeddings_updated")
    assert code == 0 and record["summary"]["embeddings"] == "updated" and record["summary"]["embeddings_lag"] == 2


def test_without_embeddings_there_is_no_lag_figure(job, corpus):
    code, out, record = job("embeddings_updated")
    assert code == 0 and record["summary"]["embeddings"] == "updated" and record["summary"]["embeddings_lag"] is None


def test_an_unknown_source_is_not_already_current(job, corpus):
    corpus.set_last_sha(corpus.upstream_head)
    corpus.set_repo_url("/nowhere")             # the pre-check cannot read the upstream: refresh_needed is false, nothing is known
    code, out, record = job("nothing_to_refresh")
    s = record["summary"]
    assert code == 0 and s["status"] == "no changes" and [r["node"] for r in record["runs"]] == ["refresh"]
    assert any("/nowhere" in e for e in s["errors"]) and any("freshness unknown for `docs`" in e for e in s["errors"])


def test_the_body_says_index_md_may_be_stale_when_the_enrich_did_not_finish(job, corpus):
    code, out, record = job("enrich_fails")
    message = corpus.git("log", "-1", "--format=%B")
    assert code == 0 and "enrich" in [r["node"] for r in record["runs"]] and record["summary"]["errors"]
    assert "`index.md` may be out of step with `index.yaml`" in message


def test_the_body_does_not_say_so_when_the_enrich_finished(job, corpus):
    code, out, record = job()
    assert "out of step" not in corpus.git("log", "-1", "--format=%B")


def test_a_body_lists_at_most_fifty_ids_in_each_list():
    from jobs.refresh import _body
    report = {
        "sources": [], "index_changes": {"added": 0, "modified": 0, "removed": 0}, "removed_ids": [f"docs:r{i}.md" for i in range(60)], "enriched": 0,
        "skipped": 120, "skipped_entries": [{"id": f"docs:s{i}.md", "reason": "r"} for i in range(120)],
        "verification": {"sampled": 1, "failed": 60, "drift_entries": [f"docs:d{i}.md" for i in range(60)]},
        "new_concept_candidates": [], "embeddings": "skipped", "embeddings_lag": None,
        "errors": [f"error {i}" for i in range(51)], "needs_attention": [f"docs:n{i}.md" for i in range(200)],
    }
    body = _body(report)
    assert "- Removed 60 entries whose files are gone from the source\n" in body
    assert "- Removed 1 entry whose file is gone from the source\n" in _body({**report, "removed_ids": ["docs:r0.md"]})
    assert body.count("`docs:r") == 50 and "docs:r49.md" in body and "docs:r50.md" not in body and "  - and 10 more\n" in body.split("- Enriched")[0]
    assert "Removed" not in _body({**report, "removed_ids": []})
    assert body.count("docs:s") == 50 and "  - and 70 more\n" in body and "docs:s49.md" in body and "docs:s50.md" not in body
    assert body.count("drift: ") == 50 and "  - and 10 more\n" in body
    assert body.count("`docs:n") == 50 and "- and 150 more\n" in body
    assert body.count("- error ") == 50 and "- and 1 more\n" in body
    exactly = _body({**report, "skipped_entries": report["skipped_entries"][:50], "removed_ids": []})
    assert exactly.count("docs:s") == 50 and "  - and" not in exactly.split("## Verification")[0]


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


def test_an_entry_whose_file_is_gone_from_the_source_is_removed_by_the_job(job, corpus):
    corpus.add_entry({"id": "docs:gone.md", "source": "docs", "path": "gone.md", "stale": False})   # no such file upstream, before or after
    code, out, record = job()
    s = record["summary"]
    assert code == 0 and s["status"] == "refreshed" and s["removed_ids"] == ["docs:gone.md"]
    assert [r["node"] for r in record["runs"]] == ["refresh", "scan", "enrich"] and s["needs_attention"] == []
    assert "docs:gone.md" not in (corpus.path / "index.yaml").read_text()
    message = corpus.git("log", "-1", "--format=%B")
    assert "- Removed 1 entry whose file is gone from the source\n  - `docs:gone.md`\n" in message


def test_a_refresh_that_removes_no_entry_says_nothing_of_it(job, corpus):
    code, out, record = job()
    assert record["summary"]["removed_ids"] == [] and "whose files are gone" not in corpus.git("log", "-1", "--format=%B")


def test_a_source_the_refresh_did_not_clone_loses_no_entry(job, corpus):
    corpus.add_entry({"id": "docs:gone.md", "source": "docs", "path": "gone.md", "stale": False})
    code, out, record = job("nothing_to_refresh")   # the refresh ends without a checkout of `docs`: its entries are not looked at
    assert code == 0 and record["summary"]["removed_ids"] == [] and not (corpus.path / ".source").exists()
    assert [e["id"] for e in yaml.safe_load((corpus.path / "index.yaml").read_text())["entries"]] == ["docs:a.md", "docs:b.md", "docs:c.md", "docs:gone.md"]


def _checkout_at_head(corpus) -> None:
    """The working copy of the source, a repository at the upstream's head: what a refresh that went well leaves."""
    subprocess.run(["git", "clone", "-q", str(corpus.upstream), str(corpus.path / ".source" / "docs")], check=True)


def test_a_removal_with_nothing_to_scan_still_leaves_index_yaml_and_index_md_in_step(job, corpus):
    _checkout_at_head(corpus)
    corpus.add_entry({"id": "docs:gone.md", "source": "docs", "path": "gone.md", "stale": False})   # c.md is gone upstream too
    assert "`docs:c.md`" in (corpus.path / "index.md").read_text()
    code, out, record = job("refresh_removal_only")
    s = record["summary"]
    assert code == 0 and [r["node"] for r in record["runs"]] == ["refresh"] and s["status"] == "refreshed"
    assert s["removed_ids"] == ["docs:c.md", "docs:gone.md"]
    index = yaml.safe_load((corpus.path / "index.yaml").read_text())
    assert [e["id"] for e in index["entries"]] == ["docs:a.md", "docs:b.md"] and index["meta"]["entry_count"] == 2
    index_md = (corpus.path / "index.md").read_text()
    assert "`docs:c.md`" not in index_md and "`docs:a.md`" in index_md and "Entries: 2 " in index_md
    message = corpus.git("log", "-1", "--format=%B")
    assert "- Removed 2 entries whose files are gone from the source\n  - `docs:c.md`\n  - `docs:gone.md`\n" in message
    assert corpus.git("status", "--porcelain") == ""   # the removal is in the commit, index.md with it
    assert set(corpus.git("show", "--name-only", "--format=", "HEAD").splitlines()) >= {
        f"{corpus.path.name}/index.yaml", f"{corpus.path.name}/index.md",
    }


def test_a_source_the_refresh_reports_failed_loses_no_entry_though_its_checkout_is_at_the_head(job, corpus):
    _checkout_at_head(corpus)
    corpus.add_entry({"id": "docs:gone.md", "source": "docs", "path": "gone.md", "stale": False})
    code, out, record = job("refresh_source_failed")   # the script records the head as `last_commit_sha`: only the status holds the entries
    assert code == 0 and record["summary"]["removed_ids"] == []
    assert [e["id"] for e in yaml.safe_load((corpus.path / "index.yaml").read_text())["entries"]] == ["docs:a.md", "docs:b.md", "docs:c.md", "docs:gone.md"]


def test_a_refresh_that_did_not_end_done_drops_nothing(job, corpus):
    _checkout_at_head(corpus)
    corpus.add_entry({"id": "docs:gone.md", "source": "docs", "path": "gone.md", "stale": False})
    code, out, record = job("refresh_not_done")   # it reports the source `updated`, and the checkout is at the head
    assert code == 0 and record["summary"]["removed_ids"] == [] and "the refresh gave up" in record["summary"]["errors"]
    assert "docs:gone.md" in (corpus.path / "index.yaml").read_text()
