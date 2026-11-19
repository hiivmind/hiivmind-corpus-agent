"""The topology: the repeated tail is one declared fragment, named by the three sequences that scan."""

from agent_core.contracts.topology import Step


def test_the_tail_is_one_fragment_named_by_three_sequences(instance):                 # ORC-3, ORC-4
    t = instance.topology
    assert set(t.fragments) == {"enrich-and-publish"}
    assert {s for s, d in t.sequences.items() if any(Step("enrich-and-publish") in row.values() for row in d.transitions.values())} == {"refresh", "enrich", "migrate"}


async def test_a_skipped_update_still_publishes(corpus, job):                         # Review Focus 1
    result = await job("update_skipped")
    assert [s["name"] for s in result.steps] == ["checks", "update-sources", "publish"]   # nothing scanned
    assert result.end == "done"
