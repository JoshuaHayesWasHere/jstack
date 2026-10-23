# Add a project

`jbus project add <name> --checkout <path> --project-id <id>` adds one `[[project]]` table at the end of the config, for a repo that is not in the config yet.
You do not edit the file by hand for it.
`/new-home <repo>` runs the command as its third step.

Every repo with a home is a project.
`/new-home <repo>` adds it as its third step, and a home's start adds it when the config has no table for its repo.
The home finds the repo's T3 Code project by its checkout and runs the same block as `/new-home`, so the two add a repo the same way.
Neither one writes `home-thread`, even if a home's rules say to.
No home merges while `home-thread` is empty, so jbus merges for a repo that either one adds, unless the user has written a thread id into `home-thread` by hand.

jbus names each home that was never added.
Each folder under `~/.local/state/home` with a `home-id` and no project of the config is a home not on the bus.
A party's folder, `_<name>`, such as an expert's, is no repo's home, and jbus does not name it.
A folder that is a link to a project's home is that home.
The pass says `homes not on the bus: <names>` in the journal when the list changes, and `jbus status` prints the list as `homes_off_bus`.
While there is one, the view's machine row shows a Homes item with the count, and the names in its tip.
jbus adds none of them: `jbus project add` adds one, or the home's next start does.

- `<name>` is the repo's folder name, which is also the name of its directory under `~/.local/state/home`.
- `--checkout` is the path of the repo's main checkout.
- `--project-id` is the id of the repo's T3 Code project.
  Step 3 of [Set up jbus](set-up-jbus.md#3-add-your-first-project) says how to find it.

To add a home with no repo, use `--scratch` in place of `--checkout`.
[A scratch home](a-scratch-home.md) says what it writes and what jbus does for it.

The command first copies the config to `config.toml.<time>.bak` beside it.
Both files are mode 600.
Every other table stays as it is.
The new table has `name`, `checkout` and `projectId`, and no webhook.
The new project uses the top-level webhook when the config has one ([Events and the webhook](events-and-the-webhook.md)).
With none there, jbus POSTs nothing for it.
A scratch home's table has `name`, `kind` and `projectId` instead.

It prints `added: one [[project]] table, the file as it was is <backup>: the next pass works it, restart no unit`.
Each pass is a new run of `jbus poll` that loads the config, so no unit needs a restart.
No line it prints shows the value of any key in the config.

It refuses, and writes nothing, in these cases:

| Line | Why |
|---|---|
| `refused: the config already has this project` | A table has that name, that checkout and that id. A second run changes nothing. |
| `refused: the config already has a project of that name` | A table has that name, or keeps its state under it, with another checkout or id. |
| `refused: the config already has a project with that checkout` | A table of another name has that checkout. |
| `refused: --checkout is not a directory` | The path is no directory on this machine. |
| `refused: a project's name is letters, digits, dots, dashes and underscores` | The name has another character in it. |
| `refused: --project-id is empty` | The id is empty. |
| `refused: no config at <path>` | jbus is not set up yet. [Set up jbus](set-up-jbus.md) comes first. |

The command takes `--checkout` or `--scratch`, one of the two.
With both or neither, it prints its usage, exits 2, and writes nothing.
