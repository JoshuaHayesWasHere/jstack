# The status line

| Line | Meaning | Do this |
|---|---|---|
| `missing optional statusline <file>` | `<file>` has no `statusLine`, so nothing writes the limits file. | Run `sh install.sh`. |
| `old optional statusline <file> -> <command>` | The status line runs jgauge's `limits.sh` from another checkout. | Run `sh install.sh`. |

A status line of your own gets no line.
[Configuration](../configuration.md#the-limits-file) shows how to call `features/jgauge/hooks/limits.sh` from it.
