# The provider instances

The doctor reads the provider instances from T3 Code's settings, `providerInstances` in `~/.t3/userdata/settings.json`, and never writes them.
You add an instance in T3 Code, as [Configuration](../configuration.md#provider-instances) shows.

| Line | Meaning | Do this |
|---|---|---|
| `missing optional provider inventory -> <path>` | T3 has no settings file, so jstack uses only the built-in instance of each provider. | Nothing, or add the instances in T3 Code's settings. |
| `old optional provider inventory -> <why>` | T3's settings, or their `providerInstances`, are not in T3's shape, so the doctor checks no instance. | Correct what `<why>` names in T3 Code's settings. |
| `missing hard skills <home> -> link it to <path>` | A listed Claude home has no `skills`. | Link `<home>/skills` to `~/.claude/skills`. |
| `old hard skills <home> -> <path>` | A listed Claude home's `skills` does not point at the central jstack skills, or one skill in it points elsewhere. | Link `<home>/skills` to `~/.claude/skills`. |
