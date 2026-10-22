Kind: perf

"I want to push my machine as hard as I can without going over the edge" (the user, 2026-10-10), and "run the test in parallel" (2026-10-12): since tests-parallel (#339) `make check` runs pytest on six workers, and three runners plus the crews' own runs put the one-minute load at 14 to 15 on 12 cores for over ten minutes on 2026-10-12 at 21:35 ET, so `room` said wait and pbus could launch nothing (`gate pp-doctor: no room for 10 passes`)
