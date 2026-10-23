# jdrift

pstack is a set of agent skills for Cursor by Lauren Tan, in the `pstack` folder of `https://github.com/cursor/plugins`.
jstack took its principles and many of its skills and playbooks from pstack.
`jdrift` tells you what changed in pstack since jstack last took from it, so that you can bring pstack's changes into jstack.
It is a command for whoever maintains a copy of jstack.
You need it only to bring pstack's changes over.

## Check what changed upstream

1. Go to the root of a jstack checkout, where `THIRD_PARTY.md` is.
2. Run `jdrift`.
   To see each change as a diff, run `jdrift --diff`.
3. Read the `changed`, `gone` and `new` lines.
4. Open a pull request that copies the upstream changes you want.

`make pstack-drift` runs the same command and passes it the flags in `ARGS`, as in `make pstack-drift ARGS=--diff`.
Outside a checkout's root, `jdrift` prints `jdrift: THIRD_PARTY.md: No such file or directory, run this in the repo's root` and exits 2.

## What it reads and prints

`jdrift` reads two things from the pstack section of `THIRD_PARTY.md`: the pin, which is the commit of pstack that jstack last took from, and the map of files.
It keeps a clone of pstack under `${XDG_CACHE_HOME:-~/.cache}/jstack/` and updates it to pstack's `main`.
It needs only `git` and the network, calls no model, and changes nothing in the repo.

It prints one line for each upstream path the map names, then the lines for jstack's own files and pstack's new ones:

| Line | Means |
|---|---|
| `same` | The upstream file has not changed since the pin. |
| `changed` | The upstream file has changed since the pin, with the commits that changed it. |
| `gone` | The upstream file is no longer there. |
| `own` | A file on the `jstack's own:` line, which has no upstream and never drifts, such as `principles/principle-depth-over-breadth.md`. |
| `new` | An upstream skill or playbook that the map does not name and `Not taken:` does not list. |

| Flag | What it does |
|---|---|
| `--diff` | Adds the unified diff under each `changed` line. |
| `--strict` | Exits 1 on a `changed`, `gone` or `new` line. |
| `--upstream <url>` | Clones another repo in place of `https://github.com/cursor/plugins`. |
