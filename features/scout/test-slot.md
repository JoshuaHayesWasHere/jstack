- A scout seldom meets a test slot, since a run that writes is a crewmate's.
  A command the request asks you to run under one, `jgauge test-slot --short --thread <thread id> -- <command>`, waits in the call for a short slot for up to 5 minutes, in the order the calls came, and registers nothing: `<thread id>` is this thread's own id, which the `t3-code` server's `t3_thread_configure` with no arguments gives as `threadId` (if your harness defers it, load it first).
  Give the call a time limit of 10 minutes (`timeout: 600000` in Claude Code), since it can wait 5 minutes and then run for the lane's limit.
  With every slot still taken by then nothing ran: it says so in one line and ends 76.
  Run the same command again at once, in this turn: nothing wakes this thread for a short slot, so never end the turn on that 76, and never wait in a background job.
