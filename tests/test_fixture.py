"""The fixture corpus is built through the package."""

from hiivmind_corpus_lib import Config, Graph, Index
from hiivmind_corpus_lib import Corpus as Package

from tests.helpers import ROOT


def test_the_fixture_files_are_canonical(corpus):                      # INS-9, CAN-2
    for name, kind in (("config.yaml", Config), ("index.yaml", Index), ("graph.yaml", Graph)):
        text = (corpus.path / name).read_text()
        assert kind.loads(text).dumps() == text, name


def test_index_md_is_what_the_package_renders(corpus):                 # INS-9, REN-1
    assert (corpus.path / "index.md").read_text() == Package.open(corpus.path).render.texts()["index.md"]


def test_a_v1_fixture_has_the_v1_files_only(corpus_v1_bullets):
    assert not (corpus_v1_bullets.path / "index.yaml").exists()
    assert Package.open(corpus_v1_bullets.path).status.index_format() == "v1"


def test_the_fixture_writes_no_yaml_or_markdown_by_hand():             # INS-9
    text = (ROOT / "tests" / "corpus_fixture.py").read_text()
    assert "safe_dump" not in text and "def _render" not in text and "render-index" not in text
