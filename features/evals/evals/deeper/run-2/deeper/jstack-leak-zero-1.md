## 1. What a top professional would do
An open-source program office (OSPO) lead or release engineer preparing a private repo for public release. "Every audit we could throw at it" has no end, so they would replace it with a **fixed, named list of audits, each with a pass/fail threshold**, and run it against **the whole git history, not just the current tree**. Once the repo is public, every past commit is public too. They would also have someone who has never seen jstack **install and use it from the README alone**, because that is the audit a public repo actually faces on day one.

## 2. The rawest material
- `git log --all -p` and `git rev-list --all` (every commit, branch and tag): in place of the current checkout, which hides secrets and paths that were deleted but still sit in history
- `git log --all --format='%an <%ae>%n%cn <%ce>' | sort -u`: in place of assuming who authored what, and to find the personal identities that would be published
- `git grep -nE '/home/[a-z]+|/Users/|\.claude/projects' $(git rev-list --all)`: in place of memory of "we cleaned up the local paths"
- `THIRD_PARTY.md`, `LICENSE`, and every vendored or quoted file (for example the Rieseberg material behind `principles/depth-over-breadth.md`): in place of a belief that credits are complete
- A fresh `git clone` into an empty container (`docker run --rm -it archlinux` / `podman`), plus the README's own install steps: in place of the maintainer's machine, which already has jbus, config and memory dirs that a stranger won't have
- `.github/workflows/*` and the CI run's own log: in place of "CI is green"

## 3. The methods and tools
- `gitleaks detect --log-opts="--all" -v` and `trufflehog git file://. --only-verified`: secret scan over full history (install: `pacman -S gitleaks`, `trufflehog` from AUR or its release binary)
- `git filter-repo --analyze`, then `git filter-repo --replace-text`/`--path` if anything is found: history rewrite before publishing, never after (`pacman -S git-filter-repo`)
- `reuse lint` (`pipx install reuse`) and `licensee detect .` or `scancode -clpeui --json-pp out.json .`: license clarity and per-file provenance
- `scorecard --local . ` / `scorecard --repo=github.com/<owner>/jstack` once pushed private (OpenSSF Scorecard): supply-chain hygiene (pinned actions, branch protection, token permissions)
- `actionlint` and `zizmor .github/workflows`: workflow security
- `shellcheck $(git ls-files '*.sh')` plus the repo's own test command: code health a reader will hit first
- A written checklist `docs/release-audit.md` with one line per audit: name, command, threshold, result, and date. This is how "every single audit" becomes finite and repeatable.

## 4. What outside the agent shows it is right
- `gitleaks` and `trufflehog` report **zero findings across all history**, with their output saved in the checklist
- `reuse lint` exits 0, and every third-party file has a credited source in `THIRD_PARTY.md`
- The history grep for home paths, `.claude/projects` and personal emails returns **nothing the user hasn't explicitly chosen to publish**
- OpenSSF Scorecard **≥ 8.0** and `actionlint`/`zizmor` clean. That bar is high for a new project and reasonable for one that wants to be a good public repo.
- **A person who has never seen jstack** clones it into a clean container and reaches a working first command from the README alone **in under 10 minutes**, without asking anyone. The user is the one who signs off on this result.

## Rewritten prompt
> "We should not take jstack public until it passes every single audit that we could potentially
> throw at it for what would make a good public repository." Make "every audit" a finite, named
> list in `docs/release-audit.md`: one line per audit with its command, its pass threshold, its
> result and its date. Start from the raw material, not the current checkout: the full history
> (`git log --all -p`, `git rev-list --all`), the author and committer identities across it, a
> history-wide grep for home paths, `.claude/projects` and personal emails, `LICENSE`,
> `THIRD_PARTY.md` and every vendored or quoted file, the CI logs, and a fresh clone in an empty
> container. Audit with `gitleaks detect --log-opts="--all"`, `trufflehog git --only-verified`,
> `git filter-repo --analyze` (and a rewrite before publishing if anything turns up),
> `reuse lint`, `licensee`/`scancode`, `scorecard`, `actionlint`, `zizmor`, `shellcheck` and the
> repo's own tests. It is ready to go public only when: both secret scanners report zero findings
> over all history; `reuse lint` passes and every third-party file is credited; the history grep
> shows nothing the user hasn't chosen to publish; Scorecard is at least 8.0 with clean workflow
> lints; and someone who has never seen jstack gets from clone to a working first command in a
> clean container using only the README, in under 10 minutes. Do not flip visibility yourself.
> Report the filled checklist and let the user decide.
