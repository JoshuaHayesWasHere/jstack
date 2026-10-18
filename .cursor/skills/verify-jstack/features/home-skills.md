# A home and its handoff

The home skill makes a thread the home of a repo: it plans with the user, queues briefs, and hands off to a fresh home before its context grows. `new-home` adds a repo, `nohome` opts out, `handoff` writes the short note and starts the next home, and `hooks/home-start.sh` starts a home in a new thread by itself. An agent runs these skills in a thread; the tests lift each shell block and run it.

Paths: `skills/home/`, `skills/new-home/`, `skills/nohome/`, `skills/handoff/`, `hooks/home-start.sh`, `templates/handoff.md`, `templates/handoff-seed.md`, `templates/hook-message.md`, `templates/plan-entry.md`
Tests: none

## Sub-features

Not driven yet.

## How to get to it (user POV)

Not driven yet.

## Driving it with verify-jstack

Needs: `home`

Not driven yet: no recipe drives this feature. The `home` seed is the sandbox's HOME, which every drive has.

## Gotchas

Not driven yet.
