**First:** check the file's **"When this applies"** section. Its first condition, "No external users depend on backward compatibility," fails: this is a public npm library with thousands of outside users. So the principle doesn't apply, and I don't delete `parseConfig` in this release.

**Instead:** ship the new API alongside it, mark `parseConfig` deprecated, and schedule removal for the next semver major. The line I write above `parseConfig`:

`/** @deprecated Use parseConfigV2 instead; parseConfig will be removed in v<next-major>.0.0. */`

I'd also add a one-time `process.emitWarning('parseConfig is deprecated; use parseConfigV2', 'DeprecationWarning')` and a CHANGELOG entry. Internal callers can still migrate now, per the file's "Inventory callers, migrate them" rule.
