# Prototype

Run by: a crewmate, for a design decision that only something built and looked at can settle (which layout, which interaction, which behaviour or timing), in a brief with `Pull request: ask first` and `Review: none`.

Source: pstack, `pstack/skills/poteto-mode/playbooks/prototype.md`

<!-- card: Decide by building | 1 | A design decision that only something built and looked at can settle: which layout, which interaction, which timing. | plain: `Pull request: ask first`; plain: `Review: none` -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

Verify skill: `.claude/skills/verify-*/`.

**You own the design decision, not the code.** The prototype is a throwaway instrument, and the real build is another task. This is the one playbook where the smallest change of `principles/principle-laziness-protocol.md` and the usual bar of proof turn over: speed over polish, code quality does not matter, no planning. The rigour is in picking the right design cheaply. Propose a variant nobody asked for, throw an approach away and try another.

1. Write the decision the prototype exists to make, in one line, and what you would have to see to settle it. No decision, no prototype: a brief that asks for a thing to be built is `playbooks/feature.md`'s. Stop and say so in the Result.
2. When the design space is open, gather references before building: prior art in the repo and outside it, summed up as three or more directions (themes, layouts, approaches), each in a line. Pick the two or three to build and say why. The user may redirect in this thread, and you do not wait for it (`principles/principle-never-block-on-the-human.md`). When the brief sets the direction: `skip: the brief sets the direction`.
3. Make the scratch directory, outside the repo's source: `mktemp -d /tmp/<slug>-proto.XXXXXX`. Everything you build goes there. For a visual decision, plain HTML, CSS and JavaScript, or the lightest stack that renders the idea. For a behaviour or a timing, the smallest script that exercises the question. No production framework, no tests, no abstractions. Run `git status --porcelain` in the worktree and see it print nothing.
4. Build the alternatives behind one switcher (buttons, a keypress, or one argument to the script), each variant labelled with a name the Result can use (`principles/principle-exhaust-the-design-space.md`). One switcher, so that every variant is seen under the same conditions.
5. Observe on the surface the decision is about: the repo's verify skill where it has one, otherwise the surface the brief names. For a visual decision, a screenshot of each variant, and the interaction driven. For a behaviour or a timing, the output printed or the timing logged, per variant. The observation is the test here, not an assertion (`principles/principle-prove-it-works.md`). Keep each one in the scratch directory, named for its variant.
6. Write the alternatives, what each costs and gives, and one recommendation. Recommend what the user will meet with delight over what is easier to build, and fewer polished parts over more rough ones (`principles/principle-experience-first.md`). When the decision is visual, put them on one page: an HTML file in the scratch directory that shows every variant's screenshot beside its tradeoffs, opened with `lavish-axi <the file>` (`lavish-axi --help` has the rules for a page). The page shows and takes no input: the pick is the user's word, in this thread or to the home. When `command -v lavish-axi` prints nothing, make no page: the Result of step 7 has each variant, what was seen of it and the recommendation, in words.
7. End as `skills/crew/SKILL.md` "End" says for a task with no pull request. The Result has the variants by name, what was seen of each, the recommendation, the scratch path, the page's link where there is one, and one plain sentence that the prototype is throwaway. `/tmp` does not outlast a reboot, so what was seen is written out in the Result, in words and numbers, and the pick can be made from the Result alone. A pick that only the user can make is parked as a gate, with your recommendation as its default.

Never done here, and who does it:

- **Shipping the prototype's code, or committing it to the branch.** A crewmate builds the chosen direction, from a new brief with `playbooks/feature.md`. The home plans it from the Result.
- **A pull request.** Nobody opens one: the branch has no commit, and the brief says `Pull request: ask first`.
- **Tests, types and cleanup of the throwaway.** Nobody does: it is deleted, not kept.
- **Variants built by subagents side by side.** Nobody does: one thread, one switcher, so the variants can be compared.
- **Waiting for the user's pick.** The user picks when they read the Result. The gate holds the question.

**Hand over:** in the Result, to the home and the user: the decision, the variants explored, the evidence for each (screenshots for a visual decision, the observed output or timing for a behaviour), the tradeoffs, your recommendation, and the scratch path. Say plainly that the prototype is throwaway.
