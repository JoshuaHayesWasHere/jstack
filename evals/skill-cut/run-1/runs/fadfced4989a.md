No wrapper. The "When this applies" conditions all hold: no external users, a breaking change the repo can absorb, and this is a refactor. So I migrate all 14 callers and delete `fetchUser` in the same wave.

First, I list every caller: `rg -n '\bfetchUser\(' --type ts`
Then I rewrite each call site to `fetchUserV2`, adjusting arguments and return handling to its contract.
Following the tests bullet, I update tests to assert `fetchUserV2`'s contract and delete tests that only protect `fetchUser` internals.
Last, I delete the `fetchUser` definition and export, and confirm `rg '\bfetchUser\b'` returns nothing before committing.
