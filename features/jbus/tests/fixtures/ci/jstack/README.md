# A recording of jstack's Actions API

What GitHub answered for `JoshuaHayesWasHere/jstack` between 2026-10-14 and 2026-10-17 22:15 UTC,
trimmed to the fields `jbus ci` reads. `features/jbus/tests/ci_replay.py` serves it as `jbus.ci.collect.Gh`, and
`features/jbus/tests/test_jbus_ci.py` counts the nine targets from it and checks them against the figures the
CI plan (`scouts/ci-cd-deep-plan.md`) was written from.

| file | what GitHub gave | kept |
| --- | --- | --- |
| `runs.json` | `actions/runs`, 293 runs | `id`, `event`, `head_branch`, `head_sha`, `run_attempt`, `created_at`, `status`, `conclusion`, `pull_requests[].number` |
| `jobs.json` | `actions/runs/<id>/jobs?filter=all`, by run id | `id`, `run_id`, `run_attempt`, `name`, `head_sha`, `status`, `conclusion`, the three times, `labels`, `runner_name`, and the names of the steps |
| `prs.json` | `pulls?state=all`, 71 pull requests | `number`, `state`, `created_at`, `closed_at`, `merged_at`, `merge_commit_sha`, `head.ref`, `head.sha` (empty for the 9 that never merged) |
| `pushes.json` | `issues/<n>/timeline`, by number | the `head_ref_force_pushed` events: `created_at` and `commit_id` |
| `logs.json` | `actions/jobs/<id>/logs` of each red job on the local runner, by job id | only the lines that say what failed (`FAILED`, `ERROR`, `E  `, `##[error]`), the time stamp taken off, each cut to 160 characters, and at most 60 failing test ids |
| `events.jsonl` | jbus's own `events.jsonl` for jstack | the rebase, conflict, mainmoved, failed, review, expedite, resume and drops events, with `text` cut to the one phrase `jbus.ci.numbers` looks for |

No annotation was recorded: the jobs of these days wrote no telemetry, as nothing could yet.
The tests give the ones they need.

The 9 pull requests that never merged were read from the scout's GraphQL listing and have no head sha;
their force-pushes are in `pushes.json` because the plan counted them.
