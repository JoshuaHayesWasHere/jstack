# jbriefs

`jbriefs` writes one HTML page of every home under `~/.local/state/home/`: each repo's handoff, its open plan entries, and every brief with its result. It prints the page's path. It reads the files alone, and asks neither T3 Code nor GitHub.

| Argument | What it does |
|---|---|
| `state` | The directory that holds one home per repo. Defaults to `~/.local/state/home`. |
| `--out <path>` | Where to write the page. Defaults to `$XDG_CACHE_HOME/jbriefs/briefs.html`, or `~/.cache/jbriefs/briefs.html`. |
