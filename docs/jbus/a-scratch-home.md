# A scratch home

A scratch home is a home with no repo, for throwaway questions and drafts.
Its threads run in T3 Code's "No project", whose workspace is `~/.t3/scratch`.
jbus carries your word to it and runs no step of a repo for it: no queue, no `jmerge`, no sweep, no CI, no reader of hot files or of what the threads noticed, and no snapshot of its tasks.
Nothing in it pushes, opens a pull request or launches a crew.

## Add it

Find the id T3 Code gives its "No project": `t3_project_list`, the entry whose `workspaceRoot` is `~/.t3/scratch`.
Then add the home, with a name you pick:

```sh
jbus project add scratch --scratch --project-id <that id>
```

The table it writes has `name`, `kind = "scratch"` and `projectId`, and no checkout and no webhook.
It is refused as a repo's table is: `refused: the config already has this project` for the same name and id, and `refused: the config already has a project of that name` for a name a project or another scratch home has.
The command takes `--checkout` for a repo or `--scratch` for a scratch home, one of the two and not both.

## The one place it is skipped

`jbus.load` reads each `[[project]]` table, and sorts one whose `kind` is `scratch` into the config's scratch homes and never into its projects.
Every step of a repo takes a project, so none of them is ever given a scratch home, and no step checks for one.
A `kind` that is neither `repo` nor `scratch` is refused, and a table with no `kind` is a repo, as every table before this was.

## Its thread, and your word

The home's thread is found as a repo's is: the first word of `~/.local/state/home/<name>/home-id`.
The home skill writes it when the thread starts as the scratch home (`features/home/skills/home/a-scratch-home.md`).

`jbus word --to <name>` sends your word to that thread, as [Your word to a home](your-word-to-a-home.md) says, and a word recorded `--from` the home's own thread is kept and not posted back.
`jbus word --all` is the home of every project, and a scratch home is none: a word about the repos does not reach it.
A word that waits, as one sent before the home's start wrote its `home-id`, goes on the next pass: the words that wait for its thread are the whole of a scratch home's pass.
It is a chore of the pass, run once a pass for the machine and for no project, so it runs in a config that has no repo project too.

## Where it shows

`jbus status` lists it under `scratch`, by name, with its `project_id` and its `home_thread`, the thread in its `home-id` or nothing, and no field of a repo's.
Its folder under `~/.local/state/home` is on the bus, so it is not among `homes_off_bus`.
The view shows it on the machine row, as `1 scratch home: <name>`, with each home's thread in the tip, and gives it no project's lane.
