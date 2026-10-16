First, replace the silent `default: break;` so the compiler flags the switch, before adding the fifth kind. I follow the "Exhaustive matching is the compiler's job" bullet: use a `never`-typed binding in TypeScript.
I write: `default: { const _exhaustive: never = event; throw new Error(\`unhandled event kind: ${(_exhaustive as { kind: string }).kind}\`); }`
Then I add the fifth variant to the union and run `npx tsc --noEmit`. It should fail at that `never` line, which shows me exactly where the new case goes.
I add `case '<fifth-kind>':` with real handling. If it's truly a no-op, I write an explicit `break` there instead of falling through a default.
I re-run `npx tsc --noEmit` until it is clean, and I grep for other `switch (event.kind)` sites to apply the same fix.
