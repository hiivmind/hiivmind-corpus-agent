# AGENTS.md — hiivmind-corpus-agent

The corpus instance of agent-core, a client of its facade: nodes (`nodes/`), shared prose (`includes/`), tools (`tools/corpus.py`) and the topology (`topology.yaml`, with the fragment `enrich-and-publish`). `hiivmind-corpus-lib` and `hiivmind-agent-core` (branch `rebuild` until the cutover) are checked out beside this repository. The previous tree is in `v0/`.

## Principles

agent-core's principles apply to this instance. Read them before you add, split, merge or change a node, a sequence, a tool or a package capability:

- **Inventory, P1–P18:** `../hiivmind-central/01.principles/hiivmind-agent-core/README.md`.
- **Governance:** `../hiivmind-central/01.principles/hiivmind-agent-core/PRINCIPLES.md`.

The ones that decide most corpus work:

- **P13:** nodes orchestrate, packages supply capabilities, and the harness works between nodes.
- **P14 to P18:** what makes a node; when two situations are one node or two; where each kind of work goes; values a tool computed move by code, not through the model; every node that writes leaves the corpus consistent.

Check a proposed node set or node contract against P13–P18 before it goes to the owner. An instance may narrow a principle, not contradict it.

## Planning

`../hiivmind-central/04.planning/hiivmind-agent-core/`: designs, plans, reviews and build records. Read `../hiivmind-central/AGENTS.md` before you change anything there.
