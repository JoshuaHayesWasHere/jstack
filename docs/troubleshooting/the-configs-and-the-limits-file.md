# The configs and the limits file

| Line | Meaning | Do this |
|---|---|---|
| `missing optional config <path> -> defaults are used: user, timezone, timezone_label` | You have no jstack config. Nothing is wrong. | Nothing, or write the file as [Configuration](../configuration.md#jstack) shows. |
| `old optional config <path> -> <why>` | The file is there and the commands refuse it. `<why>` names the key, or says the file does not parse. `jmerge` and `jbus` stop on the same line. | Correct what `<why>` names. |
| `missing optional patterns <path>` | You have no private patterns file. `jleak` checks only its built-in patterns, and both of its hooks refuse every push and every pull request command. | Run `sh install.sh`. It makes the file. Then fill in the names, as [jleak](../jleak.md#the-private-patterns) shows. |
| `missing optional roles <path> -> every role inherits the model of the thread that launches it` | You have no role map. Nothing is wrong. | Nothing, or run `sh install.sh --setup`, which writes one where every role is `inherit`. |
| `old optional roles <path> -> it cannot be read` | The path is a directory, or you cannot read it. | Remove it, or make it readable. |
| `old optional roles <path> -> bad line <n>: <line>` | `jroles` refuses the map, so every launch inherits. Each bad line is named, joined by `;`. | Correct each line as [jroles](../jroles.md) shows. |
| `missing optional jbus config <path> -> jbus does not run without it` | `jbus` is not set up. No timer runs. A home thread launches and settles, and you run `jmerge` or hand the merge to a home. | Nothing, or follow [Set up jbus](../jbus/set-up-jbus.md). |
| `old optional jbus config <path> -> <path> is mode <mode>, readable by others: chmod 600 it` | The file holds a key, and group or others can read it. | Run `chmod 600 <path>`. |
| `old optional jbus config <path> -> <why>` | `jbus` refuses the file. `<why>` is its own line: the file does not parse, lacks a key, or has a `loud` it cannot use. | Correct what `<why>` names. [Configuration](../configuration.md#jbus) has every key. |
| `old optional jbus config <path> -> jbus cannot read it: <error>` | The loader failed in a way it has no line for. `<error>` is the kind of error. | Compare the file with the example in [Configuration](../configuration.md#jbus). |
| `missing optional jbus sign-in <path> -> run jbus t3 login` | `jbus` has not signed in to T3 Code. | Run `jbus t3 login`. |
| `old optional jbus sign-in <path> -> holds no token, run jbus t3 login` | The sign-in file has no token in it. | Run `jbus t3 login`. |
| `old optional jbus sign-in <path> -> expired <date>, run jbus t3 login` | The sign-in ran out on `<date>`. | See [A T3 Code sign-in ran out](../troubleshooting.md#a-t3-code-sign-in-ran-out). |
| `old optional jbus sign-in <path> -> <path> is mode <mode>, readable by others: chmod 600 it` | The file holds a token, and group or others can read it. | Run `chmod 600 <path>`. |
| `missing optional limits <path> -> hooks/limits.sh writes it, as the status line` | Nothing has written the plan's limits yet. `jgauge room` cannot hold a launch back for the plan. | Start one Claude Code session after the install. With a status line of your own, see [Configuration](../configuration.md#the-limits-file). |
| `old optional limits <path> -> it cannot be read` | The path is a directory, or you cannot read it. | Remove it. `hooks/limits.sh` writes it again. |
| `old optional limits <path> -> it gives no limit` | No row of the file is a limit. | Remove it. `hooks/limits.sh` writes it again. |
| `old optional limits <path> -> every reset in it is past, nothing writes it now` | The file is stale. No Claude Code session ran since the last reset, or the status line no longer runs `hooks/limits.sh`. | Start one Claude Code session and run the doctor again. If the line stays, run `sh install.sh --check` and read its `statusline` line. With a status line of your own there is no such line: see [Configuration](../configuration.md#the-limits-file). |
