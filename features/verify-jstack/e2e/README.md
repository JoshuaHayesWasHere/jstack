# Deterministic end-to-end scripts

Two scripts drive the verify-jstack harness the way an agent does, from `launch.sh` to `cleanup.sh`.
They cover the paths no test reads: what Cleanup does after a good drive, two sandboxes side by side, and what the harness refuses.
This is the whole e2e layer.
A flow that a test can drive gets a test, and the recipes in the skill's Drive section are run by `test_a_drive_recipe_runs_in_a_new_sandbox_as_typed`.

```sh
bash features/verify-jstack/e2e/two-sandboxes.sh > /tmp/first.txt
bash features/verify-jstack/e2e/two-sandboxes.sh > /tmp/second.txt
diff /tmp/first.txt /tmp/second.txt && echo identical
```

| Script | What it proves | Poteto's script it follows | Run time |
|---|---|---|---|
| `two-sandboxes.sh` | Two sandboxes each go through Launch, Doctor, a `record`ed drive (`jbus queue add`, `jbus queue show`), the evidence kept, and Cleanup. Each has its own directory, port and evidence. A cleanup after a good drive stops its own stand-in and removes its own sandbox. It keeps the evidence, and the other sandbox still drives. | `create-verification-skill`, section 4 ("Prove the generated skill before handing it over") and the Isolate question of section 1. It also holds `maintain-verification-skill`'s live-pass invariants: Doctor before the first drive, evidence that survives every cleanup, and nothing a drive started outlives it. | about 3 s |
| `refusals.sh` | A launch from a shell that is already in a sandbox makes nothing. A cleanup by a partial path, or of a directory that has no marker, removes nothing. A cleanup whose recorded pid now names another sandbox's stand-in leaves that process running. | `create-verification-skill`, section 1's Isolate ("refusing to double-drive a shared instance beats corrupting the user's session") and section 2's Cleanup ("Never kill by process name; kill what you started"). It also holds `maintain-verification-skill`'s third live-pass invariant. | about 1.3 s |

## What each prints

Stdout is a transcript.
Each step prints `$ [<sandbox>] <command>`, then what the command printed and `[exit <code>]`.
Each expectation prints `ok   <what>` or `FAIL <what>`, and the last line is `e2e: ok`.
On a `FAIL` the last line is `e2e: FAIL` and the script exits 1.

What changes from run to run is masked, so two runs print the same bytes:

- the sandbox's path, name and token, as `<a>`, `<a-name>` and `<a-token>`
- its evidence directory, as `<a-evidence>`
- the scratch directory and the checkout, as `<tmp>` and `<repo>`
- pids, the stand-in's port, the time `record` stamps, the commit and the uncommitted count of Doctor's `build` line
- the dates and sizes of `ls -l`

The real paths go to stderr.

## No network, no clock

Each script runs with `UV_OFFLINE=1`, so the `uv sync` of `launch.sh` reads nothing from the network.
The stand-ins for T3 Code and `gh` are local: the T3 Code stand-in listens on 127.0.0.1, and `fake-gh` reads files.
No step depends on the time: the drive uses neither `jbus word` (its message carries a timestamp) nor `jgauge room` (it reads how full the host's `/tmp` is).

## Where the files go

Each run makes its own scratch directory, `${TMPDIR:-/tmp}/verify-jstack-e2e.XXXXXX`, and names it on stderr.
The sandboxes are made inside it and cleaned up, also when a step fails.
Their evidence stays in it, as Cleanup keeps it.
`lib.sh` holds the helpers the two scripts share.
It is sourced, never run.
