"""LNG-1 and VERB-4a: the instance's own words. A node is a node, not a skill; a procedure names no SDK."""

import re

import yaml

from tests.helpers import ROOT

PROSE = [*sorted((ROOT / "nodes").glob("*.md")), *sorted((ROOT / "includes").rglob("*.md"))]
WORDS = ("langchain", "langgraph", "anthropic", "openai", "claude")


def _docs_without_v0_runs():
    # The v0 run log is kept unchanged under "## v0 runs" (the last section of README.md) and is not checked.
    readme = (ROOT / "README.md").read_text().split("\n## v0 runs")[0]
    return {ROOT / "README.md": readme, ROOT / "AGENTS.md": (ROOT / "AGENTS.md").read_text()}


def test_nothing_calls_a_node_a_skill():   # LNG-1
    files = [*PROSE, ROOT / "topology.yaml", ROOT / "instance.yaml"]
    assert len(PROSE) == 13
    texts = {path: path.read_text() for path in files} | _docs_without_v0_runs()
    for path, text in texts.items():
        assert "SKILL.md" not in text, path
        assert not re.search(r"skill", text, re.IGNORECASE), path


def test_no_procedure_topology_or_tool_declaration_names_the_sdk():   # VERB-4a
    # `backend: langgraph` is configuration (G9) and is not checked: only `servers` and `tools` of instance.yaml are.
    instance = yaml.safe_load((ROOT / "instance.yaml").read_text())
    texts = {path: path.read_text() for path in [*PROSE, ROOT / "topology.yaml"]}
    texts[ROOT / "instance.yaml#servers+tools"] = yaml.safe_dump({"servers": instance["servers"], "tools": instance["tools"]})
    for path, text in texts.items():
        for word in WORDS:
            assert word not in text.lower(), f"{path}: {word}"
