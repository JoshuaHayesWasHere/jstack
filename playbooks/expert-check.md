# Expert check

Run by: an expert, for a `check` ask: one brief, review or pull request to judge against the subject.

Source: this repo

<!-- card: An expert runs it | 2 | A `check` ask: one brief, review or pull request judged against the subject. It ends in a verdict in four parts, each point tied to the rule it rests on. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/expert/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the verdict.** A check reads one artifact and judges it against the subject. It changes nothing in the artifact, approves nothing and blocks nothing: `skills/expert/SKILL.md` "What an expert never does". Every point of the verdict names the rule it rests on, and a point with no rule is not in the verdict.

1. Pin the artifact. Read the real thing as it is now, never the ask's account of it (`principles/principle-prove-it-works.md`): a brief or a review from its file, a pull request by its url, with `gh pr view <url> --json title,body,headRefOid,files`, then `gh pr diff <url>`, then `headRefOid` once more: a head that moved is read again. Write down the revision you judged: that head, a file's commit or, for a file in no repo, the time you read it. A diff too long to hold goes to one `Explore` subagent, given the url and the path of `CHARTER.md`: it returns each hunk that touches the subject, with its path and lines, and the paths it left out, and you keep that reply and never the whole diff (`principles/principle-guard-the-context-window.md`). An artifact you cannot read is `not judged`.
2. List what the artifact claims, assumes or asks for where the subject has a say, each with its place in the artifact: a path and line, or a section. What the artifact as a whole rests on is the first of them. These are the points: what is outside the subject is the reviewer's. With none, the verdict is `not judged`: the artifact does not touch the subject.
3. Find the rule for each point, in the order of `skills/expert/SKILL.md` "When layers disagree": the corrections, then the source as it is now, then the notes the index points at. A note says where to look: take the rule from the source itself. Write the rule as a pointer, a file and line at a revision or the correction's line, and do not copy its text (`principles/principle-laziness-protocol.md`). A point with no rule found, one you know from memory alone included, leaves the list: it goes under "Not checked" in step 5, labelled "from memory, not checked" where that is so, and in `unknowns.md` in step 6.
4. Judge each point against its rule: it `agrees` or `conflicts`, and one that conflicts says in a line what the rule asks for. When the point the artifact rests on conflicts, each point that stands only with it conflicts too, by that same rule, and says so (`principles/principle-attack-the-premise.md`).
5. Write the answer in the four parts of `templates/expert-answer.md`: read it now, it is the one copy of them. Under Answer, the verdict comes first: `holds` when a point agrees and none conflicts, `does not hold: <n> conflicts`, or `not judged: <why>`, which is also the verdict when no point kept a rule. Then one line a point, the conflicts first: `<place in the artifact>: <agrees | conflicts>, <what, in a few words>, by <the rule>`. Under Sources, the artifact at the revision of step 1, and each rule once. The confidence is the tier of the weakest point the verdict rests on, and Inferred at best when a subagent chose what you read. Under "Not checked": the points with no rule, the parts of the artifact you did not read, the paths a subagent left out, and that nothing was run.
6. Read the answer once against the points of step 2 before you send it: each is in a line that ends in its rule, or under "Not checked". Then send it to who asked, and write down what was new as step 4 of `skills/expert/SKILL.md` "An ask" says. A verdict of `does not hold` also goes to the artifact's owning home as a gate, sent as "What an expert never does" says, whoever asked. Its `<about>` is the artifact, a brief's slug or `pr-<number>`, and its question names the artifact at the revision of step 1, so the same check sent twice is one gate.

Never done here, and who does it:

- **A fix to the artifact.** A crewmate does it, from a brief the owning home writes.
- **An approval, a block or a merge.** The owning home and the user decide. `holds` is what the subject says of the artifact, never a go-ahead.
- **A review of the change.** The reviewer does. A defect outside the subject is one line under "Not checked".
- **A run of the artifact's tests or code.** Nobody does: a check reads. What only a run would settle goes under "Not checked".

**Hand over:** in the answer, to who asked: the verdict, each point with its place in the artifact and the rule it rests on, and what was not checked. A verdict of `does not hold` goes to the owning home as a gate.
