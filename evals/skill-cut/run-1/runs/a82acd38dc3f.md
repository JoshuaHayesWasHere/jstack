1. **First:** check the file's **"When this applies"** section. Its first condition, "No external users depend on backward compatibility," fails because this is a public npm library with thousands of outside users. So the delete-immediately rule doesn't cover this case.
2. **Decision:** do not delete `parseConfig` in this release. Removing it is a breaking change for users, so it waits for the next major version per semver.
3. **What I still follow:** the "Inventory callers, migrate them" step, applied to our own repo. I'd run `grep -rn "parseConfig(" src/ test/` and move every internal caller to the new API.
4. **Line I write** above `parseConfig` (new API name assumed): `/** @deprecated Use parseConfigNew() instead; parseConfig will be removed in the next major release. */`
5. **Time-box it:** treat `parseConfig` as the "exceptional and time-boxed" adapter. I'd make it a thin wrapper over the new API, add a changelog/migration note, and open an issue to delete it in the next major.
