# The status line

| Line | Meaning | Do this |
|---|---|---|
| `missing optional statusline <file>` | `<file>` has no `statusLine`, so nothing writes the limits file. | Run `jinstall`. |
| `old optional statusline <file> -> <command>` | The status line runs jgauge's `limits.sh` from another layout or copy. | Run `jinstall`. |

The doctor prints no line for a status line of your own.
[Configuration](../configuration.md#the-limits-file) shows how to call jgauge's `limits.sh` from it.
