No wrapper. I follow the **Rule** section: "Do not keep legacy API paths only because internal callers still exist" and "Inventory callers, migrate them, and delete the old API immediately." The **When this applies** conditions hold, since there are no external users.

First I list every caller: `rg -n '\bfetchUser\b' --type-add 'src:*.{ts,tsx,js}' -t src`
Next I move all 14 callers to `fetchUserV2`, delete `fetchUser`, and update the tests to check the new contract. I drop tests that only protected the old implementation.
Then I confirm nothing still uses it: `rg -n '\bfetchUser\b'` should return nothing.
