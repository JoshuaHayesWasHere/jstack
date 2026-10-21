# A jbus pass

`jbus poll` is one pass over every project: it reads the queue, the briefs, T3 Code and GitHub, launches what is approved and has room, tells each thread what it must act on, runs `jmerge`, and writes what it saw to the state directory. Every other `jbus` verb reads or writes that state. This feature is the whole `jbus` package and what it imports, so its tests are the ones that import it, which `scripts/select_tests.py` follows through the imports.

Paths:
- `src/jbus/*.py`
- `src/jbus/view/*.py`
- `src/jbus/view/panels/__init__.py`
- `features/jbriefs/src/jbriefs/`
- `src/jgauge/`
- `src/jmerge/`
- `features/jpack/src/jpack/`
- `features/jroles/src/jroles/`
- `features/jsettings/`
- `docs/jbus.md`
- `docs/chef.md`
- `docs/configuration.md`
- `docs/state.md`
- `docs/troubleshooting.md`
- `templates/jbus.service`
- `templates/jbus.timer`
- `templates/jbus-failed.service`
- `templates/jbus-relay.service`
- `templates/jbus-snapshot.service`
- `templates/jbus-snapshot.timer`
- `templates/jbus-snapshot-failed.service`
- `templates/jbus-view.service`
- `src/jbus/ci/`
- `templates/jbus-ci.service`
- `templates/jbus-ci.timer`
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
