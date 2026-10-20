# Add a project

`jbus project add <name> --checkout <path> --project-id <id>` adds one `[[project]]` table at the end of the config, for a repo jbus does not look after yet. You do not edit the file by hand for it, and `/new-home <repo>` runs the command as its third step.

Every repo with a home is a project. `/new-home <repo>` adds it as its third step, and a home's start adds it when the config has no table for its repo ("On the bus" in `skills/home/SKILL.md`): the home finds the repo's T3 Code project by its checkout and runs the same block as `/new-home`, so the two add a repo the same way. Neither ever writes `home-thread`, whatever a home's rules say, so a repo they add is one jbus merges for, unless the user has put an id in that switch by hand.

A home that was never added is named. Each folder under `~/.local/state/home` with a `home-id` and no project of the config is a home not on the bus. A party's folder, `_<name>`, as an expert's is, is no repo's home and is not named, and a folder that is a link to a project's home is that home. The pass says `homes not on the bus: <names>` in the journal when the list changes, `jbus status` prints it as `homes_off_bus`, and the view's machine row shows a Homes item with the count, and the names in its tip, while there is one. jbus adds none of them: `jbus project add`, or the home's next start, does.

- `<name>` is the repo's folder name, which is also the name of its directory under `~/.local/state/home`.
- `--checkout` is the path of the repo's main checkout.
- `--project-id` is the id of the repo's T3 Code project.

The command first keeps the file as it was, beside it, as `config.toml.<time>.bak`. Both files are mode 600. Every other table stays as it is, and the new table has `name`, `checkout` and `projectId` and no webhook. The new project takes the top-level webhook at the top of the config when there is one ([Events and the webhook](events-and-the-webhook.md)). With none there, jbus POSTs nothing for it.

It prints `added: one [[project]] table, the file as it was is <backup>: the next pass works it, restart no unit`. Each pass is a new run of `jbus poll` that loads the config, so no unit is restarted. No line it prints has a value of a key of the config.

It refuses, and writes nothing, in these cases:

| Line | Why |
|---|---|
| `refused: the config already has this project` | A table has that name, that checkout and that id. A second run changes nothing. |
| `refused: the config already has a project of that name` | A table has that name, or keeps its state under it, with another checkout or id. |
| `refused: the config already has a project with that checkout` | A table of another name has that checkout. |
| `refused: --checkout is not a directory` | The path is no directory on this machine. |
| `refused: a project's name is letters, digits, dots, dashes and underscores` | The name has another character in it. |
| `refused: no config at <path>` | jbus is not set up yet. [Set up jbus](set-up-jbus.md) comes first. |
