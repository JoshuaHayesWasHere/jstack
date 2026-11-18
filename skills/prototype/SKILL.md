---
name: prototype
description: Trigger this if the user says 'prototype' or '/prototype'. Explores a vague or open request on throwaway branches, tries several routes, and reports back with evidence and a recommendation. Never opens a PR.
metadata:
  group: Modes
  group-order: "1"
---

# Prototype

The user wants to learn something by building, not to ship. Take a vague
request, try several real routes on your own branches, and come back with
what each route taught and a recommendation. The work is likely throwaway, a
source of parts, or the start of the real build. The user decides which.

This is not **full-stop** or **full-send**. Those build one change toward a
PR. Prototype is allowed to be ambitious: try many approaches, including ones
the user did not ask for, and throw them away freely.

Before step 1, read `~/repos/jstack/docs/rules.md` in full. Its rules,
principles, playbooks, and subagent rules apply. Where it and this file
disagree, this file wins.

## Grant and limits

You may, without asking:

- Create branches named `proto/<slug>/<route>` and worktrees for them.
- Commit freely on those branches, production source included, so a route
  can be harvested or promoted later. Code quality, tests, and polish do not
  matter. The observation is the test.
- Run the app, dev servers, scripts, browsers, and other test methods the
  routes need.
- Push a `proto/` branch when a route is worth keeping, or needs CI or
  another machine. Keep it local otherwise.

Never, in this mode:

- Open a PR, mark anything ready for review, or merge.
- Commit to the default branch or to a branch you did not create.
- Delete a branch or worktree before the user answers the handoff question.

## Steps

1. **Restate, then go.** In your first message, restate the request in your
   own words: the goal, the question or decision the prototype exists to
   settle, what is unknown, and the routes you will try. Do not wait for a
   reply. Ask during the run only when a choice is product or taste and no
   route can settle it, with the harness's question tool.
2. **Pick the playbooks.** Use the prototype set in `rules.md`: investigation
   to understand what exists, prototype for a design or behavioral fork,
   runtime-forensics or trace-forensics for a live symptom or a captured
   artifact, eval for a skill or prompt change, multi-phase-plan when the
   output is a plan for a large change. A vague request often chains them,
   such as investigation, then prototype, then a plan. Copy the steps into
   your todo list.
3. **Plan at least two genuinely different routes** (the
   **principle-exhaust-the-design-space** skill). Different means a different
   mechanism, data shape, or architecture, not a parameter tweak. Include one
   route the user didn't ask for when you see one worth trying.
4. **Run the routes in parallel.** One worktree and one `proto/<slug>/<route>`
   branch per route, off the branch the user is on (the
   **principle-separate-before-serializing-shared-state** skill). Give each
   route to its own subagent per `docs/subagents.md`, or use **arena** when
   the routes are the same task on different models. Supervise. Read every
   diff yourself.
5. **Observe each route on the real surface.** Run it, drive it, log it,
   screenshot it, measure it. When the route has motion, interaction, or
   timing a still image can't show, also record a short video if the
   harness can (a preview or browser recording, or a screen recorder).
   Record what you observed, not what you expect.
   Vet any number with **benchmark-checklist**. A route that cannot be run is
   a sketch. Label it so.
6. **Refine the question.** Use what the routes showed to sharpen the request.
   When the answer changes the question, run another round with new routes.
   Stop when the decision is clear, or when the remaining ideas are marginal.
7. **Hand back.** Write the report (below), then ask the user, with the
   question tool, what to do with each route:
   - **Throw away.** Remove the worktrees and delete the branches.
   - **Harvest.** Name the commits or files worth keeping. They stay on their
     branch for the real build.
   - **Promote.** Continue that route with **full-stop** or **full-send** on
     its branch.
   Put your recommendation first. Act only on the answer. If no question tool
   is available, or it returns no answer, leave every branch and worktree in
   place and open your final message with the question.

## Report

- The restated goal and the question the prototype settled, or still can't.
- A table with one row per route: branch, approach, what you observed, and a
  verdict (works, partly works, fails, untested).
- Evidence for each row: paths to screenshots, video recordings, logs,
  timings, or command output. When a row's behavior would have suited a
  video but you couldn't record one, say why.
- The tradeoffs between the best routes.
- Your recommendation: throw away, harvest, or promote, and which route.
- Name the principles that shaped your choices.
- Say plainly which branches are throwaway.
