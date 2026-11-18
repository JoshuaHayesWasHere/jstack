---
name: file-pr
description: File a pull request that shows what changed for the user and proves it works. Use when the user asks to file, open, or create a PR.
metadata:
  group: Ship
  group-order: "8"
---

# File PR

Before filing, check whether a PR for this branch already exists. Review the
diff locally against the base branch (usually `origin/main`) to make sure its
contents match the goal.

This is how every PR description is written, in every repo. When the repo's
PR template or contributing guide asks for more, such as a linked issue or a
scope section, add it. Where the repo's title convention differs, follow the
repo.

## Writing

Read [unslop](../unslop/SKILL.md) and [bro](../bro/SKILL.md) before you
draft. Apply both to the title and every line of the body. Problem and
Solution get the strictest bro pass: one person telling another what went
wrong and what is different now, with no jargon. Before you submit, reread
the whole body against unslop's list. Em dashes are out (unslop rule 13), and
the `no-em-dash` hook blocks a `gh` or `git` command that sends one.

## Title

PR titles usually become commit messages. Write a conventional commit
(`type(scope): ...`) unless the repo's history uses something else. Look at
recently merged PRs. Say what the user now sees or gets, not the mechanism:

BAD

> ❌ perf(server): negotiate permessage-deflate on the websocket

GOOD

> ✅ perf(server): cut websocket frame size by 70%+ with gzipping

> ✅ feat(web): resolved review conversations fold into avatars on their diff line

## Size

Scale the description to the change.

- **Small fix.** A few tight paragraphs with no headings: the problem, the
  fix, a `Proof:` line, a `Not verified:` line, then the footer.
- **Feature, or a change to more than one part of the product.** The full
  form below, with headed sections.

## Body

In this order:

1. **Hero image.** A UI change opens with a screenshot of the result. The
   alt text says what the image shows.
2. **Problem.** One paragraph, told as a concrete situation from the user's
   original prompt: who hit it, what happened, the real numbers. Do not lead
   with an implementation inventory:

   BAD

   > ❌ Removed implicit workspace carry-over from every "new thread" entry point (cmd+n / cmd+shift+o, sidebar v1/v2 buttons, command palette). New threads inherit only the project from context; branch, worktree, and env mode always come from the configured defaults. Deleted buildContextualThreadOptions, startNewThreadInProjectFromContext, and the v1 sidebar's seed-context machinery.

   GOOD

   > ✅ My "new worktree" default was ignored when starting new threads on existing worktrees. Super unintuitive. Now your preferences always apply.

3. **Solution.** One paragraph on what is different now, from the user's
   side.
4. **`## What changed`.** One bullet per part of the product, led by its name
   in bold: **Server.**, **Web and desktop.**, **Agents.**, **Contracts.**,
   **Docs.** Name a setting by its path in the UI, such as **Settings ›
   General › Working tab group**. Say what happens in the parts the change
   leaves alone: "Mobile does not use themes."
5. **Evidence.** See below. In the small form it sits inline.
6. **`## Verification`.** Bullets for what you ran and what you saw. List
   each review finding you fixed, with its commit SHA and the test that
   covers it. End with the repo's check on changed files (`vp run
   check:changed` in T3 Code). "Tests pass" alone is not evidence.
7. **`## Notes`.** Calls the reviewer has to make, such as a default, a
   budget that grows, or a performance cost. Stacking and merge order. Known
   limits. Leave the section out when there is nothing to say.
8. **`## Not verified`.** The platforms, parts of the product, and cases you
   did not check, stated plainly. Leave it out only when you checked
   everything the change touches.
9. **Footer.** See below.

## Evidence

- A visual change gets a before and after table.
- Motion or interaction gets a GIF inline and the mp4 as a link below it:
  `Recording as mp4: <url>`.
- Capture from the real app at the final head. If a later push changes what
  the evidence shows, capture it again and update the description.
- Upload images and videos to hosting that GitHub can reach. Never commit
  them to the repo. A secret gist works, and `gh gist create` makes one by
  default. Create it with a README, clone the gist, add the files, commit,
  and push. Link each file at
  `https://gist.githubusercontent.com/<user>/<id>/raw/<sha>/<file>`, pinned to
  that commit.
- When the harness's preview window cannot be captured, use headless
  Playwright with saved storage state.

## Footer

When the change went through `sol-loop`, add its line first:

`Reviewed with sol-loop: <N> rounds with <model> at <effort>. Sol verdict: <verdict>.`

Drop `at <effort>` when the effort was not reported to you. A `council`
section goes above both lines.

End with the public model name and harness that made the changes, for example
`Created with <model> in <harness>.` Include subagent models that wrote part
of the change. Use the model name the harness reports. If model identity is
unavailable, name the harness without guessing a model.

## Before you submit

Check the title, description, quotes, and attachments for secrets and private
details. Never include the user's private email address or a machine
hostname. Look at every screenshot for them too: window titles, terminal
prompts, and file paths.

Write the body to a file and pass it with `--body-file`. Open a real PR rather
than a draft so review bots run. If `gh pr create` fails because the GraphQL
rate limit is used up, open it through REST with
`gh api repos/<owner>/<repo>/pulls -f title=... -f head=... -f base=... -F body=@<file>`.
If the user also asked to babysit it, continue with the `babysit-pr` skill.

Do not post a follow-up PR comment unless it serves the user's request. When a
comment is needed, use the `leaving-pr-comments` skill.
