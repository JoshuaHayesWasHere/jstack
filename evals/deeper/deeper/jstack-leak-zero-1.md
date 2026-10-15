## 1. What a top professional would do
An open-source release engineer, the person in an OSPO who signs off on a repo going public, would do two things:
- **Audit the whole history, not the tree.** A secret, a personal path or a private note deleted in a later commit still ships with every clone.
- **Turn "every audit we could throw at it" into a fixed list of named, runnable checks**, each with a pass condition. An open-ended audit never finishes and never fails, and they would refuse one.

## 2. The rawest material
- `git rev-list --all --objects` and `git log --all -p` (every branch, tag and stash, every blob ever committed): in place of the files as they look at HEAD today.
- `git log --all --format='%an <%ae>%n%cn <%ce>' | sort -u`: in place of the assumption that commits carry only the identity meant for publication.
- `git grep -nE 'the user|\.claude/|jbus|localhost:[0-9]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+' $(git rev-list --all)`: in place of memory of what was ever written into prompts, briefs, `tasks/` and `principles/`.
- `THIRD_PARTY.md` checked against the actual license text of each source it credits, and `git ls-files` for every file without a license header: in place of the belief that attribution is complete.
- A fresh `git clone` into an empty container, following only `README.md`: in place of the working copy on this machine, with its installed tools, env vars and `~/.claude` state.

## 3. The methods and tools
- `gitleaks detect --source . --log-opts="--all" --redact -v` (`pacman -S gitleaks`): secret scan over the full history.
- `trufflehog git file://$PWD --only-verified` (`go install github.com/trufflesecurity/trufflehog/v3@latest` or the AUR): a second, independent secret scanner that checks whether any key found is still live.
- `reuse lint` (`pipx install reuse`): per-file license and copyright, against the REUSE spec.
- `licensee detect .`: confirms the top-level LICENSE is recognised as the license you intend.
- `scorecard --local=.` now, and `scorecard --repo=github.com/<owner>/jstack` on a private push before flipping visibility: the OpenSSF checks (branch protection, pinned deps, token permissions, SECURITY.md).
- `shellcheck $(git ls-files '*.sh')` plus the repo's own test suite: the code in the repo holds up to a stranger's reading.
- `docker run --rm -it archlinux` (and one Debian image), cloning and following README verbatim: reproducibility from zero.
- `git filter-repo`: the remediation for anything found in history. Rewrite the history; a deleting commit is not a fix.

## 4. What outside the agent shows it is right
- gitleaks over `--all` exits 0, with no baseline entries other than ones that are written down and justified. Trufflehog reports 0 verified secrets.
- The identity and path grep over all revisions returns only what you have chosen to publish.
- `reuse lint` prints "compliant", and `licensee` names the intended license.
- OpenSSF Scorecard reaches ≥ 8/10 on the private GitHub push. That target is ambitious but reasonable for a small, new repo.
- A clean container goes from `git clone` to a working first command using only the README, in under 10 minutes.
- One person other than you, given only the repo URL, does the same and reports no blocker.

## Rewritten prompt
```
"We should not take jstack public until it passes every single audit that we could potentially
throw at it for what would make a good public repository."

Make "every audit" a fixed list, and audit the full history, not just HEAD. Start from:
`git rev-list --all --objects` and `git log --all -p`; the author/committer identities from
`git log --all --format='%an <%ae>%n%cn <%ce>' | sort -u`; a grep across all revisions for
the user, .claude/, jbus, localhost ports and email addresses; THIRD_PARTY.md checked
against each credited source's license; and a fresh clone in an empty container following only
README.md.

Run: gitleaks detect --log-opts="--all"; trufflehog git --only-verified; reuse lint;
licensee detect; scorecard --local=. and then on a private GitHub push; shellcheck and the test
suite; the README quickstart in clean archlinux and debian containers. Fix anything found in
history with git filter-repo, not with a deleting commit. Report every finding with its commit.

Done when: gitleaks and trufflehog report zero over all history, the identity/path grep shows
only what we chose to publish, reuse lint says compliant, licensee names our license, Scorecard
is ≥ 8/10, a clean container runs the quickstart in under 10 minutes, and one person who is not
me gets it running from the URL alone.
```
