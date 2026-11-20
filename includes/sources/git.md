   The working copy of a source lives in `.source/<id>/`, which is gitignored and stays between runs, so the clone is paid for once and later runs fetch and compare locally.

   For a large upstream repository, or whenever only `docs_root` matters, the clone is a sparse, blob-filtered one, as steps a to e below make it.

   Never use the GitHub compare API (`gh api repos/<owner>/<repo>/compare/<base>...<head>`) to find the changed files. It stops at 300 files and drops the rest without saying so, so a large documentation refresh would miss files with no error or warning. Always compare locally, with `git diff` inside the clone.

   a. CALL `shell__run` with the command `test -d <clone>/.git && echo cloned || echo missing`, the path written out.
   b. If it printed `missing`, CALL `shell__run` with the command `mkdir -p {{settings.CORPUS_PATH}}/.source && git clone --filter=blob:none --sparse --depth=50 --branch <branch> <repo_url> <clone>`. Then CALL `shell__run` with `git -C <clone> sparse-checkout set --skip-checks '<docs_root>'`, the directory in single quotes: `--skip-checks` lets a directory whose name has `[`, `]`, `*` or `?` in it through (atproto's is `src/app/[locale]`). When the source's `docs_root` is `.` or none, use `git -C <clone> sparse-checkout disable` instead. If a command fails, the source fails.
   c. CALL `shell__run` with the command `git -C <clone> fetch --depth=50 origin <branch>`. If it fails, the source fails.
   d. Make sure the commit the index was built at can be resolved. CALL `shell__run` with `git -C <clone> cat-file -e <last_commit_sha>^{commit}`. If it fails:
      1. CALL `shell__run` with `git -C <clone> rev-parse --is-shallow-repository`. If it prints `false`, the commit is not in the history of the branch: the source fails with the error "commit <last_commit_sha> is not in the history of <branch>".
      2. Otherwise deepen the clone: CALL `shell__run` with `git -C <clone> fetch --shallow-since=<last_indexed_at> origin <branch>`, then try `cat-file -e` again.
      3. If it still fails, CALL `shell__run` with `git -C <clone> fetch --unshallow origin <branch>`, then try `cat-file -e` again. If it still fails, the source fails with the error "commit <last_commit_sha> cannot be resolved, even with the full history".
   e. CALL `shell__run` with `git -C <clone> checkout -q -B <branch> <commit>`, then CALL `shell__run` with `git -C <clone> rev-parse HEAD`. If a command fails, the source fails. Otherwise the source is now checked out, at the commit `rev-parse` printed.
