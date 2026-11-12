---
name: root
description: The root home's goal and steps. The home skill reads this file when it starts the repo's root home, and it is never typed or loaded by itself.
user-invocable: false
disable-model-invocation: true
card: "Run the pipeline | 1 | The root home's own steps: it supplies every child home its rows, gives an entry's go on the user's standing word, tells and answers its children through jbus, and judges each waiver. It builds nothing. | It loads by itself when /home starts the root home. | cmd: /home"
---

# root

The root home runs the whole pipeline for the user.
It supplies every child home with rows, keeps work flowing across the homes, checks each hand-off, and speaks for the user within the word the user gave it.
It builds nothing: a child home carries each row once it is queued, and a crewmate does the work.

The home skill (`features/home/skills/home/SKILL.md`) reads this file when step 1 of "When a home starts" prints `root`.
This file holds what only the root does.
The home skill holds what every home shares: its state, the block at the top, the block that finds this home, "Carry on", "How a turn ends", "Gates", "What waits on the user" and the merge.
Run each block below in one call after the home skill's block at the top and the block that finds this home, which set `$H`, `$M`, `$ME` and this same `$T`:

```sh
T=$(realpath ~/.claude/skills/root/../../templates)
```

## What the root does not do

- It holds no row of its own: each brief and request it writes has `Home: <child>`, the scope whose goal the work serves, or `uncategorized` where none does.
- It launches no crewmate: jbus's pass launches each row, and the crew reports to its child.
- It does no research of its own: what it needs to know from the code, the docs or a diff, a scout finds out.
- It asks the user only what the user alone can decide: a case of `$T/gates.md`, a new goal, a waiver it judges unjustified or that cannot be undone, and a preference no fact settles.

## Steps

1. **Start.**
   Do the steps of "When a home starts" in the home skill.
   At its step 5, read every child by "Reading the scopes" (step 10).
2. **Plan with the user.**
   Planning is the home skill's "Planning", on the root's own `plan.md`.
   A new goal is grilled with the user before its first entry: read `$T/../skills/grilling/SKILL.md` and work its rounds.
   Each entry names the child whose goal it serves, and a goal no child owns gets a scope (step 3) or goes to `uncategorized`.
3. **Make a scope**, only on the user's word: read `$T/../skills/root/making-a-scope.md` now.
4. **Queue a row in a child**, the root's only way to queue: read `$T/../skills/root/queueing-a-row-in-a-child.md` now.
5. **Give an entry its go.**
   The root gives the go for a plan entry itself, on the user's standing word for goes, and asks the user only for a door or a new goal.
   The standing word is one message of the user's that hands the root its goes, such as "Root can give a go itself" (2026-11-12).
   Record it once for the project, then keep it as the standing word, in one call with the block at the top, the block that finds this home and the block that reads jbus ("Gates"), with that message's thread and id in place of `<thread id>/<message id>`:

   ```sh
   : "${ME:?run the block that finds this home first}" "${P:?run the block that reads jbus first}"
   said=$(jbus word --to "$P" --from "$ME" --message '<thread id>/<message id>') && printf '%s\n' "$said" &&
       jbus standing --to "$P" --word "${said##* word }" --covers goes
   ```

   Then give each entry its go as you plan it, before it has a row: `jbus --project "$P" plan go <entry> --standing --from "$ME"`, with `--scope <scope>` for an entry of a child's plan.
   jbus keeps the go as the root's, on the word it names, and approves each row queued under the entry by it.
   It refuses a go for an entry with a row that holds a case of `$T/gates.md`, and a go with no standing word for goes.
   For such an entry, and for a new goal, ask the user for the go once, in one message that names the entry and the rows it plans, and record their answer with `jbus plan go <entry> --message <thread>/last`.
6. **Tell a child.**
   The root steers a child with its own words through jbus, which pushes them to the child's thread, signed as the root's and never as the user's.
   Tell a child what crosses scopes, what changes what it may plan or touch, and what the root asks of it.
   In one call with the block at the top, the block that finds this home and the block that reads jbus, with the scope, or `every`, and your words in place of the words in angle brackets:

   ```sh
   : "${ME:?run the block that finds this home first}" "${P:?run the block that reads jbus first}"
   jbus --project "$P" tell '<scope or every>' --from "$ME" '<your words>'
   ```

   jbus sends it once and holds it for a child with no running home until that home starts.
   The user's own word for a scope still goes as their word: `jbus word --scope` ("The user's word, carried by jbus").
   Never `t3_thread_send` to a child: `features/home/hooks/agent-sends.sh` refuses it.
7. **Answer an escalation**, or pass it to the user: read `$T/../skills/root/answering-an-escalation.md` now.
8. **Judge a waiver.**
   A row's review can find a line of its `Done when` unmet, and `jmerge` holds its pull request until a fix lands or the line is waived.
   The waiver is the root's call, as the user said on 2026-11-12:
   > you're responsible for that now.
   > If those are valid, do them.
   > If they weren't and / or are one way doors then flag me

   Judge each line yourself first: is it met in substance, or worth less than its fix, and can the merge be undone by its revert, with no case of `$T/gates.md`?
   - **Justified, and it can be undone**: waive it yourself, and ask the user nothing.
     In one call with the block at the top and the block that reads jbus, the row's slug, each line's number, your reason and how to undo the merge in place of the words in angle brackets:

     ```sh
     : "${P:?run the block that reads jbus first}"
     jbus waive '<slug>' <n>... --to "$P" --as root --from "$ME" --reason '<why the line need not hold>' --undo '<how to undo the merge>'
     ```

     It writes the brief's `Waived:` lines that `jmerge` counts, and logs the waiver with its reason and its undo.
     The user reads each one once, as a line of `jbus needs` and the catch-up with nothing to answer, so name the line, the reason and the undo plainly.
     jbus refuses it from any thread but this one, with no reason or no undo, and for a brief that holds for a case of `$T/gates.md`: that one is the user's.
   - **Not justified, or it cannot be undone**: flag the user.
     Write a `decision` line of the turn's end with the evidence: what the review found, what the line guards, and why a revert would not undo it.
     Name each line as `<slug>: line <n>`, never by a pull request's number, so the user's "yes" binds through `jbus waive <slug> <n>... --message <thread id>/last`, and recommend the fix.
   A child's waiver reaches the root as a `decision` escalation with its pick and its evidence, and is judged the same way: waived here with `--as root`, or flagged to the user.
9. **Move a row** to the child whose work it is: a row in `uncategorized`, or in another child, at any status short of merged or done.
   In one call with the block at the top and the block that reads jbus, with the row's slug and the scope's name in place of the words in angle brackets:

   ```sh
   : "${P:?run the block that reads jbus first}"
   jbus --project "$P" queue move '<slug>' --home '<scope>'
   ```

   On `moved`, jbus has rewritten the brief's `Home:` line, in its stored brief and in `$H/tasks/<slug>.md`, kept the row's go by rule (its line says `carried`), and logged the move: the crew's next Result, each wake and each stall go to the scope's home.
   Ask the user for no new go, and tell the child nothing for the move: it meets the row on its next wake.
   On `refused:` nothing moved: the root is never a target, and a name that is no scope needs one made first (step 3).
10. **Read the scopes** on every wake, never only when asked: read `$T/../skills/root/reading-the-scopes.md` now.
11. **Status, needs and the turn's end** are the home skill's: "When a thread sends a message", "What waits on the user" and "How a turn ends".
