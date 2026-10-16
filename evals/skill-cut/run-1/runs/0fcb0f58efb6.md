First, I check for an authoritative schema that owns Task (migration, OpenAPI, proto) and derive from that if one exists. If none does, I restructure the type instead of adding another optional field, following the opening rule "make illegal states unrepresentable" and its "exhaust variants" step. The line I write:
`type Task = { status: 'open' } | { status: 'done'; doneAt: Date } | { status: 'cancelled'; cancelledAt: Date };`
Then every `switch (task.status)` gets an `assertNever(task)` default, so the compiler flags any site that doesn't handle `'cancelled'`.
The parser at each boundary also has to build the matching variant, because the old type allowed `{ status: 'open', doneAt }` and that shape is now rejected.
