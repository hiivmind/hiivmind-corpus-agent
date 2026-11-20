---
name: check-upstream
description: Decide whether the corpus named in the settings is behind its sources or needs other work - a stale entry or lagging embeddings. Looks at each source's upstream head; changes nothing.
exits: [behind, current, failed]
allowed-tools: [shell__run, files__read_text_file, corpus_status]
context: none
---
# Check upstream

Finds out whether a refresh has anything to do. `corpus_status` decides: a refresh is needed when a source is behind or unknown, an entry is stale, or the embeddings lag.

Corpus: {{settings.CORPUS_PATH}}.

A shell command's result has an exit code. A command went well when its exit code is 0.

## Steps

1. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/config.yaml`. If it returns an error, EXIT `failed` with output `reason` set to the error.
2. Look at the upstream of each source.
{{include includes/sources/upstream-head.md}}
3. CALL `corpus_status` with `observed`. If it returns an error, EXIT `failed` with output `reason` set to the error.
4. If its `refresh_needed` is `true`, EXIT `behind`. Otherwise EXIT `current` with output `reason` "Already current.".
