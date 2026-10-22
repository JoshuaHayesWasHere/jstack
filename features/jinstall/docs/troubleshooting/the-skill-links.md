# The skill links

Each skill link points into its harness's layout, which the install assembles from the checkout or the release ([The layouts](../jinstall.md#the-layouts)).

| Line | Meaning | Do this |
|---|---|---|
| `old hard generated files are current -> stale: <path>` | A skill, playbook, template or hook was added or changed after the generator ran, so `skills.json` does not list it yet. | Run `python3 scripts/generate-jstack-trees.py` in the checkout and commit what it writes, then run `sh install.sh`. |
| `missing hard layout <harness> <folder>` | The install has not assembled that harness's layout yet. | Run `sh install.sh`. |
| `old hard layout <harness> <folder> -> stale: <paths>` | A file of the layout is missing or differs, a file is there that the install did not make, or the source has a skill the layout lacks. | Run `sh install.sh`. |
| `old hard layout <harness> <folder> -> <path> links to <href>, which is not in the tree` | A skill, playbook or template links to a file that neither the layout nor the source holds. | Mend the link in the checkout. |
| `old hard layout <harness> <folder> -> the source cannot be read: <why>` | The checkout or the release has no readable `skills.json` or `plugin.json`. | Run the generator in a checkout, or install the release again. |
| `missing hard <home>/<root>/skills/<skill>` | The link for one skill is not there. `<root>` is `.claude`, which Claude and Cursor read, `.codex`, which Codex reads, or `.agents`, which Codex, Cursor and Grok read. | Run `sh install.sh`. |
| `old hard <home>/<root>/skills/<skill> -> <path>` | The link points at another layout, at the copy an install before the layouts made, or at a worktree. | Run `sh install.sh` in the checkout you want live. It points the link into the layout. |
| `old hard <home>/<root>/skills/<skill> -> not a link` | A file or a directory is where the link goes. The install never replaces it. | Move it away, then run `sh install.sh`. |
| `old hard <home>/<root>/skills/<skill> -> <path>, a skill this checkout no longer has` | The link points into a layout, or where links went before the layouts, at a skill that was removed. | Run `sh install.sh`. It removes the link. |
