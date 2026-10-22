# check-workers-fit-room: size `make check`'s pytest workers to the room left on the machine

Task: "I want to push my machine as hard as I can without going over the edge" (2026-10-10) and "run the test in parallel" (2026-10-12)

Done when:
- `make check` chooses its pytest worker count when it starts, based on the free headroom: 12 cores minus the current one-minute load, kept within the limit `room` enforces. The fixed six workers are gone.
- On an idle machine, `make check` still runs in parallel with more than one worker.
- When the load is already at or above `room`'s limit, `make check` runs with one worker. It does not add to the overload.
- Three `make check` runners started together, alongside a crew's own run, keep the one-minute load below the point where `room` says wait. A pbus launch such as `gate pp-doctor` then gets room instead of failing with `no room for 10 passes`.
- The rule that picks the worker count has tests, and `make check` passes.

Where: the `check` target in the Makefile, the pytest/xdist settings in `pyproject.toml` or `pytest.ini`, and the `room` command, which is read for its threshold and headroom logic so the worker count uses the same numbers.

Do not touch: `room`'s thresholds, which must not be loosened to make the load fit. pbus's gating. The tests-parallel change (#339) beyond how its worker count is chosen. Parallel tests must not be turned off.

Decisions: "I want to push my machine as hard as I can without going over the edge"; "run the test in parallel"

Design: none, because this is a bounded change to how one Makefile target picks a number, and it reuses `room`'s existing limit.

Pull request: open one when done

Review: review

Playbook: none
