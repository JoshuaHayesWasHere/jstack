These skills prove that work is right, or check how it reads.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `create-verification-skill` | Typed | Writes a project skill that drives your app the way a user does, so agents can prove changes. | pstack |
| `maintain-verification-skill` | Typed | Brings that project skill back in line with the app. Opens at most one PR of proven corrections. | pstack |
| `create-formal-verification-skill` | Typed | Proves one property of hard code, such as a race or a retry, with a model checker or proof tool. Writes a project skill that checks it again on each change. | pstack |
| `maintain-formal-verification-skill` | Typed | Updates the formal model after the code changes. Says whether each failure is drift or a real bug. | pstack |
| `technical-writing` | Typed | The writing standard for docs, READMEs, PR descriptions, and commit messages. | pstack |
| `council` | Phrase: "council" | Gets review from three models on three providers. Loops until all three agree. | tstack |
| `sol-loop` | Phrase: "sol loop" | Gets review from GPT Sol in a loop until both agents agree. | tstack |
| `interrogate` | Typed | Has models from different vendors try to break a diff. Keeps only the findings a run proves. | pstack |
| `benchmark-checklist` | Typed | Checks a measured number before anyone reports it or acts on it. | pstack |

`council`, `sol-loop`, and `interrogate` take their models from `docs/models.md`. See [[Models and seats]].
