---
name: migrate
description: Migrate the v1 index (index.md and index-*.md) of the corpus named in the settings to index.yaml, every entry stale, and render it. The scans that follow write each entry's metadata.
outputs:
  migrated: {type: integer}
  migrate_skipped:
    type: array
    items:
      type: object
      required: [id, reason]
      properties:
        id: {type: string}
        reason: {type: string}
  strategy: {enum: [single, tiered]}
  sections: {type: array, items: {type: string}}
  migrate_errors: {type: array, items: {type: string}}
exits: [migrated, failed]
allowed-tools: [migrate_index]
context: none
---
# Migrate

Converts the corpus's v1 index to `index.yaml`. `migrate_index` parses the v1 files, writes each entry stale with its v1 title and summary, renders the index, and checks that no id of the original files is lost; it records its figures in this node's outputs itself. When it refuses, every file is as it was.

Corpus: {{settings.CORPUS_PATH}}.

## Steps

1. CALL `migrate_index`. If it returns an error, EXIT `failed` with output `migrate_errors` set to a list holding the error as it reads.
2. EXIT `migrated`. Give no outputs: the call recorded them.
