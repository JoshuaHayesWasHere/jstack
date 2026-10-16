I don't start any subagents. "The reviewer" says this thread "starts no subagent and no other thread", and step 3, "The reading", says "Start no `Agent` call and no thread for it", however large the diff is.

What I do first: send the block of steps 1 and 2 under "The review" whole, as a foreground call with a 600000 ms limit. It goes with the block at the top, with only `<slug>` and `<url>` filled in. It prints the path, `$D/prompt.md`.

Then, for step 3, I read that prompt file myself from its first line to its last, in parts with `Read` (`offset`/`limit`) because it is long. I open whatever code the diff calls or is called by, and change nothing.

Before step 4 I write the list down myself: one line per finding, or "no findings".
