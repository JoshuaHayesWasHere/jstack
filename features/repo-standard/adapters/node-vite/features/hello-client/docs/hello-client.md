# hello-client

The feature `hello-client` shows where a client's parts go.
Its folder is an npm package, the root of the repo's node stack, with its `package.json`, its `package-lock.json` and the Node version it pins in `.nvmrc`.
Its module, `src/greet.ts`, has its unit test beside it, `src/greet.test.ts`, which Vitest runs.
`make lint` runs the package's `check` script, here `tsc --noEmit`, and `make test` its `test` script, here `vitest run`.
Rename it for the repo's first client, or delete its folder and its stack in `.repo-standard.yml`.
