## Answering an escalation

A child reaches the root only by `jbus stop` ("Escalating to the root" in `features/home/skills/home/scoped-homes.md`).
jbus carries each escalation here as one message that needs `decide`: it names the scope, the row or the entry, the kind, and what the root must clear.
Answer each one once, by its kind:

- **`door`**: a one-way door holds the child's row, and the child has parked it as a gate.
  Investigate, sending a scout first if you need facts, then answer with your recommendation.
  The child adds it to its gate, and the user alone opens or refuses the door.
  A door is never passed: its gate holds for the user already.
- **`decision`**: decide it yourself, in the light of the child's goal and the user's words under its entry's `Decisions:`, and answer with the decision and why.
  A waiver of a `Done when` line is judged as "Judge a waiver" says.
  Pass it to the user only where it is a new goal, a case of `$T/gates.md`, or a preference of the user's that no fact settles.
- **`go`**: give the entry its go yourself by "Give an entry its go", then answer that the go holds.
  Pass it to the user only where your standing word does not cover it: a new goal, or a row that holds a case of `$T/gates.md`.

The root writes nothing into a scope's files: its answer is the only thing it sends for an escalation.
In one call with the block at the top, the block that finds this home and the block that reads jbus ("Gates"), with the scope, the child's row or entry, and your words in place of the words in angle brackets:

```sh
: "${ME:?run the block that finds this home first}" "${P:?run the block that reads jbus first}"
jbus --project "$P" stop answer '<scope>' '<row or entry>' '<the answer>' --from "$ME"
```

To pass it to the user instead, run the same call with `stop pass` in place of `stop answer` and your recommendation in place of the answer.
jbus parks it as a gate on the child's slug, `home-<scope>`, which holds for the user, and carries the user's answer to the child.
`--from` comes last.
jbus closes every open escalation of that row or entry and carries the reply to the child's home, once.
