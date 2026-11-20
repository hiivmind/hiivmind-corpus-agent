"""The topology: the repeated tail is one declared fragment, named by the three sequences that scan."""

from agent_core.contracts.topology import END, Link, Step


def test_the_tail_is_one_fragment_named_by_three_prepared_sequences(instance):                 # ORC-3, ORC-4
    t = instance.topology
    assert set(t.fragments) == {"enrich-and-publish"}
    assert {s for s, d in t.sequences.items() if any(Step("enrich-and-publish") in row.values() for row in d.transitions.values())} == {"refresh-prepared", "enrich-prepared", "migrate-prepared"}


async def test_a_skipped_update_still_publishes(corpus, job):                         # Review Focus 1
    result = await job("update_skipped")
    assert [s["name"] for s in result.steps] == ["prepare-base", "checks", "check-upstream", "update-sources", "publish"]   # nothing scanned
    assert result.end == "done"


def test_the_three_sequences_start_with_prepare_base_and_link_to_their_checks(instance):   # INS-2
    for s in ("refresh", "enrich", "migrate"):
        d = instance.topology.sequences[s]
        assert d.start == Step("prepare-base") and not d.checks
        assert d.transitions["prepare-base"] == {"prepared": Link(f"{s}-prepared"), "failed": END}


def test_no_check_names_prepare_base_or_refresh_needed(instance):                      # INS-17
    for d in instance.topology.sequences.values():
        assert not {c.tool for c in d.checks} & {"prepare_base", "refresh_needed"}


def test_the_checks_that_need_the_prepared_tree_follow_prepare_base(instance):
    seqs = instance.topology.sequences
    assert [c.tool for c in seqs["refresh-prepared"].checks] == ["index_is_v2", "corpus_ready"]
    assert [c.tool for c in seqs["enrich-prepared"].checks] == ["index_is_v2", "corpus_ready", "stale_entries"]
    assert [c.tool for c in seqs["migrate-prepared"].checks] == ["index_is_v1", "sources_handled"]
    assert seqs["refresh-prepared"].start == Step("check-upstream") and seqs["enrich-prepared"].start == Step("checkout-sources")


def test_check_upstream_current_ends_the_run(instance):
    t = instance.topology.sequences["refresh-prepared"].transitions
    assert t["check-upstream"] == {"behind": Step("update-sources"), "current": END, "failed": END}
    assert t["check"]["v1"] == Link("migrate-prepared")
