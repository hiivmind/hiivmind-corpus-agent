"""The nodes of the instance, run with the scripted backend: each node's contract."""


def test_scan_declares_its_contract(instance):
    node = instance.nodes["scan"]
    assert set(node.inputs) == {"source", "files"}
    assert node.outputs["entries"]["type"] == "array"
    assert node.outputs["entries"]["items"]["required"] == [
        "path", "title", "summary", "tags", "keywords", "category", "content_type", "size", "grep_hint", "headings",
    ]
    assert node.exits == ("done", "failed") and node.context == "none"
    assert node.allowed_tools == ("files__read_text_file", "files__list_directory", "shell__run")


async def test_scan_contract(corpus_stale, run):
    assert (await run("scan", {"source": "docs", "files": ["a.md"]}))["outcome"] == "done"
    assert (await run("scan", {"source": "docs", "files": ["a.md"]}, case="scan_bad"))["reason"] == "invalid_output"   # an entry without summary, twice


async def test_scan_returns_the_entry_the_script_wrote_for_the_file(corpus_stale, run):
    result = await run("scan", {"source": "docs", "files": ["a.md"]})
    [entry] = result["outputs"]["entries"]
    assert entry["path"] == "a.md" and entry["content_type"] == "markdown" and entry["size"] == "standard"
