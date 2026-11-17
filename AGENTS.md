# AGENTS.md — hiivmind-corpus-agent

The corpus instance of agent-core: the corpus nodes (`skills/`), sequences (`topology.yaml`), thin tools (`tools/corpus.py`) and the corpus capabilities package (`packages/corpus-lib/`). Its planning and principles live in `hiivmind-central`, checked out beside this repository, under the project `hiivmind-agent-core`.

## Principles

agent-core's principles apply to this instance. Read them before you add, split, merge or change a node, a sequence, a tool or a package capability:

- **Inventory of every principle, P1–P18:** `../hiivmind-central/01.principles/hiivmind-agent-core/README.md` ([on GitHub](https://github.com/hiivmind/hiivmind-central/blob/main/01.principles/hiivmind-agent-core/README.md)).
- **How they are governed:** `../hiivmind-central/01.principles/hiivmind-agent-core/PRINCIPLES.md`.

The ones that decide most corpus work:

- **P13:** nodes orchestrate, packages supply capabilities, and the harness works between nodes.
- **P14 to P18:** what makes a node; when two situations are one node or two (for example, `index` merges scans and `design-index` designs a new index); where each kind of work goes; values a tool computed move by code, not through the model; and every node that writes leaves the corpus consistent.

Check a proposed node set or node contract against P13–P18 before it goes to the owner, and name the principle that settles each boundary. An instance may narrow a principle, not contradict it.

## Planning

`../hiivmind-central/04.planning/hiivmind-agent-core/`: designs, plans, reviews and build records under `superpowers/`, and the backlog in `a.backlog/BACKLOG_INDEX.md`. Read `../hiivmind-central/AGENTS.md` before you change anything there. `PORT.md` records where this instance's procedures, scripts and documents came from.
