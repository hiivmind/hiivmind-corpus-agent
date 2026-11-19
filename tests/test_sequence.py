"""The sequences through the facade, with the scripted backend over the fixture corpus: the checks are real, every node is
scripted, and every tool call of a script is real. The trail is the macro trail: the fragment `enrich-and-publish` is one step,
and its inner steps are under its entry's `steps`."""

import subprocess
import sys
from pathlib import Path

import yaml

from tests.helpers import ROOT

FRAGMENT = "enrich-and-publish"
TAIL = ["scan[list]", "scan[1]", "scan", "index", "concepts", "verify", "embed", "publish"]
WALK = ["checks", "update-sources", FRAGMENT]
MIGRATE_WALK = ["checks", "checkout-sources", "migrate", FRAGMENT]


def names(result) -> list[str]:
    return [step["name"] for step in result.steps]


def inner(result) -> list[str]:
    """The inner steps of the fragment's trail entry."""
    [entry] = [step for step in result.steps if step["name"] == FRAGMENT]
    return [step["name"] for step in entry["steps"]]


def outcomes(result) -> dict[str, str]:
    """The outcome of every step, the fragment's inner steps too (the fragment's own entry is under its name)."""
    found: dict[str, str] = {}
    for step in result.steps:
        found[step["name"]] = step["outcome"]
        found.update({s["name"]: s["outcome"] for s in step.get("steps", [])})
    return found


async def test_nothing_to_do_makes_no_model_call(corpus, job):             # criterion 1, CRP-2
    corpus.set_last_sha(corpus.upstream_head)
    r = await job()
    assert r.end == "done" and r.summary == "Already current." and r.record.end_state == "done"
    assert names(r) == ["checks"] and outcomes(r)["checks"] == "current"   # no node step: no model call


async def test_a_refresh_walks_every_node_in_order_and_commits(corpus, job, today):
    r = await job()
    assert r.end == "done"
    assert names(r) == WALK and inner(r) == TAIL and outcomes(r)["publish"] == "committed"
    branch = f"automated/corpus-refresh-test-{today}"
    assert corpus.git("branch", "--show-current") == "main" and corpus.git("status", "--porcelain") == ""
    assert corpus.git("log", "-1", "--format=%s", branch) == f"corpus: refresh {today}"
    committed = corpus.git("show", f"{branch}:hiivmind-corpus-test/index.yaml")
    assert "docs:c.md" not in committed and "The file d.md, added in the second commit." in committed
    assert r.facts["enriched_ids"] == ["docs:a.md", "docs:d.md"] and r.facts["scans_failures"] == [] and r.facts["branch"] == branch


async def test_a_dirty_tree_fails_before_any_node(corpus, job):            # example 4
    corpus.write("stray.txt", "x")
    r = await job()
    assert r.end == "failed" and "the working tree is dirty" in r.summary and "stray.txt" in r.summary
    assert r.record.end_state == "failed" and names(r) == ["checks"]


async def test_a_failed_verify_still_publishes(corpus, job):
    r = await job("verify_fails")
    assert r.end == "done"
    assert outcomes(r)["verify"] == "failed" and outcomes(r)["embed"] == "done" and outcomes(r)["publish"] == "committed"


def test_nothing_names_the_deleted_files():
    files = [*Path(ROOT, "nodes").glob("*.md"), *Path(ROOT, "includes").rglob("*.md"), ROOT / "instance.yaml", ROOT / "topology.yaml"]
    assert files
    for file in files:
        text = file.read_text()
        for gone in ("jobs/", "tools/repo.py", "tools/index.py", "tools/status.py", "scripts/", "reference/"):
            assert gone not in text, f"{file.name}: {gone}"


# --- the harder paths (Review Focus 1 to 5, examples 5, 7 and 8) ---------------------------------------------------------

