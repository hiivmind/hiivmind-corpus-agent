---
name: scan
description: Read a batch of a source's files and write the index metadata of each (title, summary, tags, keywords and category). Changes no file.
inputs:
  batch: "the batch to scan: `source`, the id of the source the files belong to, and `files`, the files to scan, as paths relative to the source's docs root"
outputs:
  entries:
    type: array
    description: one entry of metadata for each file of the batch that could be read, in the order of its `files`
    items:
      type: object
      required: [path, title, summary, tags, keywords, category]
      properties:
        path: {type: string, description: the path exactly as it was given in `files`}
        title: {type: string}
        summary: {type: string}
        tags: {type: array, items: {type: string}}
        keywords: {type: array, items: {type: string}}
        category: {enum: [reference, tutorial, guide, api, config, navigation, journal]}
exits: [done, failed]
allowed-tools: [files__read_text_file, files__list_directory, locate_files]
context: none
---
# Scan

Writes the metadata of the index entries of one batch of files. It reads files and changes none. It writes no section entries and no field that code fills in.

Batch: {{input.batch}}.

Below, `<source>` is the batch's `source` and "the files" are its `files`, written out as the batch has them.

## Steps

1. {{include includes/entry-metadata.md}}
   Scan every file of the batch, each one on its own.
2. CALL `locate_files` with `source` `<source>` and `files` the files. It returns one item for each path: `path`, `file` (the full path of the file to read) and `url`. If it returns an error, EXIT `failed` with output `reason` set to the error.
3. For each item, in order, CALL `files__read_text_file` with its `file`. An item whose `file` is null, or whose file cannot be read (the call returned an error), is left out of the entries: do not make one up and do not try it again.
4. For each file read, make one entry with the six fields of "Entry Metadata Generation": `path`, `title`, `summary`, `tags`, `keywords`, `category`. `path` is exactly as it was given in the files, not the full path and not prefixed with the source id. Write no other field.
5. EXIT `done` with output `entries` set to the list of entries from step 4, in the order of the files. When no file could be read the list is empty.

## Errors

| Error | Behaviour |
|-------|-----------|
| `error:` on `locate_files` (step 2) | EXIT `failed` with output `reason` set to the error. |
| `file` null, or `error:` on a file of the batch (step 3) | Leave that file out of the entries and go on with the next file. |
