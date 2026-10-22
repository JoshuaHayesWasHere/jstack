# The skill links

Each skill link points into its harness's layout, which the install assembles from the release, or from a checkout ([The layouts](../jinstall.md#the-layouts)).

| Line | Meaning | Do this |
|---|---|---|
| `missing hard layout <harness> <folder>` | The install has not assembled that harness's layout yet. | Run `jinstall`. |
| `old hard layout <harness> <folder> -> stale: <paths>` | A file of the layout is missing or differs, a file is there that the install did not make, or the source has a skill the layout lacks. | Run `jinstall`. |
| `old hard layout <harness> <folder> -> <path> links to <href>, which is not in the tree` | A skill, playbook or template links to a file that neither the layout nor the source holds. | Install the release again. In a checkout, mend the link. |
| `old hard layout <harness> <folder> -> the source cannot be read: <why>` | The release, or the checkout, has no readable `skills.json` or `plugin.json`. | Install the release again. |
| `missing hard <home>/<root>/skills/<skill>` | The link for one skill is not there. `<root>` is `.claude`, which Claude Code reads, `.codex`, which Codex reads, or `.agents`, which Cursor reads. | Run `jinstall`. |
| `old hard <home>/<root>/skills/<skill> -> <path>` | The link points at another layout, at the copy an install before the layouts made, or at a worktree. | Run `jinstall`. It points the link into the layout. |
| `old hard <home>/<root>/skills/<skill> -> not a link` | A file or a directory is where the link goes. The install never replaces it. | Move it away, then run `jinstall`. |
| `old hard <home>/<root>/skills/<skill> -> <path>, a skill this checkout no longer has` | The link points into a layout, or where links went before the layouts, at a skill that was removed. | Run `jinstall`. It removes the link. |

A checkout of jstack has one more line here, `generated files are current`, in [The lines of a checkout](working-on-jstack.md#the-generated-files).
