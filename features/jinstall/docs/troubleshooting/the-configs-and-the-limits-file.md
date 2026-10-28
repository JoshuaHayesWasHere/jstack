# The configs and the limits file

| Line | Meaning | Do this |
|---|---|---|
| `missing optional config <path> -> defaults are used: user, timezone, timezone_label, headroom, retry_cap, go, go_quiet_minutes` | You have no jstack config. Nothing is wrong. | Nothing, or write the file as [Configuration](../configuration.md#jstack) shows. |
| `old optional config <path> -> <why>` | The file is there and the commands refuse it. `<why>` names the key, or says the file does not parse. `jmerge` and `jbus` stop on the same line. | Correct what `<why>` names. |
| `missing optional patterns <path>` | You have no private patterns file. `jleak` checks only its built-in patterns. Both of its hooks refuse every push and every pull request command. | Run `jinstall`. It makes the file. Then fill in the names, as [jleak](../../../jleak/docs/jleak.md#the-private-patterns) shows. |
| `missing optional roles <path> -> every role inherits the model of the thread that launches it` | You have no role map. Nothing is wrong. | Nothing, or run `jinstall --setup`, which writes one where every role is `inherit`. |
| `old optional roles <path> -> it cannot be read` | The path is a directory, or you cannot read it. | Remove it, or make it readable. |
| `old optional roles <path> -> bad line <n>: <line>` | `jroles` refuses the map, so every launch inherits. The line names each bad line, joined by `;`. | Correct each line as [jroles](../../../jroles/docs/jroles.md) shows. |
| `missing optional jbus config <path> -> jbus does not run without it` | `jbus` is not set up. No timer runs. A home thread still launches and settles. You run `jmerge` yourself. | Nothing, or follow [Set up jbus](../../../jbus/docs/jbus/set-up-jbus.md). |
| `old optional jbus config <path> -> <path> is mode <mode>, readable by others: chmod 600 it` | The file holds a key, and group or others can read it. | Run `chmod 600 <path>`. |
| `old optional jbus config <path> -> <why>` | `jbus` refuses the file. `<why>` is its own line: the file does not parse, lacks a key, or has a value it refuses. | Correct what `<why>` names. [Configuration](../configuration.md#jbus) has every key. |
| `old optional jbus config <path> -> jbus cannot read it: <error>` | The loader failed with an error it has no line for. `<error>` is the kind of error. | Compare the file with the example in [Configuration](../configuration.md#jbus). |
| `missing optional ci report <path> -> no jbus config, so no project asks for it` | `jbus` is not set up, so it writes no weekly CI report. | Nothing. |
| `missing optional ci report <path> -> no project has ci_report = true, so jbus-ci.timer is off` | No project asks for the week's CI report, so the install leaves its timer off. | Nothing, or add `ci_report = true` to a `[[project]]` table, as [Configuration](../configuration.md#jbus) shows, then run `jinstall`. |
| `ok optional ci report <path> -> <names>` | Each project named asks for the week's CI report, and `jbus-ci.timer` is on. | Nothing. |
| `old optional ci report <path> -> <why>` | `jbus` refuses its config, so the install leaves `jbus-ci.timer` as it is. | Read the doctor's line for the jbus config, above. |
| `missing optional relay <path> -> no env file, so the relay is off` | The relay is an optional integration with a chat bot of your own, and it is off. Nothing sends alerts. | Nothing, or write its keys to `<path>` as [The relay](../../../jbus/docs/jbus/the-relay.md) says, then run `jinstall`. |
| `old optional relay <path> -> the relay would not start: <why>` | The relay would refuse the env file, so the install does not turn the relay on. A relay that is already on stays on. `<why>` names each key, never a value. | Correct each key `<why>` names, then run `jinstall`. |
| `missing optional jbus sign-in <path> -> run jbus t3 login` | `jbus` has not signed in to T3 Code. | Run `jbus t3 login`. |
| `old optional jbus sign-in <path> -> holds no token, run jbus t3 login` | The sign-in file has no token in it. | Run `jbus t3 login`. |
| `old optional jbus sign-in <path> -> expired <date>, run jbus t3 login` | The sign-in ran out on `<date>`. | See [A T3 Code sign-in ran out](../../../jbus/docs/troubleshooting/a-t3-code-sign-in-ran-out.md). |
| `old optional jbus sign-in <path> -> <path> is mode <mode>, readable by others: chmod 600 it` | The file holds a token, and group or others can read it. | Run `chmod 600 <path>`. |
| `missing optional limits <path> -> jgauge limits writes it, every 2 min` | Nothing has read that account yet. `jgauge room` and a launch cannot hold back for its plan. | Run `jgauge limits`. If the line stays, read the `units` line, because `jgauge-limits.timer` runs `jgauge limits`. |
| `old optional limits <path> -> it cannot be read` | The path is a directory. | Remove it. `jgauge limits` writes it again. |
| `old optional limits <path> -> <path> was written <n> min ago, 15 min or more: run jgauge limits` | The reader has not read that account for 15 min. Either the timer stopped, or neither the endpoint nor the cache answers. | Run `jgauge limits` and read its `stale <instance>: <why>` line. When a token has expired, that home's next Claude Code session signs in again and gets a new one. |
