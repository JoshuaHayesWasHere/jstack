---
name: new-home
description: Set up a repo's first home - its state directory, its T3 Code project, its table in jbus's config, what it lacks for jbus to merge in it, and its home thread. It finishes a home that was started by hand, and does only what is missing. Use for /new-home <repo>.
disable-model-invocation: true
card: "Run the pipeline | 8 | Sets up a repo's first home in five steps: its state directory, its T3 Code project, its table in jbus's config, what it lacks for a merge, and its home thread. | Reach for it when a repo gets its first home, or one was started by hand. | op: the operator"
---

# new-home

`/new-home <repo>` sets up the first home of a repo, from any thread. `<repo>` is the repo's path, or its folder name under `~/repos`. It is typed, never loaded by itself.

A repo's first home needs five things, and a first home has no thread to type `/home` in until the second is there. This skill does the five in order, each once. For each it tells the user one line, as the step prints it or says it: `done`, `already`, or `needs you: <a command or one sentence>`. Run again on a repo where some of it is done, it does what is missing and says `already` for the rest.

This thread does not become the home. It starts no crewmate and no scout, makes no scheduled task and no webhook, and writes no file but the two of step 1: jbus's config is written by `jbus project add`, the git hooks are linked by `jinstall --repo`, and the four switches of a repo are the user's.

## 1. The repo and its state directory

Run this with everything typed after `/new-home` in place of `<the text after /new-home>`, or nothing when nothing was typed after it:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
typed=$(cat << 'THE_TEXT_ENDS_HERE'
<the text after /new-home>
THE_TEXT_ENDS_HERE
)
word=$(printf '%s\n' "$typed" | awk 'NF {print $(1); exit}')
case $word in
'~') at=$HOME ;;
'~/'*) at=$HOME/${word#??} ;;
*/*) at=$word ;;
*) at=$HOME/repos/$word ;;
esac
common=$(git -C "$at" rev-parse --path-format=absolute --git-common-dir 2> /dev/null)
C=${common%/.git}
R=${C##*/}
H=~/.local/state/home/$R
filled=yes
case $typed in
'<the text after '*) filled= ;;
esac
if [ -z "$filled" ]; then
    echo "not filled in: put what was typed after /new-home in place of the placeholder, or nothing"
elif [ -z "$word" ]; then
    echo "needs a repo: type /new-home <repo>, a repo's path or its folder name under ~/repos. Nothing is done."
elif [ -z "$common" ] || [ "$C" = "$common" ]; then
    echo "not a git repository: $at is no checkout of one. Nothing is done."
elif [ "${R#_}" != "$R" ]; then
    echo "not a repo's home: a folder named $R under ${H%/*} is a party's, as an expert's is. Nothing is done."
else
    printf 'repo: %s\ncheckout: %s\nstate: %s\n' "$R" "$C" "$H"
    if [ -f "$H/plan.md" ]; then
        echo "1 state directory: already, $H has its plan.md"
    elif mkdir -p "$H" && touch "$H/plan.md" "$H/notes.md"; then
        echo "1 state directory: done, made $H"
    else
        echo "1 state directory: needs you: mkdir -p $H"
    fi
    id=$(awk 'NF {print $(1); exit}' "$H/home-id" 2> /dev/null)
    echo "home-id: ${id:-none}"
fi
```

On `needs a repo`, `not a git repository` or `not a repo's home`, tell the user that line and stop: nothing was made. Otherwise keep the `repo:`, `checkout:` and `home-id:` lines for the steps below. The checkout is the repo's main checkout, also when the path typed is one of its worktrees.

The directory is made as the home skill's first-home step makes it, with the same line: an empty `plan.md` and `notes.md`. `plan.md` is what says a home has started, so the home this skill launches is not told it is the first. `merge-seen` and `home-id` are the home's to write.

## 2. The T3 Code project

Find the project whose checkout is the repo, with the `t3-code` server's `t3_project_list` (if your harness defers it, load it first), called with `{"limit": 100}`. It is the entry whose `workspaceRoot` is the `checkout:` line, and its `id` is the T3 project id of the steps below. A reply with a `nextCursor` has more: ask again with that as `cursor` until it is found or the list ends. When it is found, the line is `2 T3 project: already, <id>`.

