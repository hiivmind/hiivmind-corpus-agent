---
name: enrich
description: Assign existing concepts to the entries just re-scanned, check a sample of their summaries against the files, then save the index, render it and embed it. Writes no new concept.
inputs:
  entries: the ids of the entries just re-scanned
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
  verification:
    type: object
    required: [sampled, failed, drift_entries]
    properties:
      sampled: {type: integer}
      failed: {type: integer}
      drift_entries: {type: array, items: {type: string}}
  embeddings: {enum: [updated, skipped, no-model, not-installed]}
  errors: {type: array, items: {type: string}}
exits: [done, failed]
allowed-tools: [shell__run, files__read_text_file, files__edit_file, files__write_file]
context: none
---
# Enrich

Finishes the entries the `scan` node has just written. The scans have already replaced their title, summary, tags, keywords, category and the rest, and `apply_scan` has cleared their `stale` flags. This node assigns existing concepts to the entries that have none, checks a sample of the summaries against the files, writes the index, renders `index.md` and brings the embeddings up to date. It never changes an entry's `category` or `section`, and it never writes a new concept: a group of entries that match no concept is reported as a candidate for a person to look at.

Corpus: {{settings.CORPUS_PATH}}.
Entries: {{input.entries}}.

Keep a list `errors`, empty to begin with; `concepts_assigned`, 0 to begin with; and `new_concept_candidates`, empty to begin with.

A shell command's result has an exit code. A command went well when its exit code is 0; "the command fails" below means its exit code is not 0.

When these steps say "the zero result", it is the outputs `concepts_assigned` 0, `new_concept_candidates` empty, `verification` with `sampled` 0, `failed` 0 and `drift_entries` empty, `embeddings` `skipped`, and `errors` as they stand.

## Phase 1: Read the index and the graph
Outputs: the target entries, and the concepts there are to assign.

1. If "Entries" reads "not given" or names no id, EXIT `done` with the zero result.
2. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/index.yaml`. If it returns an error, EXIT `failed` with output `reason` set to the error.
3. The target entries are the entries of `index.yaml` whose `id` is one of the ids in "Entries", in the order of "Entries". An id that has no entry in the index is left out and `<id>: no entry in the index` is added to `errors`. If no target entry is left, EXIT `done` with the zero result.
4. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/graph.yaml`. If it returns an error, or the file has no `concepts` or none in it, there is no concept to assign: go to step 8. Otherwise CALL `load` with the path `reference/graph.md`. Its section "Schema Definition" says what a concept is: the id of a concept is its key under `concepts`, and an entry belongs to a concept by having the id in its own `concepts` list.

## Phase 2: Assign concepts
Outputs: `concepts_assigned`, `new_concept_candidates`.

Only the existing concepts of `graph.yaml` are assigned: inventing a concept is a person's decision. Only a target entry whose `concepts` is empty or missing is looked at; a target entry that already has concepts keeps them.

Repeat steps 5 and 6 for each target entry that has no concepts, one after another, in the order of "Entries".

5. Match the entry against each concept of the graph, using the entry's `tags`, `keywords`, `title` and `summary`:
   1. Tag overlap: a tag or keyword of the entry is one of the `tags` of the concept.
   2. Description match: words of the concept's `label` or `description` appear in the entry's title or summary.

   The entry gets every concept that has at least one signal of each of the two kinds, or at least two tag overlaps from the first alone. An entry may get several concepts. If no concept qualifies, the entry is unmatched: go on to the next entry.
6. The entry has concepts. With `files__edit_file` on `{{settings.CORPUS_PATH}}/index.yaml`, set the entry's `concepts` to the list of the ids of its concepts. The old text is the shortest exact text of the file that holds the entry's `- id: <id>` line and its `concepts` field, which is every line from the one to the other, so that it appears once. When the entry has no `concepts` field, the old text runs from its `- id: <id>` line through its `keywords` field, and the new text is that text with a `concepts` field added after the keywords. Add one to `concepts_assigned`. If the edit fails, add `index update failed: <error>` to `errors`, do not count the entry, and go on.
7. When every such entry has been looked at, group the unmatched entries, those of step 5 that no concept qualified for (an entry whose edit failed in step 6 is not one of them). Make the groups in this order: first the directory groups, one for each directory of the entries' `path`, taken in the order of the directory paths; then the tag groups, one for each tag the entries have, taken in the order of the tags. A `path` with no directory (a file at the root of its source, directory `.`) forms no directory group. An entry stays in the first group it joins and is left out of the later ones. Each group of three entries or more is then a new concept candidate: `label` a name for the group proposed from its directory or its tag, `evidence` the ids of its entries. Add them to `new_concept_candidates`. Do not write them to `graph.yaml`.

## Phase 3: Verify the summaries
Outputs: `verification`.

