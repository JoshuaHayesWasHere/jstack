# Back up the homes' state

The homes' state tree, `~/.local/state/home` (the config's `home_dir`), can be a git repo, and then `jbus-snapshot.timer` backs it up at 08:30 and 17:30 local time.
The backup is optional.
The install enables the timer only once the tree has a remote and gitleaks is on the machine.
It has `Persistent=true`, so a snapshot time that the machine slept through runs as soon as the machine is up again.
The timer runs `jbus-snapshot.service`, which runs `jbus snapshot`:

1. It reads each project's `standing.md`, the home's and each scoped home's, before it stages anything.
   A `standing.md` holds at most 3 numbered rules, and each rule names `Code: <slug>`, a row of the project's queue that turns it into code.
   A file over the cap, a rule with no `Code:`, or a slug in no row of the queue is refused.
   It prints `snapshot: refused, left out: <project>: <file> <which rule and why>` on stderr for each refused file.
2. It stages everything in the tree but each refused `standing.md` (`git add -A`).
   With nothing staged it commits nothing, and goes on to the push.
3. gitleaks reads what is staged (`gitleaks protect --staged`).
   If gitleaks finds a secret, or gitleaks is not on the machine, the snapshot unstages it all, commits nothing, and fails.
   With a remote and no gitleaks, `jinstall --doctor` says `needs gitleaks` on its `state repo` line.
4. It commits as `snapshot <YYYY-MM-DD HH:MM zone>`, in your time zone, followed by `: <text>` when `--why <text>` is given.
   A home runs `jbus snapshot --why` right after each edit to a `standing.md`, so each edit is a commit of its own.
   "Undo an edit to standing.md" in [state.md](../../../home/docs/state.md) says how to undo one.
5. It pushes to `origin`, whether or not it committed, so a commit whose push failed goes out with the next snapshot.
   It then prints `snapshot: committed, pushed` or `snapshot: nothing changed, pushed`.
   In a tree with no `origin`, the commit stays in the tree, so you can still undo an edit back to it.
   The snapshot then succeeds with `snapshot: committed, not pushed: <tree> has no origin, so the backup is off`.
6. A snapshot that refused a `standing.md` fails after its commit and push, so the alert names the refused project, its file, rule and why.

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
A snapshot that the unit's timeout stops raises nothing, and the next one that runs says why it failed.
The first snapshot that finishes after them says it recovered.
`systemctl --user list-timers jbus-snapshot.timer` shows when the next snapshot runs on Linux, and `git -C ~/.local/state/home log -1` shows the last one.
To take one now, run `systemctl --user start jbus-snapshot.service` on Linux, or `jbus snapshot` on macOS.
