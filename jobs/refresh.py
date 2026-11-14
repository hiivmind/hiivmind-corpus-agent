"""The refresh job: bring a corpus up to date with its sources and commit the result on a branch.

The template's `refresh-headless` as a script. The steps of the repository and of the index are functions; the three model
steps are nodes: `refresh` (sources and index structure), `scan` (the metadata of the stale files, in batches that run at the
same time) and `enrich` (concepts, verification, embeddings). A pull request is opened by `repo_finish` when `PUSH` is true.
"""

import asyncio
from datetime import date

from agent_core.core.node_runner import NodeRunError

BATCH = 30   # files for one scan run


def _batches(by_source: dict[str, list[str]]) -> list[tuple[str, list[str]]]:
    return [(source, files[i:i + BATCH]) for source, files in by_source.items() for i in range(0, len(files), BATCH)]


def _reason(result: dict, what: str) -> str:
    """Why a node run did not end `done`: the harness's `reason`, else the one the node gave, else its outcome."""
    return result.get("reason") or (result.get("outputs") or {}).get("reason") or f"{what} ended {result.get('outcome')}"


def _stale_prs(branches: list[dict]) -> list[dict]:
    return [{"pr_number": b["pr_number"], "age_days": b["pr_age_days"]} for b in branches if b.get("pr_number") is not None]


def _detail(source: dict) -> str:
    """What follows a source's name in the body: the commits and the file count of an updated source, the error of a failed one."""
    if source.get("status") == "updated":
        return f": {source.get('old_sha')} -> {source.get('new_sha')}, {source.get('files_changed')} files changed"
    return f": {source['error']}" if source.get("error") else ""


def _body(report: dict) -> str:
    sources = report["sources"]
    lines = ["## Sources", ""]
    for heading, status in (("Updated", "updated"), ("Current", "current"), ("Failed", "failed"), ("Skipped as manual", "skipped-manual")):
        for source in (s for s in sources if s.get("status") == status):
            lines.append(f"- {heading}: `{source.get('id')}` ({source.get('type')})" + _detail(source))
    if not sources:
        lines.append("- none looked at")
    changes = report["index_changes"]
    lines += [
        "", "## Index", "",
        f"- {changes['added']} added, {changes['modified']} modified, {changes['removed']} removed",
        f"- Enriched: {report['enriched']}",
        f"- Skipped: {report['skipped']}",
    ]
    lines += [f"  - `{s['id']}`: {s['reason']}" for s in report["skipped_entries"]]
    verification = report["verification"]
    lines += ["", "## Verification", ""]
    if verification is None:
        lines.append("- not run")
    else:
        lines.append(f"- Sampled {verification.get('sampled')}, failed {verification.get('failed')}")
        lines += [f"  - drift: `{e}`" for e in verification.get("drift_entries") or []]
    lines += ["", "## New concept candidates (for the reviewer's decision)", ""]
    candidates = report["new_concept_candidates"]
    lines += [f"- {c.get('label')}: {', '.join(c.get('evidence') or [])}" for c in candidates] or ["- none"]
    lag = report["embeddings_lag"]
    lines += ["", "## Embeddings", "", f"- {report['embeddings']}" + ("" if lag is None else f", lag {lag}")]
    if report["errors"]:
        lines += ["", "## Errors", ""] + [f"- {e}" for e in report["errors"]]
    if report["needs_attention"]:
        lines += ["", "## Needs attention", "", "Entries still marked stale:"] + [f"- `{e}`" for e in report["needs_attention"]]
    return "\n".join(lines) + "\n"


async def main(job) -> dict:
    prep = await job.call("repo_prepare", {})   # a RepoError ends the job: the template's ABORT
    stale_prs = _stale_prs(prep["stale_branches"])
    errors: list[str] = []

    try:   # the pre-check saves a branch and a model run; it is never a gate
        status = await job.call("corpus_status", {})
        if not status["refresh_needed"] and status["embeddings_lag"] in (0, None):
            return {"status": "already current", "stale_prs": stale_prs}
    except Exception as e:
        errors.append(f"corpus_status failed: {type(e).__name__}: {e}")

    branch = (await job.call("repo_branch", {}))["branch"]

    refresh = await job.run_node("refresh", {"sources": "all"})
    if "reason" in refresh:   # the harness could not get a result: an invalid refresh result is fatal
        raise RuntimeError(f"refresh did not produce a result: {refresh['reason']}")
    found = refresh.get("outputs") or {}
    if refresh["outcome"] != "done":
        errors.append(_reason(refresh, "refresh"))
    errors += found.get("errors") or []
    changes = found.get("index_changes") or {}
    embeddings, lag = found.get("embeddings", "skipped"), found.get("embeddings_lag")

    enriched: list[str] = []
    skipped: list[dict] = []
    verification, candidates = None, []
    stale = await job.call("stale_files", {})
    if stale["entry_ids"]:   # the index says what to scan, not the refresh's report
        batches = _batches(stale["by_source"])
        runs = await asyncio.gather(
            *(job.run_node("scan", {"source": source, "files": files}) for source, files in batches), return_exceptions=True,
        )
        scans = []
        for (source, files), run in zip(batches, runs):
            if isinstance(run, NodeRunError):
                scans.append({"source": source, "files": files, "entries": [], "error": str(run)})
            elif isinstance(run, BaseException):   # a tool server that cannot be reached, or anything unforeseen
                raise run
            elif run["outcome"] == "done":
                scans.append({"source": source, "files": files, "entries": run["outputs"]["entries"], "error": None})
            else:
                scans.append({"source": source, "files": files, "entries": [], "error": _reason(run, "scan")})
        merged = await job.call("apply_scan", {"scans": scans})
        enriched, skipped = merged["enriched"], merged["skipped"]
        if enriched:
            enrich = await job.run_node("enrich", {"entries": enriched})
            result = enrich.get("outputs") or {}
            if enrich["outcome"] != "done":
                errors.append(_reason(enrich, "enrich"))
            errors += result.get("errors") or []
            verification = result.get("verification")
            candidates = result.get("new_concept_candidates") or []
            if "embeddings" in result:   # the later of the two
                embeddings = result["embeddings"]
                lag = 0 if embeddings == "updated" else lag

    needs_attention = (await job.call("stale_files", {}))["entry_ids"]   # whatever is still stale, from any cause

    summary = {
        "branch": branch,
        "sources": found.get("sources") or [],
        "index_changes": {key: changes.get(key, 0) for key in ("added", "modified", "removed")},
        "enriched": len(enriched), "enriched_ids": enriched,
        "skipped": len(skipped), "skipped_entries": skipped,
        "needs_attention": needs_attention,
        "verification": verification, "new_concept_candidates": candidates,
        "embeddings": embeddings, "embeddings_lag": lag,
        "errors": errors,
    }
    finish = await job.call("repo_finish", {
        "branch": branch, "title": f"corpus: refresh {date.today().isoformat()}", "body": _body(summary),
        "stale_branches": prep["stale_branches"],
    })
    return {
        "status": "refreshed" if finish["has_changes"] else "no changes",
        "stale_prs": stale_prs,
        **summary,
        "pr_url": finish["pr_url"], "superseded_prs": finish["superseded_prs"],
    }
