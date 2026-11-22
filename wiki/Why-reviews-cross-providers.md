A model that reviews its own work tends to agree with itself. It shares the same blind spots as the model that wrote the code, so the mistakes that one misses, the other misses too. A second model from the same vendor helps less than you might expect for the same reason.

jstack's review skills mix vendors on purpose:

- `council` asks three models across providers.
- `review-loop` defaults to Gemini 4 Neon, from Google, to review work that a Claude model usually wrote (or whichever model you name in `<model> loop`).
- `arena` picks its judge from a vendor other than the one running the chat.
- `interrogate` gives the same diff to models from different vendors and keeps only the findings that a run proves.

## What it found in practice

The council review of jstack itself is an example. All three reviewers caught a contradiction in how the modes handled prototype forks. Only Gemini caught that a condensed rule had reversed upstream's ban on disabling checks. Sol was the first to reproduce a case where the worktree audit called an unused branch merged. Each vendor found something the others did not.

## What it costs

Cross-provider review needs access to each configured provider. T3 Code gives that access through `delegate_task`. Outside T3 Code, a seat from another provider runs on the current model, and the skill says so. The review still runs, but with less disagreement to learn from.

Where each seat runs is set in one place, `docs/models.md`. See [[Models and seats]].
