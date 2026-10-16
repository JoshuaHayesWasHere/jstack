1. I follow **"The checks" → "A failed check"**, the `stale` bullet: no commit, no rerun, no rebase, and no gate.
2. The Result has no `Stale base:` line for this head, so I append this one line to the last Result in `$H/tasks/<slug>.md`:
   `Stale base: at 4b38832b997fdef0cce303119f5d052302604772, check`
3. Then I check whether jbus or `jmerge` has already sent the "A conflict" message for this head, either `main changed <files> after its check started` or `<command> fails on 4b38832… over today's main`.
4. If it has, I run the first block of **"A conflict"** now, with `why='stale'`.
5. If it hasn't, which is the case here, I end my turn and send nothing. That message will wake this thread later.
