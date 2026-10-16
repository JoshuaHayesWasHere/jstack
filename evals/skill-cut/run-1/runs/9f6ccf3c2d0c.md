First, I replace the silent `default: break;` so the compiler, not a reviewer, catches the new fifth kind. I follow the "Exhaustive matching is the compiler's job" bullet, using a `never`-typed binding in TypeScript.
I write: `default: { const _exhaustive: never = event; throw new Error(\`unhandled event kind: ${(_exhaustive as { kind: string }).kind}\`); }`
Then I run `npx tsc --noEmit`. It should fail on the fifth kind, which proves the guard works.
After that I add an explicit `case` for the new kind with its real handling, and rerun `tsc` until it is clean.
If any of the original four kinds were relying on the `break` no-op, I give them their own explicit empty `case`s.
