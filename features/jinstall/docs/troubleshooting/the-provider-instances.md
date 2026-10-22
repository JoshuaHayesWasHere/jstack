# The provider instances

The doctor reads the provider inventory and T3 Code's settings, and writes neither.
[Configuration](../configuration.md#provider-instances) has the file.

| Line | Meaning | Do this |
|---|---|---|
| `missing optional provider inventory -> <path>` | No inventory is linked there, so no instance is declared. | Run infra's install, or leave it. |
| `old optional provider inventory -> <why>` | The file is not in the shape of T3's `providerInstances`. The doctor checks no instance. | Mend the file where infra declares it. |
| `missing hard provider <id> -> T3 does not list it` | The inventory declares the instance, and T3's settings do not have it. | Run infra's install, which renders T3's settings. |
| `old hard provider <id> -> <why>` | T3 lists the instance disabled, with another driver or another `homePath`, or its settings cannot be read. | Run infra's install, or mend the inventory. |
| `missing hard skills <home> -> link it to <path>` | A declared Claude home has no `skills`. | Link `<home>/skills` to `~/.claude/skills`. |
| `old hard skills <home> -> <path>` | A declared Claude home's `skills` points away from the central jstack skills, or one skill in it does. | Link `<home>/skills` to `~/.claude/skills`. |
