# jroles names a model

`jroles <role>` prints the model selection a launch of that role takes, from the role map in the user's config, on the first instance of the role's pool with headroom in the ledger. The skills put what it prints into their launch calls, and `jbus` takes the `crew` line the same way.

Paths: `src/jroles/`, `docs/jroles.md`, `hooks/limits.sh`
Tests: none

## Sub-features

- `roles-pool` prints the selection on the first instance of the pool, and says which and why on stderr.
- `roles-spill` prints it on the next instance while the first is capped in the ledger (`<LIMITS>.<instanceId>`), and exits 75 with every instance capped.

## How to get to it (user POV)

Not driven yet.

## Driving it with verify-jstack

Needs: `home`

Not driven yet: no recipe drives this feature. The `home` seed is the sandbox's HOME, which every drive has.

## Gotchas

Not driven yet.
