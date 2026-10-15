## 1. What a top professional would do
An open-source program office (OSPO) release engineer, with a security reviewer beside them. They would turn "every audit we could throw at it" into a short, named set of audits, each run by an external tool with a pass line. They would audit the **full git history**, not just the current tree, because going public publishes every commit ever made. They would also prove a stranger can use the repo by doing a cold install in a clean container from the README alone.

## 2. The rawest material
- `git -C ~/jstack log --all -p` and `git -C ~/jstack rev-list --all --objects`: every blob in every commit and branch, in place of the current tree as it looks today
- `git -C ~/jstack log --all --format='%an <%ae>%n%cn <%ce>' | sort -u`: the real author and committer identities that will be published, in place of the assumption that only the repo's name goes public
- `git -C ~/jstack ls-files` plus each file's header, `LICENSE`, and the lockfiles (`package-lock.json`, `uv.lock`, `Cargo.lock`, or whatever jstack has): what is actually shipped and under which terms, in place of a remembered "it's MIT"
- `~/jstack/.github/workflows/*.yml` and the logs of their last runs (`gh run view --log`): what CI really does with tokens and permissions, in place of "CI is green"
- `README.md` as written, read by a machine that has never seen jstack: in place of the author's knowledge of how to set it up
- Hard-coded paths, hostnames and emails found by `rg -n 'the user|@gmail\.com|localhost:[0-9]+|BEGIN .*PRIVATE KEY' ~/jstack`: in place of a belief that nothing personal is in it

## 3. The methods and tools
- `gitleaks detect --source ~/jstack --log-opts="--all"` and `trufflehog git file://$HOME/jstack --only-verified`: secret scanning across all history, with two scanners, not one. If either is missing: `pacman -S gitleaks`, `yay -S trufflehog-bin`.
- `git filter-repo --analyze` (`pacman -S git-filter-repo`): find large or sensitive blobs in history. If anything is found, rewrite the history with `git filter-repo` before publishing, not after.
- `reuse lint` (`pipx install reuse`) and `licensee detect ~/jstack`: license compliance per file, and whether the declared license is recognised.
- `osv-scanner -r ~/jstack` (`go install github.com/google/osv-scanner/cmd/osv-scanner@latest`): known vulnerabilities in the locked dependencies.
- `scorecard --local ~/jstack` (OpenSSF Scorecard; the full checks run with `--repo` once it's on GitHub as private): supply-chain and repo-hygiene audit. Covers pinned actions, token permissions, branch protection, SECURITY.md, and dangerous workflows.
- `zizmor ~/jstack/.github/workflows` (`pipx install zizmor`): static audit of GitHub Actions for injection and over-broad permissions.
- Language linters at their strictest, e.g. `shellcheck $(git ls-files '*.sh')`, `ruff check --select ALL`, or `cargo clippy -- -D warnings`: code a stranger will read first.
- `docker run --rm -it -v ~/jstack:/src:ro archlinux` (or `debian:stable`): a cold-start test. Copy the repo in, then follow `README.md` literally, line by line, with no outside knowledge.
- Method: write the audit list down first as a fixed checklist, `~/jstack/docs/release-audit.md`. Each line names the audit, its command and its pass line. That makes "every audit" finite and repeatable.

## 4. What outside the agent shows it is right
- `gitleaks` and `trufflehog` both report **0 findings over `--all` history**. Not "0 in HEAD".
- `reuse lint` exits 0, and `licensee` identifies the license with ≥ 95% confidence.
- `osv-scanner` reports 0 known vulnerabilities, or each one has a written, dated exception.
- OpenSSF Scorecard scores **≥ 8.0/10**. That is an unreasonable target for a personal repo, and it is the reasonable one for a project that asks strangers to run it. `zizmor` reports 0 high findings.
- In a clean container, a run of `README.md`'s steps verbatim ends in a working jstack, and the test suite passes there.
- One human who is not the author, and not a model, gives a "ready" or "not yet" after reading the repo cold, and their notes are kept.

## Rewritten prompt
```
"We should not take jstack public until it passes every single audit that we could
potentially throw at it for what would make a good public repository."

Make "every audit" a fixed, finite checklist in ~/jstack/docs/release-audit.md. Each line
names one audit, the command that runs it, and its pass line. Then run it. Do not publish
anything. This task ends at a verdict, not at the release.

Start from the raw repo, not its current tree: `git log --all -p` and
`git rev-list --all --objects` (all history, all branches), the published author/committer
identities (`git log --all --format='%an <%ae>%n%cn <%ce>' | sort -u`), `git ls-files` with
LICENSE and the lockfiles, .github/workflows/*.yml with the logs of their last runs, and
README.md as a stranger would read it. Grep for the user, personal emails, local hosts and
private keys.

Use: gitleaks and trufflehog over --all history; git filter-repo --analyze (and rewrite the
history if anything is found, before going public); reuse lint and licensee; osv-scanner on
the lockfiles; OpenSSF Scorecard (--local, then --repo on a private GitHub copy); zizmor on
the workflows; the strictest linter for each language in the repo; and a cold install in a
clean archlinux or debian container that follows README.md verbatim. Install any tool that is
missing, and say which.

Done when, and only when: gitleaks and trufflehog both report 0 findings over all history;
reuse lint exits 0 and licensee recognises the license; osv-scanner has 0 unexcepted
vulnerabilities; Scorecard is >= 8.0 and zizmor has 0 high findings; the README-only cold
install works and the tests pass in the container; and one human other than the author has
read the repo cold and said "ready". Report each audit's raw output against its pass line.
Report every failure as it stands.
```
