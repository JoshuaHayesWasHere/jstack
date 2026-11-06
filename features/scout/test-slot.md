- A scout seldom meets a test slot, since a run that writes is a crewmate's.
  A command the request asks you to run under one, `jgauge test-slot --short --thread <thread id> -- <command>`, waits in the call for a short slot for up to the lane's time limit: `<thread id>` is this thread's own id, which the `t3-code` server's `t3_thread_configure` with no arguments gives as `threadId` (if your harness defers it, load it first).
  Give the call a time limit of 10 minutes (`timeout: 600000` in Claude Code), since it can wait the lane's limit and then run as long again.
  With every slot still taken by then it registers this thread as a waiter and ends 76.
  Then end your turn with one line, `Waiting on a test slot: jbus will wake this thread when one is free.`, and run the same command again when jbus wakes you.
  Never poll for a slot, never wait in a background job, and never end the turn with nothing said.
  On a machine with no jbus nothing wakes a waiter: leave `--thread <thread id>` off, and the call waits in place.
