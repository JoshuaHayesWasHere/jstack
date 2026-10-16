### Intent
> Topic 10, "A way to undo a bad merge into standing.md." Every edit a home or a handoff makes to `$H/standing.md` is followed right away by `jbus snapshot --why <text>`. That gives the edit its own commit in `~/.local/state/home`, pushed, with the reason after the timestamp in the message. The twice-daily timer stays as it is. `docs/state.md` explains how to find a bad edit with a path-limited `git log -p`, restore the earlier text with `git show <commit>^:<path>`, and snapshot again. Tests run the flag and the documented restore against a temporary tree with a bare remote.

### Reviewers
- Reviewer A: 7 findings
- Reviewer B: 5 findings
- Each reviewer found three of the same problems on their own: no lock on concurrent snapshots, a restore command that can empty the file, and a new duty added to handoff. Both also flagged the out-of-scope `docs/jbus.md`. The review skill's questions were answered: both reviewers checked the Done-when lines, the tests, correctness and scope.

### Act On

**1. Concurrent snapshots have no lock** (A1, B1: lock part)
Before this change, `take` ran twice a day from a single timer. It now also runs whenever any home, scoped homes included, edits `standing.md`, and all of them share the same index in `~/.local/state/home`.

Both reviewers describe concrete ways this fails:
- **Lock collision.** A run hits `.git/index.lock` and `_must` raises `Failed`. If the timer's run is the one that fails, `OnFailure` fires `--alarm` and sends a false alert to every project.
- **Lost commit.** Home A's `git reset -q` can land between home B's `add` and `diff --cached`. B then prints "nothing changed" and its edit gets no commit of its own. That is the exact guarantee the task asks for.

The fix is cheap and stays inside **Where**: hold an exclusive `flock` on a file in `.git` across add, commit and push in `snapshot.py`.

**2. The documented restore can empty the live `standing.md`** (A2, B2)
The shell `>` truncates the target before `git show` runs. `git show` fails in ordinary cases:
- the bad commit is the one that created the file (the first rule a repo ever got),
- the bad commit is the root commit,
- the hash is mistyped or ambiguous.

When it fails, the rules file is left empty. The doc's next step then snapshots the empty file, and the next home start reads it as "no standing rules". This is the undo path the task exists for, so it cannot be allowed to destroy data.

The fix:
- Document `git -C ~/.local/state/home restore --source=<commit>^ -- <repo>/standing.md`, or the tmp-file-then-`mv` form.
- Say what to do when the bad commit created the file.
- Add a test that undoes the creating commit. The current test only covers a parent commit that already has the file.

**3. Handoff gains a new duty to write rules** (A5, B3)
The added line "One it did not write yet goes there now, as one dated line" makes handoff a second place where rules get written. It contradicts the sentence just before it, which says the home wrote the rule when it heard it. The task asked handoff to snapshot after an edit, not to start making edits. Skill text steers behaviour, so an unrequested behaviour change here matters.

Cut the line and keep only the general rule: "after any edit to `$H/standing.md`, run `jbus snapshot --why …`". This also removes the hardcoded `added` that A4 saw drifting from the other two copies.

### Consider

**4. `--why` commits still sweep in the whole tree** (A3, B1: mixed-commit and two-edits parts)
`git add -A` means a commit labelled "jstack standing rule 3 added" can also carry briefs, `merge.log`, and other repos' changes. Two homes editing the same `standing.md` before either snapshots end up in one commit. Undoing "the bad one" then reverts both edits.

What still works: the documented undo is path-limited, so `log -p` and `show <commit>^:<path>` still find and restore the right text. Once the lock from item 1 is in place, the two-edits window shrinks to edits made between a write and its immediately following snapshot.

The cleaner fix is `git commit -- <path>` when `--why` is given, which makes "a commit of its own" literally true. It is cheap, but it adds a path argument to the CLI. It is worth doing if the user reads unfiltered `git log`. Otherwise the cheapest version is to note in the message that the commit is a whole-tree snapshot.

### Noted

- **The snapshot rule lives in prose in three skill files** (A4). The task specified exactly this mechanism: skill instructions plus a flag. A `jbus standing add` verb would enforce it, but that is outside **Where**, so record it for later. Item 3 removes the drift between the copies.
- **`docs/jbus.md` is edited outside Where** (A6, B4). The edit is accurate and needed, since otherwise the flag would be undocumented on the commands page. The crewmate should name it under "Noticed" rather than revert it.
- **Test name understates what it checks, and its first half duplicates line 77** (B5). It is a cheap rename if the file is touched anyway for item 2, but it is not worth a round on its own.

### Dismissed

- **`with_origin` duplicates the inline setup in older tests** (A7). Migrating the untouched older tests would be a refactor of code that isn't broken, outside this change's lines. A test fixture helper is not the internal-API case that principle covers.

### Agreement Map

The reviewers agreed independently on both correctness problems (no lock, and a restore that truncates the file) and on the handoff scope creep. That consensus, plus concrete execution paths for each, is why all three are Act On. The one divergence was severity on the handoff line: A called it a warning, B a nit. I side with A because skill prose is behaviour.

A split the commit-content problem into its own finding (A3). B folded it into the concurrency finding. Taken together, they show the change treated "a commit of its own" as a property of the call site, while the code (`git add -A`, no lock) never made it a property of the commit.

Neither reviewer padded with style nits. The remaining low findings are honest scope and naming notes. The core change, the flag plus the doc section, is sound once the lock and a safe restore form are in.

BUCKETS
A1: Act on
A2: Act on
A3: Consider
A4: Noted
A5: Act on
A6: Noted
A7: Dismissed
B1: Act on
B2: Act on
B3: Act on
B4: Noted
B5: Noted