8. Take the first ten target entries, in the order of "Entries", or all of them when there are fewer: the sample.
9. CALL `shell__run` with the command `uv run scripts/verify_entries.py --index {{settings.CORPUS_PATH}}/index.yaml --source-root {{settings.CORPUS_PATH}}/.source/ --config {{settings.CORPUS_PATH}}/config.yaml --entries "<ids>"`, `<ids>` being the ids of the sample joined with commas and no spaces, kept inside the double quotes. If the command fails, verification is best-effort: add `verification not run: <error>` to `errors`, set `verification` to `sampled` 0, `failed` 0 and `drift_entries` empty, and go to step 12.
10. The command printed a JSON list with one item for each entry: `entry_id`, `title`, `summary`, `source_path` and `content_preview`. An item whose `content_preview` is null cannot be judged: add `<entry_id>: no content preview` to `errors` and leave it out. Set `sampled` to the number of items left, `failed` to 0 and `drift_entries` to empty.
11. Repeat for each item left, one after another: judge whether its `summary` accurately describes its `content_preview`. If it does, go on to the next item. If it does not, write a new summary from the preview alone and, with `files__edit_file` on `{{settings.CORPUS_PATH}}/index.yaml`, replace the entry's summary. The old text is the shortest exact text of the file that holds the entry's `- id: <id>` line and its `summary` field, which is every line from the one to the other, so that it appears once. Write the new summary in double quotes, with `"` and `\` escaped, when YAML needs it: when it holds `:` or `#`, or starts with a special character such as `-`, `?`, `[`, `{`, `&`, `*`, `!`, `|`, `>`, `'`, `"`, `%`, `@` or a backtick. Add one to `failed`. If the edit succeeds, add the entry's id to `drift_entries`; if it fails, add `index update failed: <error>` to `errors`.

## Phase 4: Save, render and embed
Outputs: `embeddings`.

12. CALL `shell__run` with the command `date -u +%Y-%m-%dT%H:%M:%SZ`. That is "now". Then CALL `shell__run` with the command `yq '.entries | length' {{settings.CORPUS_PATH}}/index.yaml`.
13. With `files__edit_file` on `{{settings.CORPUS_PATH}}/index.yaml`, set `meta.generated_at` to now and `meta.entry_count` to the number the command printed; the old text is the two lines of the `meta` block that hold them. If the edit fails, add `index update failed: <error>` to `errors`.
14. CALL `shell__run` with the command `cd {{settings.CORPUS_PATH}} && bash ./render-index.sh index.yaml`. If its exit code is not 0, add `index.md not rendered: <error>` to `errors`, set `embeddings` to `skipped` and go to step 18: an index that was not rendered is not embedded.
15. CALL `load` with the path `reference/embeddings.md`. Its section "Dependency Detection" is used here.
16. CALL `shell__run` with the command `test -d {{settings.CORPUS_PATH}}/index-embeddings.lance && echo present || echo absent`. If it printed `absent`, set `embeddings` to `skipped` and go to step 18.
17. CALL `shell__run` with the command `uv run scripts/detect.py`.
    - It prints `ready`: CALL `shell__run` with `uv run scripts/embed.py {{settings.CORPUS_PATH}}/index.yaml {{settings.CORPUS_PATH}}/index-embeddings.lance/`. This embeds again only the entries whose text changed. If its exit code is 0, set `embeddings` to `updated`; otherwise set it to `skipped` and add `embedding failed: <error>` to `errors`.
    - It prints `no-model`: set `embeddings` to `no-model`. Never download the model here.
    - It prints `not-installed`: set `embeddings` to `not-installed`.
    - It prints anything else, or nothing: set `embeddings` to `skipped` and add `detect.py printed <output>` to `errors`, `<output>` being what it printed or `nothing`.
18. EXIT `done` with outputs `concepts_assigned`, `new_concept_candidates`, `verification`, `embeddings` and `errors`.

## Errors

| Error | Behaviour |
|-------|-----------|
| `error:` on `index.yaml` (step 2) | EXIT `failed` with output `reason` set to the error. |
| `error:` on `graph.yaml` (step 4) | There is no concept to assign: go to step 8. |
| An edit of the index fails (steps 6, 11, 13) | Add `index update failed: <error>` to `errors` and go on; what was saved stays saved. |
| `verify_entries.py` fails (step 9) | Add `verification not run: <error>` to `errors`; verification is best-effort. |
| `render-index.sh` exits with a code that is not 0 (step 14) | Add `index.md not rendered: <error>` to `errors`, set `embeddings` to `skipped` and go to step 18. |
| `detect.py` prints something other than the three statuses (step 17) | `embeddings` is `skipped`; add `detect.py printed <output>` to `errors`. |
| `embed.py` fails (step 17) | `embeddings` is `skipped`; add `embedding failed: <error>` to `errors`. |
