---
name: typescript-best-practices
description: TypeScript best practices. Use for /typescript-best-practices, typed before reading or editing .ts or .tsx files.
tip: loads the TypeScript rules before a .ts or .tsx edit | typescript | tsx | ts file
disable-model-invocation: true
card: "House standards for text and code | 4 | TypeScript practices a thread loads before it reads or edits `.ts` and `.tsx` files. | Reach for it when the task touches TypeScript. | op: the operator"
---

# TypeScript best practices

Source: pstack, `pstack/skills/typescript-best-practices/SKILL.md`

The source's frontmatter has `paths:` for `**/*.ts` and `**/*.tsx`, which loads it whenever such a file is read. That line is dropped here: a skill in this repo loads only when it is typed, so nothing brings these rules in by a file's path. Type `/typescript-best-practices` at the start of TypeScript work, or have the brief tell the crewmate to read this file.

Run this first:

```sh
if R=$(realpath ~/.claude/skills/typescript-best-practices/../.. 2> /dev/null) && [ -f "$R/principles/type-system-discipline.md" ]; then
    echo "$R"
else
    echo "no root: ~/.claude/skills/typescript-best-practices is not a link into the repo this skill lives in"
fi
```

It prints the root of the repo this skill lives in. Every path below that starts with `playbooks/`, `principles/` or `skills/` is from that root, and a path that starts with `references/` is beside this file. On `no root` the skill was loaded from somewhere else: the root is two directories above the real place of this file, not of a link to it.

Apply `principles/type-system-discipline.md` first: read it in full.

| Rule | Summary |
|------|---------|
| Discriminated unions | Model variants with a `kind` literal discriminant so impossible states can't be represented. No optional-field bags. |
| Branded types | Brand primitives with `& { readonly __brand: "X" }` so they can't be mixed up. Validate once at the boundary. |
| Constructive modeling | Build the shape so the illegal value can't be constructed. `[T, ...T[]]` for non-empty, `[T, T][]` for even length, `start` plus `duration` for a range. Not a runtime guard, not a wish for refinement types. |
| Simplest total type | Keep `T[]` while every operation on it stays total. Strengthen to `NonEmpty<T>` only where the loose type forces `!`, a cast, or a "should never happen" throw. |
| `unknown` over `any` | External data is `unknown`. |
| Schemas before guards | Before hand-writing a property-by-property type guard, use the repository's runtime schema library and infer the type from the schema, such as `z.infer`. |
| No `as` casts | Every `as` is a runtime crash waiting. Cast only after validation. |
| Narrowing hierarchy | Discriminant switch > `in` operator > `typeof`/`instanceof` > user-defined type guard > `as`. |
| Type guards | Must verify the claim. A lying guard is worse than `as` because the bug hides behind a name that says it's safe. Name them `isX` or `hasX`. |
| Exhaustiveness | Inline `const _exhaustive: never = x;` in default arms so the compiler errors when a new variant is added. |
| `satisfies` over `as` | Validates the value without widening literal types. |
| Boundary validation | Parse where data crosses in, into a named domain type. `Record<string, unknown>` (however spelled) stops at that parse. Trust types inside. See `principles/boundary-discipline.md`. |
| Schema-derived types | Reach for `Pick`/`Omit`/`Parameters`/`ReturnType`/`Awaited`/`typeof` before declaring a new interface. |
| Object args | Pass objects, not positional, so argument order is self-documenting. Skip on hot paths (per-frame render, tokenizers, parsers). |
| Real tests | Don't mock what you can run. Prefer the framework's real test primitives with leak/disposable checks, and verify UI in a running build. Mock only what you can't run locally. |
| Structured telemetry | Prefer structured logger diagnostics with enough context to debug from an id. No `console.log` in shipped code. |

Examples: `references/patterns.md`.
