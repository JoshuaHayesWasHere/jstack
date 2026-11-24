Every pull request an agent opens follows the shape that [`file-pr`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/file-pr/SKILL.md) sets, in every repository. The `full stop` and `full send` modes file their PRs with it. This page describes that shape. The skill is the source, so when the two disagree, the skill wins.

A description shows what changed for the user and proves that it works. It does not list the code that changed.

## Repository rules come first

- When the repository's PR template or contributing guide asks for more, such as a linked issue or a scope section, the agent adds it.
- When the repository's title convention differs, the agent follows the repository.

## Voice

The agent reads [`unslop`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/unslop/SKILL.md) and [`bro`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/bro/SKILL.md) before it drafts, and applies both to the title and to every line of the body.

- The Problem and Solution paragraphs get the strictest `bro` pass. They read like one person telling another what went wrong and what is different now, with no jargon.
- The agent rereads the whole body against the `unslop` list before it submits.
- Em dashes are not allowed. The `no-em-dash` hook blocks a `gh` or `git` command that sends one.

## Title

The title is a conventional commit, `type(scope): ...`, unless the repository's merged PRs use another style. It says what the user sees or gets, not the mechanism.

| Bad | Good |
| --- | --- |
| `perf(server): negotiate permessage-deflate on the websocket` | `perf(server): cut websocket frame size by 70%+ with gzipping` |

## Size

The description scales with the change.

| Change | Form |
| --- | --- |
| Small fix | A few short paragraphs with no headings, in this order: the problem, the fix, a `Proof:` line, a `Not verified:` line, and the footer. |
| A feature, or a change to more than one part of the product | The full form below, with headed sections. |

## Full form

The full form has these parts, in this order.

1. **Hero image.** A UI change opens with a screenshot of the result. The alt text says what the image shows.
2. **Problem.** One paragraph that tells a concrete situation from the user's original request: who hit it, what happened, and the real numbers. It does not open with a list of deleted functions or entry points.
3. **Solution.** One paragraph on what is different now, from the user's side.
4. **`## What changed`.** One bullet for each part of the product, led by its name in bold, such as **Server.**, **Web and desktop.**, **Agents.**, **Contracts.**, or **Docs.** A setting is named by its path in the UI, such as **Settings › General › Working tab group**. The section also says what happens in the parts that the change leaves alone, for example "Mobile does not use themes."
5. **Evidence.** See [Evidence](#evidence). In the small form it sits inline.
6. **`## Verification`.** Bullets for what the agent ran and what it saw. Each review finding that the agent fixed is listed with its commit SHA and the test that covers it. The section ends with the repository's check on changed files. "Tests pass" alone is not evidence. In `full stop` and `full send`, the section also names the playbook the agent followed.
7. **`## Notes`.** Calls that the reviewer has to make, such as a default, a budget that grows, or a performance cost. Stacking and merge order. Known limits. The section is left out when it has nothing to say.
8. **`## Not verified`.** The platforms, parts of the product, and cases that the agent did not check. The section is left out only when the agent checked everything the change touches.
9. **Footer.** See [Footer](#footer).

## Evidence

| Change | Evidence |
| --- | --- |
| Visual | A before and after table. |
| Motion or interaction | A GIF inline, with the mp4 linked below it as `Recording as mp4: <url>`. |

- The agent captures evidence from the real app at the final head commit. If a later push changes what the evidence shows, the agent captures it again and updates the description.
- Images and videos go to hosting that GitHub can reach, never into the repository. The usual host is a secret gist, with each file linked at a URL pinned to the gist commit.
- When the harness preview window cannot be captured, the agent uses headless Playwright with saved storage state.

## Footer

The footer has these lines, in this order.

1. A [`council`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/council/SKILL.md) section, when the change went through `council`.
2. The [`review-loop`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/review-loop/SKILL.md) line, when the change went through `review-loop`:

	```
	Reviewed with review-loop: <N> rounds with <model> at <effort>. Reviewer verdict: <verdict>.
	```

	The agent drops `at <effort>` when nobody reported the effort to it.
3. The model and harness that made the change, such as `Created with <model> in <harness>.` The line includes subagent models that wrote part of the change. When the harness does not report a model, the line names only the harness.

## Before the agent submits

- The agent checks the title, the body, quotes, and every screenshot for secrets, private email addresses, machine hostnames, window titles, terminal prompts, and file paths.
- The agent writes the body to a file and passes it with `--body-file`.
- The agent opens a real PR, not a draft, so that review bots run. When the GraphQL rate limit is used up, the agent opens it through the REST API.
- The agent posts a follow-up comment only when the request needs one, and formats it with [`leaving-pr-comments`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/leaving-pr-comments/SKILL.md).