When no entry has that checkout, make one with `t3_project_create`, called with `{"title": "<repo>", "workspaceRoot": "<the checkout>"}`. The line is `2 T3 project: done, <id>`, with the `id` of the reply. In a session with neither tool, the line is `2 T3 project: needs you: add <the checkout> as a project in T3 Code, then type /new-home <repo> again`, and steps 3 and 5 are not done: each needs the id.

## 3. The project's table in jbus's config

This block is the one registration there is: the home skill's start runs it too, for a repo whose home started with no project in jbus's config ("On the bus" in `skills/home/SKILL.md`). Run it with the `checkout:` line of step 1 and the id of step 2 in place of the words in angle brackets:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
C='<the checkout>'
P='<the T3 project id>'
case $C$P in
'' | *'<'* | *'>'*)
    echo "not filled in: put the checkout step 1 printed and the T3 project id of step 2 in place of the placeholders" ;;
*)
    if ! command -v jbus > /dev/null; then
        echo "3 jbus project: needs you: sh install.sh in the checkout that holds this skill, jbus is not on PATH"
    else
        said=$(jbus project add "${C##*/}" --checkout "$C" --project-id "$P" 2>&1)
        case $said in
        'added: '*) echo "3 jbus project: done, ${said#added: }" ;;
        'refused: the config already has this project') echo "3 jbus project: already, jbus's config has its table" ;;
        'refused: no config at '*) echo "3 jbus project: needs you: set jbus up once for the machine, as features/jbus/docs/jbus.md \"Set up jbus\" says, then type /new-home ${C##*/} again" ;;
        *) echo "3 jbus project: needs you: jbus project add said \"$said\"" ;;
        esac
    fi
    if ! command -v jinstall > /dev/null; then
        echo "3 git hooks: needs you: sh install.sh in the checkout that holds this skill, jinstall is not on PATH"
    elif hooked=$(jinstall --repo "$C" 2>&1); then
        echo "3 git hooks: done, $(printf '%s\n' "$hooked" | grep -c '^ok ') ok in $C/.git/hooks"
    else
        echo "3 git hooks: needs you: jinstall --repo $C said:"
        printf '%s\n' "$hooked" | grep -v '^ok '
    fi ;;
esac
```

`jinstall --repo` links jleak's `pre-push` and `commit-msg` hooks into the repo's main checkout, and keeps the repo in the list `jinstall --check` and the doctor read.
A run on a repo that has them already links nothing and says `done` all the same.
A hook of the repo's own is never written over: the `needs you` line names it, with the line that runs jstack's hook from it.

`jbus project add` is the only thing that writes the config: it keeps the file as it was beside it, leaves every other table as it is, writes no webhook, and prints no value of any key. Never open, print or edit that file here. The project's name in jbus is the repo's folder name, which is also the name of its state directory. Each pass of jbus is a new run that loads the config, so the next pass works the new project and no unit is restarted: the `done` line says so.

It never writes `home-thread`, here or at a home's start: a repo it adds is one jbus merges for, unless the user has put an id in that switch by hand.

## 4. What the repo lacks for a merge

This step reads and changes nothing. Run it with the `checkout:` line of step 1 in place of the words in angle brackets:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
C='<the checkout>'
case $C in
'' | *'<'* | *'>'*)
    echo "not filled in: put the checkout step 1 printed in place of the placeholder" ;;
*)
    H=~/.local/state/home/${C##*/}
    lacks=0
    need() {
        lacks=$((lacks + 1))
        echo "4 to merge: needs you: ${1}"
    }
    if ! git -C "$C" remote get-url origin > /dev/null 2>&1; then
        need "git -C $C remote add origin <the repo's address at GitHub>, it has no remote named origin"
    elif ! git -C "$C" ls-remote --symref origin HEAD 2> /dev/null | grep -q '^ref: refs/heads/'; then
        need "git -C $C push -u origin <the default branch>, origin names no default branch yet or could not be asked"
    fi
    checked=$(grep -lsE 'pull_request([^_]|$)' "$C"/.github/workflows/*.yml "$C"/.github/workflows/*.yaml 2> /dev/null |
        while IFS= read -r flow; do
            if awk '
                function close_job() {
                    if (id != "" && !matrix && (name == "check" || (name == "" && id == "check"))) found = 1
                    id = ""
                }
                /^jobs:[[:space:]]*$/ {jobs = 1; at = -1; next}
                jobs && /^[^[:space:]#]/ {close_job(); jobs = 0}
                jobs && NF && $(1) !~ /^#/ {
                    match($(0), /^ */)
                    if (at < 0) at = RLENGTH
                    if (RLENGTH == at) {close_job(); id = $(1); sub(/:.*/, "", id); name = ""; matrix = 0; next}
                    if (RLENGTH == at + 2 && $(1) == "name:") {
                        name = $(0); sub(/^[^:]*:[[:space:]]*/, "", name); sub(/[[:space:]]+#.*$/, "", name)
                        gsub(/["\047]/, "", name); sub(/[[:space:]]+$/, "", name)
                    }
                    if ($(1) == "matrix:") matrix = 1
                }
                END {close_job(); exit !found}' "$flow"; then echo "$flow"; fi
        done | head -n 1)
    if [ -z "$checked" ]; then
        need "a workflow in $C/.github/workflows that runs on pull_request and has a job named check: jmerge merges on that check alone"
    fi
    if [ ! -s "$H/fresh-check" ]; then
        line='<the check command, on one line>'
        if grep -qs '^check:' "$C/Makefile"; then line='make check'; fi
        need "echo '$line' > $H/fresh-check, the one line jmerge runs as the repo's local check"
    fi
    if [ "$lacks" -eq 0 ]; then
        echo "4 to merge: already, it has origin, a default branch, a workflow with a check named check, and fresh-check"
    fi
    there() { if [ -e "$H/${1}" ]; then echo there; else echo absent; fi; }
    holds=empty
    if [ -n "$(cat "$H/home-thread" 2> /dev/null | tr -d '[:space:]')" ]; then holds='an id'; fi
    echo "switches, the user's alone: off is $(there off) (/nohome repo), merge-off is $(there merge-off) (/nohome merge), home-thread holds $holds (a home's thread id on one line of $H/home-thread, written by hand)" ;;
esac
```

