- A proof that runs on GitHub Actions, a run you start yourself (the macOS nightly, a browser run, any `gh workflow run`), takes most of an hour, and nothing wakes this thread when it ends unless jbus is told.
  So once the run has started, take its id (`gh run list --workflow <file> --limit 1 --json databaseId --jq '.[0].databaseId'`, right after `gh workflow run`), and register the wait in this worktree, with the block at the top and the run's id and this thread's own id in place of the words in angle brackets:

  ```sh
  uv run --project "$T/../source" jbus run-wait <run id> --thread <thread id>
  ```

  `<thread id>` is this thread's own id: the `t3-code` server's `t3_thread_configure` with no arguments gives it as `threadId`.
- On `waiting:`, end your turn at once, with one line: `Waiting on GitHub run <run id>: jbus will wake this thread when it ends.`
  Never poll the run, never `gh run watch`, and never write a Result that says the run is in progress: while the wait is registered your row reads `waiting on GitHub run <run id> (<workflow>)`, and is never stale.
  jbus asks GitHub for the run once a pass, and sends this thread one message once it has ended, with its conclusion and its page: that message is the wake. On it, read the run's result and go on with the task from there.
- On `ended:`, the run is over already and nothing is registered: read it now and go on.
- On `refused:`, GitHub does not know that run in this repo: check the id, and register again.
- On a machine with no jbus (`refused: no config at` or `refused: no project`), nothing wakes this thread: wait on the run in this turn with `gh run watch <run id> --exit-status`, under a time limit.
