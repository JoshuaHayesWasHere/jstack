First I follow **End, step 1**: check the checkout against the start note, in one call with the setup block at the top and `S=<slug>`:

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"); H=~/.local/state/home/$R; S=<slug>
echo "There at the start:"; git status --porcelain | grep -Fxf "$H/scouts/$S.start"
echo "New since the start:"; git status --porcelain | grep -Fxvf "$H/scouts/$S.start"
```

I show its output, name any leftover line and whose it is, and correct the report's `Repo:` line if needed. Then step 2 (report and brief on disk), step 3 (tell the home via `t3_thread_send` and write `$S.told`), step 4, and step 5's settle check.
