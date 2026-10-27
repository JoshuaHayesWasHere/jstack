# A pull request is reviewed

The pr-review skill reviews a finished pull request in a fresh thread: it reads the diff, judges what it found, proves the one safety fact by running code, and writes the findings in the brief, where jbus reads them and tells the crewmate when it owes a line.
`blast-radius` and `interrogate` are the questions it asks.

Paths:
- `features/pr-review/`
- `features/skill-library/skills/blast-radius/`
- `features/skill-library/skills/interrogate/`
- `features/crew/templates/rerun.md`
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
