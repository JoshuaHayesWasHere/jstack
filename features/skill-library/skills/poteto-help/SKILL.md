---
name: poteto-help
description: "Answer a help question about jstack: how to get set up, which role takes a piece of work, and which playbook and skills fit a brief, a scout's request or a plain question, each with the file it came from. Type /poteto-help with a question, a brief's path or its slug."
disable-model-invocation: true
card: "Run the pipeline | 9 | Answers a help question with the skill to type and the file it came from: the role that takes the work, its playbook, and the skills its words call for. It starts no work. | Reach for it when you do not know which skill, playbook or role fits a brief, a request or a question. | op: the operator"
---

# Poteto help

jstack's own skill. It keeps the name of pstack's help skill and its rule that help starts no work, and takes none of its text (`THIRD_PARTY.md`).

Answer the user's question about jstack, give them the line to type, and name the file the answer came from. A help question starts no work: no brief, no thread, no edit. The user asked which way to go, and going is theirs to send.

jstack has no mode that one thread works under. Work goes through threads that keep their own context:

- the **home** (`skills/home/SKILL.md`) plans with the user, writes each brief and launches its crewmate;
- a **crewmate** (`skills/crew/SKILL.md`) does one brief in its own worktree and stays on its pull request;
- a **scout** (`features/scout/SKILL.md`) answers one question read-only and writes a report;
- an **expert** (`skills/expert/SKILL.md`) answers asks about its one subject from its sources and notes.

Prefer a crewmate or a scout to a subagent for work that needs depth: its thread, its brief and its Result outlive the turn, where a subagent's context ends with its answer. A message that asks for work, not for help, goes to the home: give the user `/home` to type in the repo's main checkout, and do none of the work here.

## Find out what they need

Infer the need from the message. When it is still unclear, ask one multiple-choice question, and answer only the part they pick:

- Get set up
- Start a piece of work
- Pick the role, playbook and skills for a brief, a request or a question
- Ask about one subject

## Pick

The pick comes from the tree, not from a list in this file. Run this, with what the user typed after `/poteto-help` in place of the line in angle brackets, as typed:

```sh
said=$(cat << 'THE_ASK_ENDS_HERE'
<what the user typed after the skill's name>
THE_ASK_ENDS_HERE
)
if R=$(realpath ~/.claude/skills/poteto-help/../.. 2> /dev/null) && [ -f "$R/skills/poteto-help/SKILL.md" ]; then
    repo=$(git rev-parse --path-format=absolute --git-common-dir 2> /dev/null) && H=~/.local/state/home/$(basename "$(dirname "$repo")") || H=
    path=
    for maybe in "$said" "$H/$said" "$H/tasks/$said.md" "$H/scouts/$said.md"; do
        case $maybe in
        *'
'*) ;;
        *) if [ -z "$path" ] && [ -f "$maybe" ]; then path=$maybe; fi ;;
        esac
    done
    echo "root: $R"
    if [ -n "$path" ]; then
        uv run --quiet --no-sync --project "$R" jbriefs pick "$path"
    else
        printf '%s\n' "$said" | uv run --quiet --no-sync --project "$R" jbriefs pick -
    fi
    C=$(realpath "$R/source" 2> /dev/null) || C=$R
    if [ -f "$C/install.sh" ]; then
        echo "setup: sh $C/install.sh --setup"
    else
        echo "setup: README.md, Quickstart"
    fi
else
    echo "no root: ~/.claude/skills/poteto-help is not a link into the repo this skill lives in"
fi
```

It reads a brief or a request by its path, by its path from the repo's home folder (`tasks/<slug>.md`), or by its slug, and anything else as a plain question. Its first line is the root of the repo this skill lives in: every path it prints after that is from that root. Then one line each:

- `role <skill>: <what to type> (<file>)`: who takes the work. A brief under `tasks/` is a crewmate's, `/crew <slug>`; a request under `scouts/` is a scout's, `/scout <slug>`; a question is the home's, `/home`.
- `playbook <name>: <file> (<why>)`: the steps the role works through, from the file's `Playbook:` line, else the `Run by:` row of that role that fits, else that role's default. `playbook none` is no playbook.
- `tip <skill>: ...`: up to three skills whose `tip:` phrases the words say, the rule the tips hook uses.
- `named <skill>: ...`: a skill the words name, as `/<name>` or as `skills/<name>`.
- `unknown <name>: ...`: a name the words give that is no skill or playbook here. Say so: it may be a built-in command, a skill of another tool, or a typo.
- `setup: ...`: where getting set up starts on this checkout.

On `no root`, the skill was loaded from somewhere else: the root is two directories above the real place of this file. Answer from the files there, and say that the pick was not run.

## Answer

Read each file a line names before you quote it, and trust the file where it differs from this one. Answer in this order, one line each:

1. The line to type, in a code span: `/crew <slug>`, `/scout <slug>`, `/home`, or `/expert <name>` for a question about one subject an expert holds.
2. The playbook, with its file, and in a few words what its first steps do.
3. The other skills worth typing, each with its file and the words that called for it.
4. Each `unknown` name, and what it is if you know.

For "get set up", give the `setup:` line: the command it names, or the README's Quickstart, read from `README.md` in the root. For "start a piece of work", give `/home`. For a subject an expert holds, give `/expert <name>` and its folder under `~/.local/state/home/`.

Do not offer to run any of it. The user types the line.