Each `needs you` line is something only the user does: tell it as printed and do none of it. The default branch is asked of origin itself, as `jmerge` asks it, so this step needs the network. A workflow counts when it runs on `pull_request` and one of its jobs reports a check named exactly `check`, as `jmerge` waits for: a job whose `name:` is `check`, or a job with the id `check` and no `name:`, and no `matrix:`, which adds the matrix values to the name. The workflow is read in the checkout as it is, on whatever branch is checked out there. `fresh-check`, `off`, `merge-off` and `home-thread` are the user's four switches for a repo: the lines name what to write, and this skill writes none of them.

## 5. The home's thread

A home has one thread, so look for it before launching one. List the project's threads that are not settled, with `t3_thread_list` (if your harness defers it, load it first), called with `{"projectId": "<the T3 project id>", "settled": false, "limit": 100}`. A reply with a `nextCursor` has more: ask again with that as `cursor` until the list ends. The title is no filter here: a home started by hand may have any title.

The home is there when one of these holds, and then the line is `5 home thread: already, [home: <repo>](t3-thread://v1/<its threadId>)` and nothing is launched:

- the `home-id:` line of step 1 is an id, and a thread of the list has that id;
- a thread of the list is titled exactly `home: <repo>`: a home launched a moment ago that has not written its `home-id` yet, or one whose `home-id` was lost.

Otherwise launch the home in the project's root checkout, with `t3_thread_launch`, called with `{"projectId": "<the T3 project id>", "title": "home: <repo>", "workspaceStrategy": {"type": "root"}, "message": "/home"}`.

Before this launch, run `uv run --project <the checkout that holds this skill> jroles home`. When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is `{"projectId": "<the T3 project id>", "title": "home: <repo>", "workspaceStrategy": {"type": "root"}, "message": "/home", "modelSelection": <model selection>}`, which starts the home on the model the role map names. When it prints nothing, or a line on stderr that says why the map gives no model, the call is the one above.

The line is `5 home thread: done, [home: <repo>](t3-thread://v1/<its threadId>)`. The new thread writes its own id to `home-id` at its start: write nothing there. A launch has no retry key. If the call fails or its reply is lost, ask `t3_thread_list` again before launching again, so there are never two. In a session with no `t3_thread_launch`, the line is `5 home thread: needs you: open a new thread in the project <repo> and type /home`.

## The end

Give the user the lines, in order: step 1's, step 2's, step 3's two, each of step 4's and step 5's, then the `switches` line. Add nothing a line does not say. This thread is done: the home is the thread step 5 names.
