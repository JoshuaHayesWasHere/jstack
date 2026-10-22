# Back up the homes' state

The homes' state tree, `~/.local/state/home` (the config's `home_dir`), is a git repo, and `jbus-snapshot.timer` backs it up at 08:30 and 17:30 local time.
The backup is optional: the install enables the timer only once the tree has a remote and gitleaks is on the machine, and with no remote nothing alerts.
It has `Persistent=true`, so a time the machine slept through runs as soon as it is up again.
The timer runs `jbus-snapshot.service`, which runs `jbus snapshot`:

1. It stages everything in the tree (`git add -A`). With nothing staged it commits nothing, and goes on to the push.
2. gitleaks reads what is staged (`gitleaks protect --staged`).
   A secret in it, or no gitleaks on the machine, unstages it all, commits nothing, and fails the snapshot.
   With a remote and no gitleaks, `install.sh --doctor` says `needs gitleaks` on its `state repo` line.
3. It commits as `snapshot <YYYY-MM-DD HH:MM zone>`, in your time zone, followed by `: <text>` when `--why <text>` is given.
   A home runs `jbus snapshot --why` right after each edit to a `standing.md`, so each edit is a commit of its own: "Undo an edit to standing.md" in [state.md](../../../home/docs/state.md) undoes one.
4. It pushes to `origin`, whether or not it committed, so a commit whose push failed goes with the next snapshot, and prints `snapshot: committed, pushed` or `snapshot: nothing changed, pushed`.
   A tree with no `origin` keeps the commit, which an edit can still be undone to, and succeeds with `snapshot: committed, not pushed: <tree> has no origin, so the backup is off`.

The remote is a private repository of yours, which nothing else pushes to.
Set it once with `git -C ~/.local/state/home remote add origin <url>`.
`install.sh --doctor` prints it as `ok optional state repo <tree> -> <url>`, or says `not a git repo`, `no remote, so the backup is off`, or `needs gitleaks`.
Run `sh install.sh` once the remote is set, and it enables the timer.

A snapshot that did not finish fails the unit, whose `OnFailure=jbus-snapshot-failed.service` runs `jbus snapshot --alarm`.
The first one alerts at once, and the next ones in the same run of failures alert no more ([When jbus fails](when-jbus-fails.md)).
The first snapshot that finishes after them says it recovered.
`systemctl --user list-timers jbus-snapshot.timer` shows when the next snapshot runs, and `git -C ~/.local/state/home log -1` the last one.
To take one now, run `systemctl --user start jbus-snapshot.service`.
