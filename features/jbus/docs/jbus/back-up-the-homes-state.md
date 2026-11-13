# Back up the homes' state

The homes' state tree, `~/.local/state/home` (the config's `home_dir`), can be a git repo, and then `jbus-snapshot.timer` backs it up at 08:30 and 17:30 local time.
The backup is optional.
The install enables the timer only once the tree has a remote and gitleaks is on the machine.
It has `Persistent=true`, so a snapshot time that the machine slept through runs as soon as the machine is up again.
The timer runs `jbus-snapshot.service`, which runs `jbus snapshot`:

1. It stages everything in the tree (`git add -A`).
   With nothing staged it commits nothing, and goes on to the push.
2. gitleaks reads what is staged (`gitleaks protect --staged`).
   If gitleaks finds a secret, or gitleaks is not on the machine, the snapshot unstages it all, commits nothing, and fails.
   With a remote and no gitleaks, `jinstall --doctor` says `needs gitleaks` on its `state repo` line.
3. It commits as `snapshot <YYYY-MM-DD HH:MM zone>`, in your time zone, followed by `: <text>` when `--why <text>` is given.
4. It pushes to `origin`, whether or not it committed, so a commit whose push failed goes out with the next snapshot.
   It then prints `snapshot: committed, pushed` or `snapshot: nothing changed, pushed`.
   In a tree with no `origin`, the commit stays in the tree, so you can still undo an edit back to it.
   The snapshot then succeeds with `snapshot: committed, not pushed: <tree> has no origin, so the backup is off`, or `snapshot: nothing changed, not pushed: ...` when nothing changed.

The backup needs two things a fresh install does not have: a private repository of yours as the remote, which nothing else pushes to, and gitleaks on the machine.
Without them the timer stays off, and nothing alerts.
To turn the backup on, install gitleaks, then make the tree a repo with its remote:

```sh
git init ~/.local/state/home
git -C ~/.local/state/home remote add origin <url>
jinstall
```

`jinstall` enables the timer once both are there.
`jinstall --doctor` prints the backup as `ok optional state repo <tree> -> <url>`, or says `not a git repo`, `no remote, so the backup is off`, or `needs gitleaks`.
To turn it off again, remove the remote, `git -C ~/.local/state/home remote remove origin`, and run `jinstall`.

A snapshot that did not finish fails the unit and raises its own alert.
When gitleaks found a secret, the alert is for the project whose home holds the file, the first path segment of each file gitleaks names, and only that project's home hears of it.
Any other failure is the machine's, and goes to the desk and the infra home.
The first failure alerts at once, and the later ones in the same run of failures do not alert ([When jbus fails](when-jbus-fails.md)).
A snapshot that is stopped before its end, as the unit's timeout stops one, cannot raise its alert itself, so the next pass of jbus raises it, as the machine's.
The first snapshot that finishes after them says it recovered.
A snapshot that fails only for other projects ends the alert of a project whose files it read clean.

A failed run also reaches you on `jbus needs`, as one item on the infra project's list and its root home's, whatever the cause: a secret gitleaks found, a push that failed, a run the timeout stopped.
It reads `infra jbus-snapshot.service, the state backup, has failed since <YYYY-MM-DD HH:MM zone>; its last line: snapshot: <why>`, with the time of the first run that failed and the line the last failed run wrote to the journal.
A later run that fails too gives the item its own last line, and adds no second item.
Nothing you say clears it: fix what its last line names, and the next snapshot that succeeds removes it.
A run that fails on a real secret still commits nothing.
`systemctl --user list-timers jbus-snapshot.timer` shows when the next snapshot runs on Linux, and `git -C ~/.local/state/home log -1` shows the last one.
To take one now, run `systemctl --user start jbus-snapshot.service` on Linux, or `jbus snapshot` on macOS.
