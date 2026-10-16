First I replace the silent `default: break;` so the compiler, not a runtime fall-through, flags the unhandled fifth kind. This follows the "Exhaustive matching is the compiler's job" bullet: a `never`-typed binding in TypeScript.
The line I write is `default: { const _exhaustive: never = event; throw new Error(\`unhandled event kind: ${(_exhaustive as { kind: string }).kind}\`); }`
Then I run `npx tsc --noEmit`, which should fail at that line once the fifth kind is in the union, naming the new variant.
Next I add `case '<fifth-kind>': ...` with the actual handling and re-run `npx tsc --noEmit` until it is clean.
If some kinds really should be ignored, I list them as explicit no-op cases (`case 'x': case 'y': break;`) rather than restoring a catch-all `default`.
