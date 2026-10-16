Next is **End, step 1**: check the checkout against the note taken at the start. I run this in one call, with the setup block (`R`, `H`, `T`) at the top and `S` set to the slug:

```sh
echo "There at the start:"; git status --porcelain | grep -Fxf "$H/scouts/$S.start"
echo "New since the start:"; git status --porcelain | grep -Fxvf "$H/scouts/$S.start"
```

If a line is left, I name it and whose it is, and fix the report's `Repo:` line to match. Then step 2: I confirm the report and brief are on disk. Step 3: the `home-id` block, then `t3_thread_send`, then the `cksum > $S.told` note. Steps 4 and 5 follow, ending with the settle check.
