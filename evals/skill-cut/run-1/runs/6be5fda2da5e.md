**First**, following "The checks" → "A failed check", answer `stale`: append to the last Result in `$H/tasks/<slug>.md` the line
`Stale base: at 4b38832b997fdef0cce303119f5d052302604772, check`
**No gate** is parked. I make no commit, no rerun and no rebase, because a base that moved is not by itself a reason to rebase ("A conflict").
**Then** I look for the message from jbus or `jmerge` for this head: `main changed <files> after its check started`, or `<command> fails on 4b38832… over today's main`.
- **If it has come**, I run the first block of "A conflict" with `why='stale'`.
- **If not**, I end my turn, and that message is what wakes this thread.
