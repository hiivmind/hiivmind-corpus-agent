from pathlib import Path

import hiivmind_corpus

DOCUMENTS = Path(hiivmind_corpus.__file__).parent / "documents"


def test_nothing_in_the_instance_names_a_coding_agent():  # VERB-4a
    for path in [*Path("skills").rglob("*.md"), *DOCUMENTS.rglob("*.md"), Path("topology.yaml"), Path("instance.yaml")]:
        text = path.read_text()
        for word in ("CLAUDE_PLUGIN_ROOT", "AskUserQuestion", "Task tool", "CALL_SKILL", "Write tool", "request_cowork_directory"):
            assert word not in text, f"{path}: {word}"
