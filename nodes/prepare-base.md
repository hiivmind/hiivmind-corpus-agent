---
name: prepare-base
description: Put the corpus repository named in the settings on its base branch, fast-forwarded to origin, so that a run starts from the published state. Refuses a dirty working tree and a base branch that is ahead of origin.
exits: [prepared, failed]
allowed-tools: [shell__run]
context: none
---
# Prepare base

Puts the corpus repository on its base branch, level with origin, before anything else reads or changes it. A run branch is cut from the base branch, so a base branch that holds commits origin does not have would put those commits into the pull request.

Corpus: {{settings.CORPUS_PATH}}. Base branch: {{settings.BASE_BRANCH}}.

A shell command's result has an exit code. A command went well when its exit code is 0; "the command fails" below means its exit code is not 0. Run each command as written, with no time limit added.

A step that ends the node on a failure: EXIT `failed` with output `reason` set to the sentence given.

## Steps

1. CALL `shell__run` with the command `git -C {{settings.CORPUS_PATH}} status --porcelain`. If it fails, EXIT `failed` with `reason` "The corpus repository could not be prepared: git status --porcelain <what it printed>". If it printed anything, EXIT `failed` with `reason` "The corpus repository could not be prepared: the working tree is dirty: <the lines it printed>".
2. CALL `shell__run` with the command `git -C {{settings.CORPUS_PATH}} checkout {{settings.BASE_BRANCH}}`. If it fails, EXIT `failed` with `reason` "The corpus repository could not be prepared: git checkout {{settings.BASE_BRANCH}} <what it printed>".
3. CALL `shell__run` with the command `git -C {{settings.CORPUS_PATH}} fetch --prune origin`. If it fails, EXIT `failed` with `reason` "The corpus repository could not be prepared: git fetch --prune origin <what it printed>".
4. CALL `shell__run` with the command `git -C {{settings.CORPUS_PATH}} merge --ff-only origin/{{settings.BASE_BRANCH}}`. If it fails, EXIT `failed` with `reason` "The corpus repository could not be prepared: git merge --ff-only origin/{{settings.BASE_BRANCH}} <what it printed>".
5. CALL `shell__run` with the command `git -C {{settings.CORPUS_PATH}} rev-list --count origin/{{settings.BASE_BRANCH}}..HEAD`. If it fails, EXIT `failed` with `reason` "The corpus repository could not be prepared: git rev-list --count origin/{{settings.BASE_BRANCH}}..HEAD <what it printed>". If the count it printed is above 0, EXIT `failed` with `reason` "The corpus repository could not be prepared: {{settings.BASE_BRANCH}} has <n> commit(s) that origin/{{settings.BASE_BRANCH}} does not have", `<n>` being the count. (Step 4 succeeds in that case: the merge has nothing to add.)
6. EXIT `prepared`.
