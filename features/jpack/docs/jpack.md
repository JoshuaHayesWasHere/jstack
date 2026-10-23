# jpack

`jpack` checks a repo's context pack, the notes that a home reads about that repo when the home starts.
It checks that each line a note cites exists, and that each quote is on the line it cites.
It calls no model and writes nothing.
[Context packs](context.md) says what a pack is, where it lives and who writes it.

## Check a pack

1. Go to the checkout of the repo the pack is about.
2. Run `jpack lint <repo>/docs/context`, then `jpack verify <repo>/docs/context`.
3. For each line they print, fix the note it names in a pull request to the pack.
4. To find the notes that cite a file changed since their pin, run `jpack stale <repo>/docs/context`.

## The verbs

| Verb | What it does |
|---|---|
| `jpack lint <pack>` | Checks that every note in `notes/` has a line in the index and lists a source, and that each source names a revision. Checks that the pack's `INDEX.md` has at most 40 lines that are not blank. |
| `jpack verify <pack>` | Checks that each citation `` `path:line` at <sha> `` is there: the commit, the path at it, the line, and the quoted words on the line. It also names each citation that quotes no words, and each source that names a commit and cites no line. |
| `jpack stale <pack>` | Lists each note that cites a path changed since its commit, as `stale <note>: <path> changed since <sha>`. It prints `prune <note>` for a note that has been stale for more than 14 days. |

| Flag | What it does |
|---|---|
| `jpack verify --repo <checkout>`, `jpack stale --repo <checkout>` | Reads that checkout in place of the one the pack is in. |
| `jpack stale --rev <rev>` | Reads `<rev>` as now, in place of `HEAD`. |
| `jpack stale --days <n>` | The days a note is stale before `jpack stale` lists it as `prune` (14). |

Each verb prints one line for each fault it finds and exits 1.
For a pack with no faults, it prints nothing and exits 0.
It exits 2 when the folder has no `notes/`, or when the pack is not in a git checkout.
