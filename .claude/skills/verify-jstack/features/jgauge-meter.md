# jgauge meters a session

`jgauge session` counts what a thread's session used, `jgauge context` tells a home how full its context is, through `hooks/home-gauge.sh`, and `jgauge test-slot` runs a command while it holds one of the machine's test slots. The counts are checked against two probe sessions (`docs/meter-findings.md`).

Paths:
- `src/jgauge/`
- `hooks/home-gauge.sh`
- `docs/jgauge.md`
- `docs/meter-findings.md`
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
