# The verify-jstack harness

The scripts of this skill make a sandbox, check it, keep the evidence and clean up: `launch.sh`, `doctor.sh`, `record.sh`, `cleanup.sh`, and the stand-ins for T3 Code, `gh` and `systemctl`.

Paths:
- `features/verify-jstack/`
Tests: test_verify_jstack.py and test_home_clears_blockers.py drive these scripts and the skill's Drive recipes. Each spells or imports what it reads, so select_tests picks them with no entry here.

## Sub-features

Not driven yet.

## How to get to it (user POV)

Not driven yet.

## Driving it with verify-jstack

Needs: `home`

Not driven yet: no recipe drives this feature. The `home` seed is the sandbox's HOME, which every drive has.

## Gotchas

`fake-gh` answers only the calls its header lists, from the files of the sandbox's `gh` folder, and exits 64 on any other.
A drive that cancels or reruns a stuck run needs no shim of its own:
- `gh run cancel <id>` marks run `<id>` of `runs.json` completed and cancelled.
- `gh run rerun <id>`, with or without `--failed`, marks it queued again, at its next `run_attempt`.
- `gh api .../actions/runs/<id>/jobs` gives `jobs/<id>.json`, or no job when that file is not there.

Each call is a line of `calls.log`.
A run `runs.json` does not hold, or no `runs.json`, is not found, exit 1, as gh's.
