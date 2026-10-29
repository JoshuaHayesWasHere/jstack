# jstack

`jstack` runs each of jstack's other commands by one name: `jstack <name> ...` runs what `j<name> ...` runs.
It takes the name with no leading `j`, and passes every word after it to that command as it is.
The usage, the help, the output and the exit code are the command's own.
The other names stay on `PATH`, so the skills, units and hooks that name them keep working.

| Name | Runs |
|---|---|
| `jstack briefs` | `jbriefs` |
| `jstack bus` | `jbus` |
| `jstack drift` | `jdrift` |
| `jstack gauge` | `jgauge` |
| `jstack install` | `jinstall` |
| `jstack leak` | `jleak` |
| `jstack merge` | `jmerge` |
| `jstack pack` | `jpack` |
| `jstack roles` | `jroles` |

`scripts/generate-jstack-trees.py` writes the table `jstack` reads from each feature's `commands`, so a new command needs no line in `jstack`.
`jstack` imports the module of the name typed and no other, so it starts as fast as the command does.
With no name, or a name it does not have, it prints its usage and exits 2.
