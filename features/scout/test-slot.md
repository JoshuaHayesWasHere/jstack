- A scout seldom meets a test slot, since a run that writes is a crewmate's.
  A command the request asks you to run under one, `jgauge test-slot --short --thread <thread id> -- <command>`, does not wait: `<thread id>` is this thread's own id, which the `t3-code` server's `t3_thread_configure` with no arguments gives as `threadId` (if your harness defers it, load it first).
  With every slot taken it registers this thread as a waiter and ends 76.
  Then end your turn with one line, `Waiting on a test slot: jbus will wake this thread when one is free.`, and run the same command again when jbus wakes you.
  Never poll for a slot, never wait in a background job, and never end the turn with nothing said.
  On a machine with no jbus nothing wakes a waiter: leave `--thread <thread id>` off, and the call waits in place.
