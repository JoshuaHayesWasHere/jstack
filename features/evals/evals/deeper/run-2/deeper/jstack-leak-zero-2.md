## 1. What a top professional would do
An open-source program office (OSPO) release reviewer, the person who signs off before a company repo goes public, would do two things here:
- Replace "every audit we could throw at it" with a fixed, named checklist. Each item would have a tool and a pass condition, so "passes" has a definite meaning.
- Audit the whole git history, not just the current tree. Going public publishes every commit ever made: secrets, author emails, vendored code and deleted files included. A clean HEAD over a dirty history fails.

## 2. The rawest material
- `git rev-list --objects --all` and `git log --all -p` in the jstack repo, which cover every blob and diff in every branch and tag: in place of the files as they look today.
- `git log --all --format='%an <%ae> | %cn <%ce>' | sort -u`, the identities that would go public with the repo: in place of the assumption that only the code is exposed.
- The lockfiles and manifests themselves (`package-lock.json`, `Cargo.lock`, `go.sum`, `requirements*.txt`, whichever jstack has) and every file header: in place of a remembered "it's all MIT".
- A fresh `git clone` of jstack into an empty directory on a machine without your dotfiles: in place of the working copy that only builds because of local state.
- `git ls-files | xargs file` and `git ls-files -z | xargs -0 du -h | sort -h | tail`, for binaries, large blobs, `.env` files and fixtures with real data: in place of a skim of the tree.

## 3. The methods and tools
- `gitleaks detect --source . --log-opts="--all"` and `trufflehog git file://. --only-verified`: a secret scan over all of history, with a second scanner as a cross-check. Install with `pacman -S gitleaks` and `trufflehog` from AUR or its release binary.
- `reuse lint` (`pipx install reuse`) and `scancode -clpi --json-pp out.json .` (scancode-toolkit): per-file licence and copyright provenance against the REUSE spec.
- `osv-scanner -r .`: known vulnerabilities in the full dependency tree, read from the lockfiles.
- `scorecard --local .`, or `scorecard --repo=github.com/<owner>/jstack` once it is pushed private: the OpenSSF Scorecard checks (branch protection, pinned actions, token permissions, SECURITY.md, licence).
- `git filter-repo --analyze`, then `git filter-repo` for any rewrite: history surgery driven by what the scans found, not by guesses.
- A clean-room build with `docker run --rm -v "$PWD/clone":/src -w /src <base image> sh -c '<README's install and test commands>'`: proof that the README alone is enough to build and test the project.

## 4. What outside the agent shows it is right
- `gitleaks` exits 0 and `trufflehog --only-verified` reports 0 findings over `--all` history. The target is zero, not "only low severity".
- `reuse lint` prints "Congratulations! Your project is compliant", and scancode finds no licence incompatible with jstack's own.
- `osv-scanner` reports 0 known vulnerabilities, or each remaining one is listed with a reason.
- `scorecard` scores ≥ 8/10. That is ambitious for a first release, and reasonable for a repo built to be public.
- The clean-room container runs the README's commands to a green test suite with no edits.
- Your own cold read: you read the author list from `git log` and the README as a stranger would, and sign off on both.

## Rewritten prompt
> "We should not take jstack public until it passes every single audit that we could
> potentially throw at it for what would make a good public repository." Make "every audit"
> a fixed checklist, and audit the full git history (`git rev-list --objects --all`, all branches
> and tags), not just HEAD. Start from the raw material: every blob and diff in history, the
> author and committer identities from `git log --all --format='%an <%ae> | %cn <%ce>'`, the
> lockfiles, every file's licence header, and a fresh clone in an empty directory. Run
> `gitleaks detect --log-opts="--all"`, `trufflehog git file://. --only-verified`, `reuse lint`,
> `scancode -clpi`, `osv-scanner -r .`, `scorecard`, and a clean-room `docker run` of the README's
> build and test commands. Use `git filter-repo` for any history fix the scans call for. jstack
> is ready to go public only when gitleaks and trufflehog report zero over all history,
> `reuse lint` is compliant, osv-scanner is clean or each finding is justified, Scorecard is ≥ 8,
> the clean-room build passes its tests unedited, and I have signed off on the author list and
> README myself. Report each check with its command and raw output.
