---
name: checkout-sources
description: Check out each git source of the corpus named in the settings at the commit its index was built at, so that the scans can read the files. Changes no index file.
outputs:
  checkouts:
    type: array
    description: one item for each source of config.yaml, in its order
    items:
      type: object
      required: [id, status]
      properties:
        id: {type: string}
        status: {enum: [checked-out, failed]}
        error: {type: string}
  checkout_errors: {type: array, items: {type: string}}
exits: [done, failed]
allowed-tools: [shell__run, files__read_text_file, reference]
context: none
---
# Check out sources

Makes the working copy of each git source match the commit the index was built at, its `last_commit_sha`. The `scan` node reads each file from that working copy, which git does not keep in the corpus repository, so a fresh checkout of the corpus has none. The sources are worked one after another.

Corpus: {{settings.CORPUS_PATH}}.

Keep a list `checkout_errors`, empty to begin with, and one record for each source: `id`, `status` and, for a source that failed, `error`.

A shell command's result has an exit code. A command went well when its exit code is 0; "the command fails" below means its exit code is not 0.

The working copy of a source is `<clone>` = `{{settings.CORPUS_PATH}}/.source/<id>`, where `<id>` is the source's `id`. It is a sparse clone, as the "Sparse Checkout for Large Repositories" section of the `sources/git` document says.

A source that fails does not stop the others: its record is `status: failed` with `error` set to what went wrong, `<id>: <error>` is added to `checkout_errors`, and you go to step 5.

## Steps

1. CALL `files__read_text_file` with the path `{{settings.CORPUS_PATH}}/config.yaml`. If it returns an error, EXIT `failed` with output `checkout_errors` set to a list holding that error, and `checkouts` empty.
2. CALL `reference` with `doc` `sources/git` and `section` `Sparse Checkout for Large Repositories`.
3. Take the first source of `config.yaml`, in its order, that has not been checked out or failed yet.
4. Check out the commit the index was built at: `<commit>` is the source's `last_commit_sha`, as `config.yaml` writes it. When the steps below end with the source checked out, its record is `status: checked-out`.
{{include fragments/sources/git.md}}
5. If a source has not been checked out or failed yet, go to step 3.
6. If a source failed, EXIT `failed`; otherwise EXIT `done`. The outputs are `checkouts` (the records, in the order of `config.yaml`, with `error` only on a source that failed) and `checkout_errors`.
