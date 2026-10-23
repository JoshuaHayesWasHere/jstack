# The provider instances

The doctor reads the provider inventory, `~/.config/jstack/providers.json`, and T3 Code's settings, and writes neither.
You write the inventory yourself, as [Configuration](../configuration.md#provider-instances) shows.

| Line | Meaning | Do this |
|---|---|---|
| `missing optional provider inventory -> <path>` | There is no inventory, so it declares no instance, and jstack uses only the built-in instance of each provider. | Nothing, or write the file. |
| `old optional provider inventory -> <why>` | The file is not in the shape of T3's `providerInstances`, so the doctor checks no instance. | Correct what `<why>` names. |
| `missing hard provider <id> -> T3 does not list it` | The inventory declares the instance, but T3's settings do not have it. | Add the instance in T3 Code with the same id, driver and home, or take it out of the inventory. |
| `old hard provider <id> -> <why>` | T3 lists the instance disabled, with another driver or another `homePath`, or its settings cannot be read. | Make the instance in T3 Code and the inventory say the same thing. |
| `missing hard skills <home> -> link it to <path>` | A declared Claude home has no `skills`. | Link `<home>/skills` to `~/.claude/skills`. |
| `old hard skills <home> -> <path>` | A declared Claude home's `skills` does not point at the central jstack skills, or one skill in it points elsewhere. | Link `<home>/skills` to `~/.claude/skills`. |
