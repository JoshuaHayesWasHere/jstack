# A home and its handoff

The home skill makes a thread the home of a repo: it plans with the user, queues briefs, and hands off to a fresh home before its context grows. `new-home` adds a repo, `nohome` opts out, `handoff` writes the short note and starts the next home, and `features/home/hooks/home-start.sh` starts a home in a new thread by itself. An agent runs these skills in a thread; the tests lift each shell block and run it.

Paths:
- `features/home/skills/home/`
- `features/home/skills/new-home/`
- `features/home/skills/nohome/`
- `features/home/skills/handoff/`
- `features/home/hooks/home-start.sh`
- `features/home/templates/handoff.md`
- `features/home/templates/handoff-seed.md`
- `features/home/templates/hook-message.md`
- `features/home/templates/plan-entry.md`
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
