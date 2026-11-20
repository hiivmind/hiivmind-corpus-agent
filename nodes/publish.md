---
name: publish
description: Commit the corpus's changes on a new branch, and, when pushing is on, push it, open the pull request and close the ones it supersedes; then return to the base branch. Commits only the corpus.
inputs:
  sources: what update-sources found for each source
  index_changes: the counts of entries added, modified and removed
  removed_ids: the ids removed because their files are gone
  excluded_paths: the paths left out of the index by build.skip_sections
  enriched_ids: the ids of the entries the scans updated
  skipped_entries: the entries skipped, each with its reason
  index_errors: the problems of the index node
  scans_failures: the scan runs that did not end done, with their batch and reason
  concepts_assigned: how many entries got concepts
  new_concept_candidates: groups of entries that match no concept
  verification: the sample of summaries checked
  embeddings: what happened to the embeddings
  embeddings_lag: how many entries the embeddings lag behind
  update_errors: the problems of update-sources
  concept_errors: the problems of concepts
  verify_errors: the problems of verify
  embed_errors: the problems of embed
  migrated: how many entries the migration wrote
  migrate_skipped: the v1 entries the migration skipped, each with its reason
  strategy: how the migrated index is rendered, single or tiered
outputs:
  branch: {type: [string, "null"]}
  pr_url: {type: [string, "null"]}
  superseded_prs: {type: array, items: {type: integer}}
exits: [published, committed, nothing-to-publish, failed]
allowed-tools: [shell__run, files__write_file, stale_entries]
context: none
---
# Publish

Publishes what the run changed in the corpus: a commit on a new branch made from the working changes and, when pushing is on, a pull request. It commits only the corpus directory. Whatever happens, the working tree goes back to the base branch at the end, except after a failure.

Corpus: {{settings.CORPUS_PATH}}.
Repository on GitHub: {{settings.CORPUS_REPO}}.
Base branch: {{settings.BASE_BRANCH}}.
Branch prefix: {{settings.BRANCH_PREFIX}}.
Push: {{settings.PUSH}}.

What the nodes before this one reported (each reads "not given" when that node did not report it):
- Sources: {{input.sources}}
- Index changes: {{input.index_changes}}
- Removed because their files are gone: {{input.removed_ids}}
- Excluded by `build.skip_sections` (no entry added): {{input.excluded_paths}}
- Enriched: {{input.enriched_ids}}
- Skipped: {{input.skipped_entries}}
- Scan runs that failed: {{input.scans_failures}}
- Concepts assigned: {{input.concepts_assigned}}
- New concept candidates: {{input.new_concept_candidates}}
- Verification: {{input.verification}}
- Embeddings: {{input.embeddings}}, lag {{input.embeddings_lag}}
- Errors of update-sources: {{input.update_errors}}
- Errors of index: {{input.index_errors}}
- Errors of concepts: {{input.concept_errors}}
- Errors of verify: {{input.verify_errors}}
- Errors of embed: {{input.embed_errors}}
- Migrated: {{input.migrated}}, rendered {{input.strategy}}
- Skipped in the migration: {{input.migrate_skipped}}

Every `git` and `gh` command below is run with `timeout 120` before it, as written; each `git` command runs in the corpus directory, by `-C {{settings.CORPUS_PATH}}`. A shell command's result has an exit code. A command went well when its exit code is 0; "the command fails" below means its exit code is not 0. When a command fails and the step says nothing else, EXIT `failed` with output `reason` set to the command and what it printed.

## Phase 1: Check
Outputs: whether there is anything to publish.

1. CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} status --porcelain -- .`. If it prints nothing, the corpus has no change: EXIT `nothing-to-publish` with outputs `branch` null, `pr_url` null and `superseded_prs` empty.
2. If "Push" is `False`, go to step 6.
3. CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} remote get-url --push origin`. When the URL it prints is a GitHub repository (`github.com/<owner>/<name>`, by https or ssh, with or without `.git`), and `<owner>/<name>` is not `{{settings.CORPUS_REPO}}` (compared without regard to case), EXIT `failed` with output `reason` set to "origin is <owner>/<name> but CORPUS_REPO is {{settings.CORPUS_REPO}}: nothing was pushed". A URL that is a path or another host is not checked.
4. Find the earlier refresh branches this one supersedes. CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} for-each-ref --format='%(refname:short)' refs/remotes/origin/`. Take each name `origin/{{settings.BRANCH_PREFIX}}-<rest>` whose `<rest>` is a date `YYYY-MM-DD`, alone or followed by `-<number>`; a longer prefix, as `{{settings.BRANCH_PREFIX}}ing-…`, is another prefix.
5. For each branch of step 4, without `origin/`, CALL `shell__run` with the command `timeout 120 gh pr list --repo {{settings.CORPUS_REPO}} --head <branch> --state open --json number,createdAt`. Keep the `number` of each pull request it lists: those are the superseded pull requests.

## Phase 2: Branch and commit
Outputs: `branch`.

6. CALL `shell__run` with the command `date +%Y-%m-%d`. That is "today".
7. CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} for-each-ref --format='%(refname:short)' refs/heads refs/remotes/origin`. The branch is `{{settings.BRANCH_PREFIX}}-<today>`; when that name, or `origin/` and that name, is in the list, it is `{{settings.BRANCH_PREFIX}}-<today>-2`, then `-3` and so on, the first that is not.
8. CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} checkout -b <branch>`.
9. CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} add -A -- .`, which stages the corpus directory only.
10. CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} rev-parse --show-prefix`; it prints the corpus directory relative to the repository's root (nothing when the corpus is the root). Then CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} diff --cached --name-only`. If a path it prints does not start with that prefix, EXIT `failed` with output `reason` set to "staged outside {{settings.CORPUS_PATH}}, nothing was committed: <the paths>".
11. CALL `stale_entries`: the ids still stale, for "Needs attention".
12. Write the message. Its first line is the title, which names the work from what the nodes reported, the first rule that holds: `corpus: migrate <today>` when Migrated is given (it does not read "not given"); `corpus: refresh <today>` when Sources is given; otherwise `corpus: enrich <today>`. Then an empty line; then the body, in Markdown, in these sections, each list showing at most 50 items and then a line `- and <n> more`:
    - `## Migration`, only when Migrated is given: `- Migrated: <migrated> entries (<strategy>)`, then `- Skipped: <n>` with each entry skipped in the migration and its reason.
    - `## Sources`: one line for each source, `- <Updated|Current|Failed|Skipped as manual>: `<id>` (<type>)`, and for an updated source `: <old_sha> -> <new_sha>, <files_changed> files changed`, for a failed or skipped one `: <error>`; `- none looked at` when there is none.
    - `## Index`: `- <added> added, <modified> modified, <removed> removed`; `- Removed <n> entries whose files are gone from the source` with their ids, when there are any; `- Excluded by build.skip_sections: <n>` and the paths, left out when none; `- Enriched: <n>` with the ids of the entries enriched; `- Skipped: <n>` with each skipped entry and its reason, and each failed scan run with its files and reason.
    - `## Verification`: `- Sampled <sampled>, failed <failed>` and each drift entry, or `- not run`.
    - `## New concept candidates (for the reviewer's decision)`: each candidate's label and evidence, or `- none`.
    - `## Embeddings`: `- <embeddings>`, and `, lag <n>` when the lag is a number.
    - `## Errors`: every error of every node, each on its own line, with the name of the node; leave the section out when there is none.
    - `## Needs attention`: "Entries still marked stale:" and the ids of step 11; leave the section out when there is none.

    A value that reads "not given" is written as "not given". CALL `shell__run` with the command `mktemp`; it prints a file name. CALL `files__write_file` with that path and the message.
13. CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} commit -q -F <the message file>`.
14. If "Push" is `False`, CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} checkout {{settings.BASE_BRANCH}}`, and EXIT `committed` with outputs `branch`, `pr_url` null and `superseded_prs` empty. Nothing is pushed, no pull request is opened and none is closed.

## Phase 3: Push and open the pull request
Outputs: `pr_url`, `superseded_prs`.

15. CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} push -u origin <branch>`.
16. Write the body alone, the message of step 12 without its title and the empty line after it, to a second file the same way: CALL `shell__run` with `mktemp`, then `files__write_file`. CALL `shell__run` with the command `timeout 120 gh pr create --repo {{settings.CORPUS_REPO}} --base {{settings.BASE_BRANCH}} --head <branch> --title "<the title>" --body-file <the body file>`, the title of step 12 written out. The last word it prints is the pull request's URL, `pr_url`. If it prints none, EXIT `failed` with output `reason` set to "gh pr create printed no pull request URL; the branch <branch> is pushed".
17. For each superseded pull request of step 5, in order, CALL `shell__run` with the command `timeout 120 gh pr close <number> --repo {{settings.CORPUS_REPO}} --comment "Superseded by <pr_url> (regenerated from current upstream)." --delete-branch`. If it fails, EXIT `failed` with output `reason` set to what it printed, then "; the new pull request is <pr_url>; pull requests already closed: " and the numbers closed so far, or "none".
18. CALL `shell__run` with the command `timeout 120 git -C {{settings.CORPUS_PATH}} checkout {{settings.BASE_BRANCH}}`.
19. EXIT `published` with outputs `branch`, `pr_url` and `superseded_prs`, the numbers of step 17.

## Errors

| Error | Behaviour |
|-------|-----------|
| origin is another GitHub repository (step 3) | EXIT `failed`: "origin is … but CORPUS_REPO is …: nothing was pushed". |
| A file staged outside the corpus (step 10) | EXIT `failed`: "staged outside …, nothing was committed: …". |
| A `git` or `gh` command fails or times out | EXIT `failed` with the command and what it printed; the branch stays as it is. |
| Closing a superseded pull request fails (step 17) | EXIT `failed` naming the new pull request and the ones already closed. |
