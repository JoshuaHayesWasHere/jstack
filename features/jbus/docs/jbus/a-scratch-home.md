# A scratch home

A scratch home is a home with no repo, for throwaway questions and drafts.
Its threads run in T3 Code's "No project", whose workspace is `~/.t3/scratch`.
jbus sends your word to it and runs no step of a repo for it: no queue, no `jmerge`, no sweep, no CI, no reader of hot files, and no snapshot of its tasks.
Nothing in it pushes, opens a pull request or launches a crew.

## Add it

Find the id that T3 Code gives its "No project", the project whose folder is `~/.t3/scratch`.
Step 3 of [Set up jbus](set-up-jbus.md#3-add-your-first-project) shows how to find a project's id.
Then add the home, with a name you pick:

```sh
jbus project add scratch --scratch --project-id <that id>
```

The table it writes has `name`, `kind = "scratch"` and `projectId`, and no checkout.
The command refuses it the way it refuses a repo's table.
It prints `refused: the config already has this project` for the same name and id.
It prints `refused: the config already has a project of that name` when a project or another scratch home already has the name.
The command takes `--checkout` for a repo or `--scratch` for a scratch home, one of the two and not both.

## How a pass treats it

A table whose `kind` is `scratch` is a scratch home, and never one of the config's projects, so no step of a repo runs for it.
jbus refuses a `kind` that is neither `repo` nor `scratch`, and reads a table with no `kind` as a repo.

## Its thread, and your word

jbus finds the home's thread as it finds a repo's, in the first word of `~/.local/state/home/<name>/home-id`.
The home skill writes it when the thread starts as the scratch home (`features/home/skills/home/a-scratch-home.md`).

`jbus word --to <name>` sends your word to that thread, as [Your word to a home](your-word-to-a-home.md) says.
When a word is recorded `--from` the home's own thread, jbus keeps it and does not post it back to that thread.
`jbus word --all` goes to the home of every project.
A scratch home is no project's home, so a word about the repos does not reach it.
A word that waits, such as one sent before the home's start wrote its `home-id`, goes on the next pass.
Sending the words that wait for its thread is all a pass does for a scratch home.
That step, `word.scratch`, is a chore.
A chore runs once a pass, for the machine and for no project, so this step also runs in a config that has no repo project.

## Where it shows

`jbus status` lists it under `scratch`, by name, with its `project_id` and its `home_thread`, the thread in its `home-id` or nothing, and no field of a repo's.
Its folder under `~/.local/state/home` is on the bus, so it is not among `homes_off_bus`.
The view shows it on the machine row, as `1 scratch home: <name>`, with each home's thread in the tip, and gives it no project's lane.
