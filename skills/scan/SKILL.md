---
name: scan
description: Read a batch of a source's files and write the index metadata of each (title, summary, tags, keywords, category and the rest). Changes no file.
inputs:
  source: the id of the source the files belong to
  files: the files to scan, as paths relative to the source's docs root
outputs:
  entries:
    type: array
    description: one entry of metadata for each file that could be read, in the order of `files`
    items:
      type: object
      required: [path, title, summary, tags, keywords, category, content_type, size, grep_hint, headings]
      properties:
        path: {type: string, description: the path exactly as it was given in `files`}
        title: {type: string}
        summary: {type: string}
        tags: {type: array, items: {type: string}}
        keywords: {type: array, items: {type: string}}
        category: {enum: [reference, tutorial, guide, api, config, navigation, journal]}
        content_type: {enum: [markdown, yaml, json, rst, text]}
        size: {enum: [standard, large]}
        grep_hint: {type: [string, "null"]}
        headings:
          type: array
          items:
            type: object
            required: [anchor, title]
            properties:
              anchor: {type: string}
              title: {type: string}
exits: [done, failed]
allowed-tools: [files__read_text_file, files__list_directory, shell__run]
context: none
---
# Scan

Writes the metadata of the index entries of one batch of files. It reads files and changes none. It writes no section entries: a section entry under a re-scanned file keeps its line range until the next build.

Inputs: source `{{input.source}}`; files `{{input.files}}`.

## Steps

1. CALL `load` with the path `reference/source-scanner.md`. Its section "Entry Metadata Generation" says how each of the ten fields is made; use only that section. Ignore its sampling strategy: scan every file of the batch, each one on its own. Ignore its sections on section entries and chunks.
2. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/config.yaml`. Find the source whose `id` is `{{input.source}}` and take its `docs_root`. If the source is not in the file, EXIT `failed` with output `reason` saying the source is not in `config.yaml`.
3. The working copy of a git source is `{{settings.CORPUS_PATH}}/.source/{{input.source}}/` and a file is at `<docs_root>/<path>` under it, where `<path>` is a path of `files`. A `docs_root` of `.` or none means the files are directly under it. (This rule is the one of `reference/paths.md`, "Resolve Source Reference to File".)
4. For each path in the files, in order, CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/.source/{{input.source}}/<docs_root>/<path>`. A file that cannot be read (the call returned an error) is left out of the entries: do not make one up and do not try it again. To count the lines of a long file, CALL `shell__run` with the command `wc -l <full path>`, the full path of the file written out.
5. For each file read, make one entry with these ten fields, from "Entry Metadata Generation":
   - `path`: exactly as it was given in the files, not the full path and not prefixed with the source id;
   - `title`, `summary`, `tags`, `keywords`, `category`, `content_type`, `size`, `grep_hint`, `headings`.

   `grep_hint` is a search command with `FILE` where the file goes for a `large` file, and `null` for a `standard` one. `headings` are `{anchor, title}` pairs, the anchor being the slug of the heading text. Write no other field and no section entries.
6. EXIT `done` with output `entries` set to the list of entries from step 5, in the order of the files. When no file could be read the list is empty.

## Errors

| Error | Behaviour |
|-------|-----------|
| `error:` on the config file (step 2) | EXIT `failed` with output `reason` set to the error. |
| `error:` on a file of the batch (step 4) | Leave that file out of the entries and go on with the next file. |
