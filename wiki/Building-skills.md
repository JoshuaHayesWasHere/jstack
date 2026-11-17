These skills take a change to a pull request.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `full-send` | Phrase: "full send" | Builds, proves, reviews, files, babysits, and merges a change while nobody watches. | tstack, with pstack rules |
| `full-stop` | Phrase: "full stop" | Does the same work as `full-send`, then stops with the PR ready for you. | tstack, with pstack rules |
| `file-pr` | Phrase: "file a PR" | Opens a short PR that leads with the problem. | tstack |
| `babysit-pr` | Phrase: "babysit" | Watches a PR through CI and review bots and fixes real findings. Uses one watcher per PR. | tstack |
| `leaving-pr-comments` | Automatic | Formats any comment an agent posts on GitHub for you. | tstack |
| `tdd` | Typed | Writes the failing test first, then the fix, when the bug has a cheap local test. | pstack |

`file-pr` and `babysit-pr` call `leaving-pr-comments`. `full-send` calls `sol-loop`, `file-pr`, and `babysit-pr`. See [[Modes]] for what the two modes may do.
