---
name: concepts
description: Assign existing concepts of graph.yaml to the entries just re-scanned that have none, through set_concepts, and report groups that match no concept as candidates. Writes no new concept.
inputs:
  enriched_ids: the ids of the entries just re-scanned
outputs:
  concepts_assigned: {type: integer}
  new_concept_candidates:
    type: array
    description: groups of entries that match no existing concept, for a person to look at; nothing is written to graph.yaml for them
    items:
      type: object
      required: [label, evidence]
      properties:
        label: {type: string}
        evidence: {type: array, items: {type: string}}
  concept_errors: {type: array, items: {type: string}}
exits: [done, failed]
allowed-tools: [files__read_text_file, reference, set_concepts, shell__run]
context: none
---
# Concepts

Assigns existing concepts to the entries the `scan` runs have just written. It never changes an entry's `category` or `section`, and it never writes a new concept: a group of entries that match no concept is reported as a candidate for a person to look at. The concepts are written by `set_concepts`; never edit `index.yaml`.

Corpus: {{settings.CORPUS_PATH}}.
Entries: {{input.enriched_ids}}.

Keep a list `concept_errors`, empty to begin with; `concepts_assigned`, 0 to begin with; `new_concept_candidates`, empty to begin with; and `assignments`, an empty mapping from entry id to concept ids.

When these steps say "the zero result", it is the outputs `concepts_assigned` 0, `new_concept_candidates` empty, and `concept_errors` as they stand.

## Phase 1: Read the index and the graph
Outputs: the target entries, and the concepts there are to assign.

1. If "Entries" reads "not given" or names no id, EXIT `done` with the zero result.
2. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/index.yaml`. If it returns an error, add `index.yaml not read: <error>` to `concept_errors` and EXIT `failed` with outputs `reason` set to the error and `concept_errors`, so that `publish` reports it.
3. The target entries are the entries of `index.yaml` whose `id` is one of the ids in "Entries", in the order of "Entries". An id that has no entry in the index is left out and `<id>: no entry in the index` is added to `concept_errors`. If no target entry is left, EXIT `done` with the zero result.
4. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/graph.yaml`. If it returns an error, or the file has no `concepts` or none in it, there is no concept to assign: EXIT `done` with the zero result. Otherwise CALL `reference` with `doc` `graph` and `section` `Schema Definition`. That section says what a concept is: the id of a concept is its key under `concepts`, and an entry belongs to a concept by having the id in its own `concepts` list.

## Phase 2: Assign concepts
Outputs: `concepts_assigned`, `new_concept_candidates`.

Only the existing concepts of `graph.yaml` are assigned: inventing a concept is a person's decision. Only a target entry whose `concepts` is empty or missing is looked at; a target entry that already has concepts keeps them.

Repeat steps 5 and 6 for each target entry that has no concepts, one after another, in the order of "Entries".

5. Match the entry against each concept of the graph, using the entry's `tags`, `keywords`, `title` and `summary`:
   1. Tag overlap: a tag or keyword of the entry is one of the `tags` of the concept.
   2. Description match: words of the concept's `label` or `description` appear in the entry's title or summary.

   The entry gets every concept that has at least one signal of each of the two kinds, or at least two tag overlaps from the first alone. An entry may get several concepts. If no concept qualifies, the entry is unmatched: go on to the next entry.
6. The entry has concepts. Add the entry's id to `assignments`, with the list of the ids of its concepts.
7. When every such entry has been looked at, group the unmatched entries, those of step 5 that no concept qualified for. Make the groups in this order: first the directory groups, one for each directory of the entries' `path`, taken in the order of the directory paths; then the tag groups, one for each tag the entries have, taken in the order of the tags. A `path` with no directory (a file at the root of its source, directory `.`) forms no directory group. An entry stays in the first group it joins and is left out of the later ones. Each group of three entries or more is then a new concept candidate: `label` a name for the group proposed from its directory or its tag, `evidence` the ids of its entries. Add them to `new_concept_candidates`. Do not write them to `graph.yaml`.
8. If `assignments` is empty, go to step 10.
9. CALL `set_concepts` with `assignments`, every entry in one call. Set `concepts_assigned` to the `assigned` it returns. If it returns an error, add `index update failed: <error>` to `concept_errors` and go to step 10. Otherwise render the index; the node's error list is `concept_errors`. {{include fragments/render-index.md}}
10. EXIT `done` with outputs `concepts_assigned`, `new_concept_candidates` and `concept_errors`.

## Errors

| Error | Behaviour |
|-------|-----------|
| `error:` on `index.yaml` (step 2) | EXIT `failed` with the error in `reason` and in `concept_errors`. |
| `error:` on `graph.yaml` (step 4) | There is no concept to assign: EXIT `done` with the zero result. |
| `set_concepts` returns an error (step 9) | Add `index update failed: <error>` to `concept_errors`; nothing is assigned. |
| `render-index.sh` exits with a code that is not 0 (step 9) | Add `index.md not rendered: <error>` to `concept_errors`. |
