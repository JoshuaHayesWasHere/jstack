# qw-deploy-main-to-prod: deploy the changes landed on main (7a8fe2cab573) to prod, with a rollback target pinned and prod checked after
Green main: 9ad3c16451be5f95ccf66301ff85138c025525a0
Task: "deploy the changes that have landed so far to prod" (Josh, chat, Oct 30 2026 5:13 PM ET, word d3da00397861)
Goal: Deploy main at 7a8fe2cab573 to Winnifred prod (stacks winnifred-prod and winnifred-frontend-prod) with the repo's own deploy scripts, following api/DEPLOYMENT.md: the rollback target is pinned first and prod is verified after. Nothing is deleted; no down migration runs on prod.
Where: `infra/`, `api/DEPLOYMENT.md`, `db/migrations/`, `client/sync_frontend.sh`; no source change
Do not touch: source code, .github/workflows/, the ruleset, PR #255 or any other open PR, dev's stacks, any prod data other than the additive migration named below, never `sam build && sam deploy` by hand
Decisions: Josh's own words: "deploy the changes that have landed so far to prod". That is the go for this one prod deploy of the pinned sha and nothing more. Main's check is red at 7a8fe2cab573 on one flaky test, infra/deploy-account.test.mjs:135, and PR #255 (qw-dev-deploy-lock) fixes it; do not touch #255. The deploy scripts have no CI gate, but this row is held by jbus while main is red, so it launches after the fix merges.
Done when:
- before any write: `git fetch origin --tags`, then `git rev-parse origin/main` is recorded. If it is still 7a8fe2cab573 deploy that. If it moved, run `git diff --stat 7a8fe2cab573 origin/main`: deploy the newer main only when every file changed is a test or test helper (the lock-test fix), else deploy the pinned 7a8fe2cab573 from a detached worktree and say so
- the commit prod runs now is found from prod itself (stack winnifred-prod `DeploymentVersion` and LastUpdatedTime via `aws cloudformation describe-stacks --stack-name winnifred-prod --profile winnifred-prod`, and the `entry/start.<hash>.js` that `curl -s https://winnifred.example.test/` names matched to a commit's `client/build`), and it is pinned with `git tag prod/<short sha> <sha> && git push origin prod/<short sha>` as api/DEPLOYMENT.md says. If the running commit cannot be found, stop before any write and report that
- `git diff --stat <prod's commit> <deployed sha> -- db/schema.sql db/migrations` is read. Migration 0023_delivery_dismissed.up.sql (one `ALTER TABLE delivery ADD COLUMN IF NOT EXISTS dismissed_at`, additive, safe to rerun) is applied to prod before the backend deploys: `DSQL_STAGE=prod db/apply.sh dsql migrations/0023_delivery_dismissed.up.sql`, then `grants.sql` as api/DEPLOYMENT.md shows. Any other migration that drops, renames or rewrites a column or table, or any down migration: stop and report, since the rollback would then lose data
- `DRY_RUN=1 ./deploy-backend.sh prod` and `DRY_RUN=1 ./deploy-frontend.sh prod` pass; then `infra/deploy-backend.sh prod` and `infra/deploy-frontend.sh prod` (or `client/sync_frontend.sh prod`) run from a checkout of the deployed sha, backend first, the "yes" prompt answered `yes` because of Josh's go above
- `aws cloudformation describe-stacks --stack-name winnifred-prod` shows UPDATE_COMPLETE with the new DeploymentVersion, and so does winnifred-frontend-prod
- the front door's `entry/start.<hash>.js` from `curl -s https://winnifred.example.test/` equals the one in the deployed sha's `client/build/index.html`
- prod verified as api/DEPLOYMENT.md "What to check after" says: sign in as the household's owner (credentials from the vault, never printed), Today lists the household's doses, one dose is logged and taken back with Undo, a pet, the calendar and Settings open; prod's API logs show no new errors for 15 minutes (`sam logs -n ApiFunction --stack-name winnifred-prod`) and CloudWatch alarms stay OK
- if any check above fails, roll back as api/DEPLOYMENT.md "Redeploy the previous commit" says (to the pinned tag, schema check first, never a down migration) and report; if rollback needs a data change, stop and report
- the Result names the sha deployed, prod's previous sha and tag, the DeploymentVersion, the migration applied, each check with its output, and the rollback command ready to run
Proves it: the commands `aws cloudformation describe-stacks --stack-name winnifred-prod` (UPDATE_COMPLETE and the new DeploymentVersion) and `curl -s https://winnifred.example.test/` (its start.<hash>.js equals the deployed build's), and Josh, who can open prod and see Today
Size: M
Pull request: ask first
Review: none
This row opens no pull request (the pushed `prod/<sha>` tag is the only repo write), so `Review: none` holds nothing; if a pull request does come up, it waits for Josh's word.
Playbook: autonomous-run
Design: none, a deploy with no UI change
Skills: architect, blast-radius, principle-prove-it-works, show-me-your-work
Read:
- api/DEPLOYMENT.md lines 255-315 (stages, each stage's database, prod migrations) and 388-490 (rollback, pin what prod runs now, what to check after)
- infra/README.md lines 30-45 and 191-205 (stage scripts, the prod confirm prompt) and infra/deploy-backend.sh lines 40-75 (the prod branch warning and prompt)
- db/migrations/0023_delivery_dismissed.up.sql and .down.sql (additive up; the down is refused on prod)
- AGENTS.md lines 170-230 (use the scripts, never sam by hand) and 296-310 (prod is on the tailnet at https://winnifred.example.test/, front door winnifred-front-door-prod on 127.0.0.1:8491)
Instruments:
- `git rev-parse origin/main` and `git diff --stat <a> <b> -- db/schema.sql db/migrations` for the pin and the schema check
- `DRY_RUN=1 infra/deploy-backend.sh prod` and `DRY_RUN=1 infra/deploy-frontend.sh prod` for the account check
- `aws cloudformation describe-stacks --region us-east-1 --stack-name winnifred-prod --profile winnifred-prod --query 'Stacks[0].[StackStatus,LastUpdatedTime,Parameters[?ParameterKey==`DeploymentVersion`].ParameterValue|[0]]' --output text`, and the same for winnifred-frontend-prod
- `curl -s https://winnifred.example.test/` and `client/build/index.html` for the front door build hash
- headless Chromium signed in as the household owner for the prod walk, and `sam logs -n ApiFunction --stack-name winnifred-prod` for the 15 minutes after
Home: 123s

