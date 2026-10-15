# public-readiness-audit: Audit jstack against every public-repo standard and fix what fails, without making it public
Task: "We should not take jstack public until it passes every single audit that we could potentially throw at it for what would make a good public repository"
Done when:
- A secret scan of the working tree and the full git history (`gitleaks detect` and `trufflehog git file://.`) reports no findings, or each finding is listed and shown to be a false positive
- No personal data is left in tracked files or commit metadata that the user has not cleared: no home-directory paths like `/home/<user>/`, no personal email addresses, no machine names, no tokens
- `LICENSE`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` and issue/PR templates exist, and the README covers what jstack is, how to install it, how to use it, and what it needs
- `pip-audit` reports no known vulnerabilities in the Python dependencies, and every dependency's license is compatible with the chosen license
- The Python commands pass lint, type checks and tests in CI on a clean checkout, with no dependence on local paths or the author's `~/.claude`
- The OpenSSF Scorecard checks that can run before publishing are run, and each failure is fixed or written down with a reason
- A report at `docs/public-readiness.md` lists every audit run, the command used, the result, and any remaining item that needs the user's decision
Where: the whole repo: skills, playbooks, Python commands, docs, CI config, repo metadata files, and the git history (read only)
Do not touch: the repo's visibility (do not make it public), git history (do not rewrite or force-push; list any history problems in the report instead), package registries (publish nothing), the user's `~/.claude` and memory files
Decisions: "We should not take jstack public until it passes every single audit that we could potentially throw at it for what would make a good public repository"
Design: none, this task audits the repo and fixes metadata and hygiene issues. It does not change how jstack is built.
Pull request: ask first
Review: review
Playbook: none