async def test_sixty_two_stale_entries_are_scanned_in_three_batches(corpus_many, job):
    r = await job("many")
    assert r.end == "done"
    assert [n for n in inner(r) if n.startswith("scan[")] == ["scan[list]", "scan[1]", "scan[2]", "scan[3]"]
    committed = yaml.safe_load(corpus_many.git("show", f"{r.facts['branch']}:hiivmind-corpus-test/index.yaml"))["entries"]
    assert len(committed) == 62 and not [e["id"] for e in committed if e["stale"]]
    assert all(e["summary"] == f"The file {e['path']}, scanned." for e in committed if e["id"] != "docs:a.md")   # verify rewrote a.md


async def test_when_every_scan_fails_the_entries_are_skipped_with_the_reason(corpus, job):   # Review Focus 2, example 5
    r = await job("scan_fails")
    assert r.end == "done"
    assert outcomes(r)["scan"] == "failed" and outcomes(r)["index"] == "done" and outcomes(r)["publish"] == "committed"
    [failure] = r.facts["scans_failures"]
    assert failure["item"] == {"source": "docs", "files": ["a.md", "d.md"]} and failure["reason"] == "the test makes every scan fail"
    committed = yaml.safe_load(corpus.git("show", f"{r.facts['branch']}:hiivmind-corpus-test/index.yaml"))["entries"]
    assert [e["id"] for e in committed if e["stale"]] == ["docs:a.md", "docs:d.md"]   # still stale: the next run scans them again


async def test_a_dead_stale_entry_goes_when_no_source_moved(corpus_stale, job):              # Review Focus 1
    corpus_stale.set_last_sha(corpus_stale.upstream_head)   # current; upstream deleted c.md
    corpus_stale.mark_stale("docs:c.md")
    r = await job("dead_stale")
    assert r.end == "done"
    assert outcomes(r)["update-sources"] == "current" and "scan[1]" in inner(r)
    committed = yaml.safe_load(corpus_stale.git("show", f"{r.facts['branch']}:hiivmind-corpus-test/index.yaml"))["entries"]
    assert "docs:c.md" not in [e["id"] for e in committed]


async def test_after_a_merged_refresh_the_corpus_is_already_current(corpus, job, today):     # Review Focus 3
    r = await job()
    assert r.end == "done"
    corpus.git("push", "-q", "origin", f"{r.facts['branch']}:main")   # the pull request, merged on origin
    r = await job()
    assert r.end == "done" and r.summary == "Already current." and names(r) == ["checks"]


