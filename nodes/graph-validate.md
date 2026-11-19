---
name: graph-validate
description: Check graph.yaml of the corpus named in the settings against the graph rules, and report the issues. Changes nothing.
outputs:
  concepts: {type: integer}
  relationships: {type: integer}
  issues:
    type: array
    items:
      type: object
      required: [severity, rule, detail]
      properties:
        severity: {enum: [error, warning]}
        rule: {type: string}
        detail: {type: string}
  valid: {type: boolean}
exits: [valid, invalid, failed]
allowed-tools: [validate_graph]
context: none
---
# Graph validate

Checks `graph.yaml` against the rules of the graph: its schema, the concepts the entries of `index.yaml` name, the ends of each relationship, concepts no entry names, and the vocabularies of relationship types and origins. `validate_graph` records what it finds in this node's outputs itself.

Corpus: {{settings.CORPUS_PATH}}.

## Steps

1. CALL `validate_graph`. If it returns an error, EXIT `failed` with output `reason` set to the error.
2. If its `valid` is `true`, EXIT `valid`; otherwise EXIT `invalid`. Give no outputs: the call recorded them.
