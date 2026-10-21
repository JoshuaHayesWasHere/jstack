# jdrift

`jdrift` lists what changed upstream in pstack since the commit `THIRD_PARTY.md` pins, for the files taken from it. Run it as `make pstack-drift`. It keeps a clone of the source under `${XDG_CACHE_HOME:-~/.cache}/jstack/`, and needs only `git` and the network. It prints `same`, `changed` or `gone` for each upstream path the map names, then `own` for each file on the `jstack's own:` line (a file here with no upstream, such as `principles/principle-depth-over-breadth.md`, which never drifts), then `new` for each upstream skill or playbook that the map does not name and `Not taken:` does not list. It changes nothing in this repo.

| Flag | What it does |
|---|---|
| `--diff` | Adds the unified diff under each `changed` line. |
| `--strict` | Exits 1 on a `changed`, `gone` or `new` line. |
| `--upstream <url>` | Clones another repo in place of `https://github.com/cursor/plugins`. |

`make` passes the flags on from `ARGS`, as in `make pstack-drift ARGS=--diff`.