async def test_a_run_crashed_in_verify_resumes_there(corpus, job, monkeypatch):               # Review Focus 5, example 8; re-cut
    """The `crash` script kills the process that runs the scripted `verify`, so the first run is a child process of this test;
    the resume is in this one, on the journal the child left. The scripted backend resumes by macro (the core's journal): the
    steps done before the crash are not run again, and the fragment, in flight, runs again from its start as one step."""
    from tests.conftest import INSTANCE_YAML, _scripted

    _scripted(monkeypatch, corpus, "crash")
    program = (
        "import asyncio, sys, agent_core\n"
        "async def main():\n"
        "    async with agent_core.open(sys.argv[1], backend='scripted', settings=[sys.argv[2]], runs=sys.argv[3]) as h:\n"
        "        await h.sequences.run('refresh', {}, run_id='crashed')\n"
        "asyncio.run(main())\n"
    )
    child = subprocess.run(
        [sys.executable, "-c", program, str(INSTANCE_YAML), str(corpus.settings_file), str(corpus.base / "runs")],
        cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    assert child.returncode != 0 and not (corpus.base / "runs" / "crashed" / "record.json").exists(), child.stdout   # killed: no record
    import importlib
    corpus_tools = importlib.import_module("tools.corpus")
    checked = []   # the checks' tools called in this process
    for name in ("prepare_base", "refresh_needed"):
        original = getattr(corpus_tools, name)
        monkeypatch.setattr(corpus_tools, name, lambda *a, _o=original, _n=name, **k: (checked.append(_n), _o(*a, **k))[1])
    r = await job(resume="crashed")
    assert checked == []   # `checks` was not run again
    ran = [note.node for note in r.record.notes]   # the nodes that started in this process
    assert ran == ["index", "concepts", "verify", "embed", "publish"]   # not update-sources; the fragment ran again from its start, its journalled scan units replayed, not run
    assert r.end == "done" and r.run_id == "crashed"
    assert names(r) == WALK and r.steps[1]["outcome"] == "updated"   # the macro trail: the fragment once, as one step
    assert inner(r)[0] == "scan[list]" and inner(r)[-5:] == TAIL[3:] and outcomes(r)["publish"] == "committed"   # verify and on ran in the resume
    assert r.record.end_state == "done"


async def test_a_stopped_node_ends_the_run_and_publishes_nothing(corpus, job, today):        # example 7
    r = await job("stop")
    assert r.end == "stopped" and r.record.end_state == "stopped"
    assert inner(r)[-1] == "concepts" and "publish" not in inner(r) and "publish" not in names(r)
    assert corpus.git("branch", "--list", f"automated/corpus-refresh-test-{today}*") == ""
    assert corpus.git("status", "--porcelain") != ""   # the changes stay in the working tree


async def test_a_failed_index_reaches_publish_with_its_error(corpus, job):                   # final review 2
    r = await job("index_fails")
    assert r.end == "done"
    assert outcomes(r)["index"] == "failed" and outcomes(r)["publish"] == "committed" and "concepts" not in inner(r)
    assert r.facts["index_errors"] == ["merge_scans failed: the test makes the merge fail"]


# --- the job workflows: status, enrich, migrate, graph-validate (design §4.2) ----------------------------------------------

def committed_entries(corpus, r) -> dict[str, dict]:
    text = corpus.git("show", f"{r.facts['branch']}:hiivmind-corpus-test/index.yaml")
    return {e["id"]: e for e in yaml.safe_load(text)["entries"]}


def subject(corpus, r) -> str:
    return corpus.git("log", "-1", "--format=%s", r.facts["branch"])


async def test_status_on_a_stale_corpus(corpus, job):                      # example 1
    r = await job(sequence="status")
    assert r.end == "done"
    assert names(r) == ["status"] and outcomes(r)["status"] == "stale" and r.record.end_state == "done"
    assert r.facts["refresh_needed"] is True and r.facts["sources"][0]["freshness"] == "behind"


async def test_enrich_with_nothing_stale_makes_no_model_call(corpus, job):  # example 2
    r = await job(sequence="enrich")
    assert r.end == "done" and r.summary == "Nothing is stale."
    assert names(r) == ["checks"] and outcomes(r)["checks"] == "nothing-stale"


async def test_enrich_walks_from_checkout_to_publish(corpus_stale, job, today):   # example 3
    r = await job("enrich_ok", sequence="enrich")
    assert r.end == "done"
    assert names(r) == ["checks", "checkout-sources", FRAGMENT] and inner(r) == TAIL
    assert subject(corpus_stale, r) == f"corpus: enrich {today}"
    entries = committed_entries(corpus_stale, r)
    assert entries["docs:b.md"]["stale"] is False and entries["docs:b.md"]["summary"] == "The file b.md, scanned for enrich."


async def test_migrate_walks_and_publishes_a_migration(corpus_v1_bullets, job, today):   # example 4, CJW-1, CJW-3, CJW-11
    r = await job("migrate_ok", sequence="migrate")
    assert r.end == "done"
    assert names(r) == MIGRATE_WALK and inner(r) == TAIL and outcomes(r)["publish"] == "committed"
    entries = committed_entries(corpus_v1_bullets, r)
    assert set(entries) == {"docs:a.md", "docs:b.md"} and not [id for id, e in entries.items() if e["stale"]]
    assert entries["docs:b.md"]["summary"] == "The file b.md, scanned after the migration."
    assert r.facts["migrated"] == 2 and r.facts["strategy"] == "single"   # recorded by the tool (example 7e)
    assert subject(corpus_v1_bullets, r) == f"corpus: migrate {today}"


async def test_refresh_on_a_v1_corpus_links_to_migrate(corpus_v1_bullets, job, today):     # example 5, CJW-2
    r = await job("migrate_ok")
    assert r.end == "done"
    assert r.steps[0]["name"] == "checks" and r.steps[0]["outcome"] == "v1" and "migrate" in names(r)
    assert "update-sources" not in names(r) and subject(corpus_v1_bullets, r) == f"corpus: migrate {today}"


async def test_enrich_on_a_v1_corpus_links_to_migrate(corpus_v1_bullets, job, today):      # CJW-2a
    r = await job("migrate_ok", sequence="enrich")
    assert r.end == "done"
    assert r.steps[0]["outcome"] == "v1" and "migrate" in names(r) and "checkout-sources" in names(r)
    assert subject(corpus_v1_bullets, r) == f"corpus: migrate {today}"


async def test_a_failed_scan_after_migration_keeps_the_v1_entry_and_enrich_picks_it_up(corpus_v1_bullets, job, today):   # 7d, CJW-8
    r = await job("migrate_scan_fails", sequence="migrate")
    assert r.end == "done"
    assert outcomes(r)["scan"] == "failed" and outcomes(r)["publish"] == "committed"
    entries = committed_entries(corpus_v1_bullets, r)
    assert {id: (e["title"], e["summary"], e["stale"]) for id, e in entries.items()} == {
        "docs:a.md": ("Alpha", "The file a.md, in v1.", True), "docs:b.md": ("Beta", "The file b.md, in v1.", True),
    }
    message = corpus_v1_bullets.git("log", "-1", "--format=%B", r.facts["branch"])
    assert "- docs:b.md: the test makes every scan fail" in message
    corpus_v1_bullets.git("push", "-q", "origin", f"{r.facts['branch']}:main")   # the pull request, merged
    corpus_v1_bullets.git("branch", "-D", r.facts["branch"])                      # and its branch deleted
    r = await job("enrich_ok", sequence="enrich")
    assert r.end == "done"
    assert "scan[1]" in inner(r) and not [id for id, e in committed_entries(corpus_v1_bullets, r).items() if e["stale"]]


async def test_migrate_refuses_a_corpus_with_a_web_source(corpus_v1_bullets, job):        # example 6, CJW-6
    corpus_v1_bullets.add_source({"id": "site", "type": "web"})
    r = await job(sequence="migrate")
    assert r.end == "failed" and "The corpus has sources this instance does not handle." in r.summary
    assert names(r) == ["checks"]


async def test_migrate_that_would_lose_ids_ends_failed_and_writes_nothing(corpus_v1_bullets, job):   # example 7, CJW-4
    corpus_v1_bullets.write("sections/extra.md", "See `docs:c.md`.\n")
    corpus_v1_bullets._save("test: an id the parser does not read")
    r = await job("migrate_lost", sequence="migrate")
    assert r.end == "failed", r.summary
    assert names(r)[-1] == "migrate" and outcomes(r)["migrate"] == "failed" and r.record.end_state == "failed"
    assert r.facts["migrate_errors"] == ["ids lost in migration: docs:c.md"]
    assert corpus_v1_bullets.git("status", "--porcelain") == "" and not (corpus_v1_bullets.path / "index.yaml").exists()


async def test_a_source_that_cannot_be_checked_out_ends_the_run(corpus_v1_bullets, job):  # example 7a, CJW-12
    r = await job("checkout_fails", sequence="migrate")
    assert r.end == "failed", r.summary
    assert names(r) == ["checks", "checkout-sources"] and r.record.end_state == "failed"
    assert "cannot be resolved" in r.facts["checkout_errors"][0]
    assert corpus_v1_bullets.git("status", "--porcelain") == "" and not (corpus_v1_bullets.path / "index.yaml").exists()


async def test_graph_validate_on_a_valid_graph(corpus, job):                # example 8
    r = await job(sequence="graph-validate")
    assert r.end == "done"
    assert names(r) == ["checks", "graph-validate"] and outcomes(r)["graph-validate"] == "valid"
    assert r.facts["valid"] is True and r.facts["issues"] == []


async def test_graph_validate_without_a_graph_fails(corpus, job):           # example 9, CJW-13
    (corpus.path / "graph.yaml").unlink()
    corpus._save("test: no graph")
    r = await job(sequence="graph-validate")
    assert r.end == "failed" and "The corpus has no graph.yaml." in r.summary
    assert r.record.end_state == "failed" and names(r) == ["checks"]
