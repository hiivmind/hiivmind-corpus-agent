from pathlib import Path

from tests.helpers import sh


def test_nothing_in_the_instance_names_a_coding_agent():  # VERB-4a
    for path in [*Path("skills").rglob("*.md"), *Path("reference").rglob("*.md"), Path("topology.yaml"), Path("instance.yaml")]:
        text = path.read_text()
        for word in ("CLAUDE_PLUGIN_ROOT", "AskUserQuestion", "Task tool", "CALL_SKILL", "Write tool", "request_cowork_directory"):
            assert word not in text, f"{path}: {word}"


def test_the_reference_documents_and_scripts_are_present():
    for name in ("detect.py", "embed.py", "verify_entries.py", "lance_meta.py", "constants.py", "token_utils.py"):
        assert Path("scripts", name).is_file(), name
    for name in ("sources/git.md", "sources/shared.md", "index-updating.md", "index-format-v2.md", "freshness.md",
                 "embeddings.md", "paths.md", "graph.md", "source-scanner.md"):
        assert Path("reference", name).is_file(), name


def test_the_scripts_run_from_the_instance_as_the_procedures_run_them(corpus_stale):
    assert sh("uv run scripts/detect.py").stdout.strip() in ("ready", "no-model", "not-installed")
    c = corpus_stale.path
    r = sh(f"uv run scripts/verify_entries.py --index {c}/index.yaml --source-root {c}/.source/ --config {c}/config.yaml --entries docs:a.md")
    assert r.returncode == 0, r.stdout + r.stderr
