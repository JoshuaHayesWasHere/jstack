- While you work, run only the tests that cover the files you change, never the whole suite, in the short lane of the test slots. Run this in this worktree, with the block at the top and the tests in place of the words in angle brackets (in a Python repo, `uv run pytest <those test files>`):

  ```sh
  uv run --project "$T/../source" jgauge test-slot --short --thread <thread id> -- <the targeted tests>
  ```

  The short lane has slots of its own, which no full suite takes, so a targeted run never waits behind one.
  A run still going at the lane's time limit (`jgauge test-slot --help` gives it) is stopped, exit 124, and says so: run fewer files at once.
  The check of the change runs here too, one step to a call, and its block runs a step the lane stopped again alone in a full test slot, as "Do the task" says.

  `<thread id>` is this thread's own id: the `t3-code` server's `t3_thread_configure` with no arguments gives it as `threadId` (if your harness defers it, load it first).
  With `--thread` the call waits for no slot.
  When every slot of the lane is taken it registers this thread as a waiter, prints one line saying so, and ends 76.
  Then end your turn at once, with one line: `Waiting on a test slot: jbus will wake this thread when one is free.`
  Never poll for a slot, never loop on the call, never wait in a background job, and never end the turn with nothing said: `jbus poll` sends this thread one message when a slot of the lane is free, and that message is the wake.
  On it, run the same command again.
  If the slots are taken again by then, the call registers this thread again and you stop again: each wait is woken once.
  On a machine with no jbus nothing wakes a waiter: leave `--thread <thread id>` off, and the call waits in place.

  Every suite you run, a targeted one or the whole one, goes through `jgauge test-slot --thread <thread id>` with this thread's own id, and never runs outside a slot.
  The slot then records the run as this thread's, and while it holds the slot jbus counts this thread as at work and sends its home no leftover for it.
  A turn that ends while that run still holds the slot ends with one line: `My test run holds a slot: jbus will wake this thread when it ends.`
  jbus's message that the run ended, which names the command and its exit code, is the cue to read what the run printed and go on.
