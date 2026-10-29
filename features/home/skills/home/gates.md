## Gates

A gate is a question only the user can answer, asked with the default that was taken so the work did not wait for it. jbus keeps each one as a numbered question: `jbus gate` writes it, and `jbus answer` closes it, once. This home keeps no file of them and no copy: it reads the open ones from jbus, and runs the one command that closes one.

**Every gate acts unless stopped.**
The asking thread, this home included, acts on its default at once and carries on.
No question parks work while it waits, and the user sees each one as already acted on.
Every gate carries a default, and the default is the option the thread recommends, marked `(default, recommended)`.
`jbus gate` refuses a gate with no filled `Default:` line, and one whose recommended option is not the default.
The first jbus pass that sees the question closes it with its default at once, by silence.
The record says it was not the user's word (`by jbus`, the time, `settled at once`).
A later answer from the user still replaces that close, and one that differs goes back to the thread as any other.

The one exception is a default that is **irreversible or slow to revert**: undoing it needs the user, or takes more than one ordinary pull request or command, or cannot restore what was there, or has already reached someone outside this machine. Such a gate does not act. Its thread does the fail-safe and adds two lines under `Undo:`: `Holds: <the case>`, word for word from the table, and `Fail-safe: <what was prepared, with its path or link>`. The action then waits for the user's answer, and silence never closes it. `jbus gate` refuses a `Holds:` line with no filled `Fail-safe:` line, a case that is not in the table, and a `Fail-safe:` line with no `Holds:` line.

| Case | Examples | Fail-safe |
|---|---|---|
| deletes data | removing files, folders, branches, a repo, a T3 project or thread, a database, a bucket, a cloud resource | dry-run: list exactly what goes; a backup or bundle first where one can be made; then hold for the user |
| rewrites history | force-push to a shared branch, filter-repo, deleting tags | safety bundle of the old history, verify script, then hold for the user |
| spends money | creating paid cloud resources, raising a plan or a limit, a purchase | the cost estimate or plan, then hold for the user |
| touches prod or real users | a prod deploy, a prod data or schema change, a message to a customer or anyone outside | the plan or diff (`terraform plan`, `cdk diff`, the message text), then hold for the user |
| changes access or secrets | rotating or granting a key or token, tailnet policy or DNS | the diff of the change, then hold for the user (jmerge's protected paths already hold the code side) |
| publishes | a public release, a tag, a package, a public repo or post | the exact artifact and where it goes, then hold for the user |

Everything else acts at once on its default: a merge (reverted by `gh pr revert`), a branch, a brief, a config edit with its backup, a launch. `$T/gates.md` has the same rule under the gate's lines, for every thread that gates.

**The block that reads jbus** is run in the same call as every block of this section but the last two, after the block at the top and the block that finds this home, from the main checkout:

```sh
: "${M:?run the block that finds this home first}"
SEP=$(printf '\037')
own=home
if [ "$M" != "$H" ]; then own=home-$(basename "$M"); fi
mine() {
    if [ "${1}" = "$own" ]; then return 0; fi
    case ${1} in
    home) return 1 ;;
    home-*) if [ -f "$H/${1#home-}/plan.md" ]; then return 1; fi ;;
    esac
    for f in "$H/tasks/${1}.md" "$H/scouts/${1}.md"; do
        if [ -f "$f" ]; then
            [ "$(whose "$f")" = "$M" ]
            return
        fi
    done
    [ "$M" = "$H" ]
}
P=$(awk -v repo="$R" '
    function said(line) { sub(/^[^=]*=[ \t]*"/, "", line); sub(/"[ \t]*(#.*)?$/, "", line); return line }
    function table() { if (inside && !found && name != "" && (state == "" ? name : state) == repo) { print name; found = 1 } name = state = "" }
    /^[ \t]*\[/ { table(); inside = ($(0) ~ /^[ \t]*\[\[project\]\][ \t]*$/); next }
    inside && /^[ \t]*name[ \t]*=/ { name = said($(0)) }
    inside && /^[ \t]*state[ \t]*=/ { state = said($(0)) }
    END { table() }' "${JBUS_CONFIG_DIR:-$HOME/.config/jbus}/config.toml" 2> /dev/null)
OPEN=
Q="${JBUS_STATE_DIR:-$HOME/.local/state/jbus}/$P/questions.json"
if ! command -v jbus > /dev/null; then
    WHY="no jbus: jbus is not installed here, so it holds no question"
elif [ -z "$P" ]; then
    WHY="no project: jbus's config names no project for $R, so it holds no question of this repo"
elif [ ! -e "$Q" ]; then
    WHY=
elif ! found=$(jq -r '.records[] | select(.answer == null) | [.number, .slug, .question, .default, .built_on, .undo, (.holds // ""), (.fail_safe // "")] | map(tostring) | join("\u001f")' "$Q" 2> /dev/null); then
    WHY="jbus could not be read: $Q is not the record jbus writes"
else
    WHY=
    OPEN=$(printf '%s\n' "$found" | while IFS=$SEP read -r n slug rest; do
        if [ -n "$n" ] && mine "$slug"; then printf '%s\n' "$n$SEP$slug$SEP$rest"; fi
    done)
fi
```

It prints nothing. `$P` is this repo's project in jbus's config, and `$OPEN` the open questions that are this home's, read from the record jbus keeps of them, `questions.json` in the project's state directory: it is as it is now, with no pass between. This block only reads it: `jbus gate` and `jbus answer` are the two that write it. A question is this home's by the brief or the request of the slug that asked, as step 4 of "When a home starts" tells, or by this home's own slug, whatever brief has that name: `home` for the root home, `home-<scope>` for a scoped one. One that no brief, no request and no home asked, as an expert's finding is, is the root home's. `$WHY` says why nothing could be read.

**Ask one** when the question is this home's own. Take the default you would recommend and act on it at once, or, for a default the table above holds, do its fail-safe and act on it only once the user answers. Fill in the lines of `$T/gates.md` (read it first), its `<n>` left as it is, with the `Holds:` and `Fail-safe:` lines under `Undo:` for a gate that holds, and carry on. Under the gate go one `Context:` line and one `Option:` line for every option you weighed, the default you took among them, which is the one you recommend, marked `(default, recommended)`, and the rest with no mark. With the entry in place of the line in angle brackets, and `own` left as it is:

```sh
: "${SEP:?run the block that reads jbus first}"
slug='own'
the_gate() {
    cat << 'THE_GATE_ENDS_HERE'
<the gate, filled in>
Context: <what the user needs to know to answer it, in one line, with the links to it>
Option: <an option's short name> (default, recommended): <what follows from it>
THE_GATE_ENDS_HERE
}
gate=$(the_gate)
if [ "$slug" = own ]; then
    slug=$own
    gate=$(printf '%s\n' "$gate" | sed "s/^Asked by: [^,]*/Asked by: $own/")
fi
if ! command -v jbus > /dev/null; then
    echo "not asked: jbus is not installed here"
elif said=$(printf '%s\n' "$gate" | jbus gate "$slug" 2>&1); then
    echo "asked: $said"
else
    echo "not asked: jbus said: $said"
fi
```

On `asked: queued: question <number>`, jbus has it under this home's own slug, and nothing is written here.
`asked: already sent:` is the same question still open.
On `asked: already answered: question <number>:` nothing was asked: an earlier question of this home had the same words, and the line gives its answer.
If that answer does not settle this one, word the question so that it says what is new, and run it again.
On `not asked: jbus said: not sent:` or `jbus said: refused:`, jbus names what the gate lacks, checked against `$T/gates.md`: a first line that is not `## Gate <n>: ` and the question, more than one gate, no `Status: open` line, a line of the template left unfilled, a default that is not the recommended option, a `Holds:` line with no fail-safe or a case not in the table.
Mend that line and run it again.
On any other `not asked`, jbus holds nothing: end the turn with `decision local <slug>: ` and then the question and the default taken ("How a turn ends").

The same block hands jbus a gate another thread wrote out in full, the lines of a gate in a Result or under "Findings" in a Report: run it with that thread's slug in place of `own` and those lines as the entry.
On `asked:`, jbus holds it, or held it already, and it asks nothing more here.
On `not asked`, it is one jbus could not take: the end of this section says what to do with it.

**Show the open ones** when the user asks for status, and at no other time: a question jbus holds is told once, at the end of the turn that asked it or that jbus's wake brought it in ("How a turn ends"), and is on jbus's list of what waits on the user from then on:

```sh
: "${SEP:?run the block that reads jbus first}"
if [ -n "$WHY" ]; then
    echo "$WHY"
elif [ -z "$OPEN" ]; then
    echo "no open questions"
else
    printf '%s\n' "$OPEN" | while IFS=$SEP read -r n slug asked took built undo holds safe; do
        if [ -n "$n" ]; then
            printf 'question %s, from %s: %s\ndefault: %s\nbuilt on it: %s\nundo: %s\n' "$n" "$slug" "$asked" "$took" "$built" "$undo"
            if [ -n "$holds" ]; then
                printf 'holds (%s) for the answer, fail-safe: %s\n' "$holds" "$safe"
            else
                printf 'acted on already: the default stands unless the user stops it\n'
            fi
        fi
    done
fi
```

On `no open questions`, say nothing about gates. On `no jbus`, `no project` and `jbus could not be`, say that line: no question could be read. One open question is text: give it to the user by its number: the question and the default taken, then what was built on it and how to undo it. For one whose last line is `holds (<case>) for the answer`, say instead that its default waits for their answer, with the case and the fail-safe. Ask for nothing more than the answer.

Two or more open questions are one round of the grill page, wherever the grilling skill's "On a page" (`$T/../skills/grilling/SKILL.md`, read it now) puts a round on a page. Each set of open questions has a page of its own: do its step 1 with `gates-<n>` as the `<slug>`, `<n>` being the highest number among them, and for a scoped home `gates-<scope>-<n>`. Then run this in place of its step 2:

```sh
: "${SEP:?run the block that reads jbus first}"
open=$(printf '%s\n' "$OPEN" | grep -c .)
last=$(printf '%s\n' "$OPEN" | cut -d "$SEP" -f 1 | sort -n | tail -n 1)
slug=gates-$last
if [ "$M" != "$H" ]; then slug=gates-$(basename "$M")-$last; fi
F="$H/reports/grill-$slug.html"
if [ -n "$WHY" ]; then
    echo "no page: $WHY"
elif [ "$open" -lt 2 ]; then
    echo "no page: $open open, and fewer than two are text"
elif [ ! -f "$F" ]; then
    echo "no page: $F is not there, make it first with $slug as the slug"
else
    ROUND=$(printf '%s\n' "$OPEN" | jq -R --arg slug "$slug" '
        split("\u001f") | {
            id: "gate-\(.[0])", title: .[2],
            body: (if (.[6] // "") != "" then "Asked by \(.[1]). It holds (\(.[6])) for your answer, with its fail-safe: \(.[7])" else "Asked by \(.[1]). Its default is acted on already" end),
            built_on: .[4], undo: .[5],
            options: [
                {id: "default", label: "Yes: \(.[3])", recommended: true},
                {id: "other", label: "Something else: say what in the note"}
            ]
        }' | jq -s --arg slug "$slug" '{
            slug: $slug, round: 1, title: "Open questions",
            lead: "Each default was taken so the work did not wait, but for one that holds. A question left alone settles on its default at once, but for one that holds.",
            settled: [], questions: .
        }')
    export ROUND
    if awk '
        /<script type="application\/json" id="round-data">/ { print; print ENVIRON["ROUND"]; inside = 1; seen = 1; next }
        inside && /<\/script>/ { inside = 0 }
        !inside { print }
        END { exit !seen }' "$F" > "$F.new" && mv "$F.new" "$F"; then
        echo "round written: $open questions, in $F"
    else
        uv run --project "$T/../source" jbus forget "$F.new" > /dev/null
        echo "no page: $F has no round-data block to write the round into"
    fi
fi
```

On `round written:`, each open question is a question `gate-<n>` on the page, its default the recommended option, with what was built on it and how to undo it. Go on with steps 3 to 5 of "On a page": open the session, hold the one poll, end your turn. If a poll for this page is already out, hold no second one. On `no page:`, or where "On a page" keeps a round as text, give each question as text, as for one.

When the poll returns answers, put what it printed, all of it, in place of `<what the poll printed>`:

```sh
awk '
    function plain(s,    out, i, c) {
        out = ""
        for (i = 1; i <= length(s); i++) {
            c = substr(s, i, 1)
            if (c == "\\") { i++; c = substr(s, i, 1); if (c == "n") c = "\n" }
            out = out c
        }
        return out
    }
    function answer(line,    word, n, same, mark, at, note) {
        if (line !~ /^- gate-[0-9]+: (default|other) /) return
        split(line, word, " ")
        n = word[2]; gsub(/[^0-9]/, "", n)
        same = (word[3] == "default")
        mark = same ? "), left as recommended" : "), changed from the recommended"
        at = index(line, mark)
        note = at ? substr(line, at + length(mark)) : ""
        sub(/^\. Note: /, "", note)
        if (same && note == "") print "question " n ": default: the default, picked on the page"
        else if (same) print "question " n ": noted: " note
        else if (note != "") print "question " n ": differs: " note
        else print "question " n ": open: something else was picked, with no note"
        seen++
    }
    /^- gate-/ { answer($(0)); next }
    /\\n- gate-/ { count = split(plain($(0)), line, "\n"); for (i = 1; i <= count; i++) answer(line[i]) }
    END { if (!seen) print "no answers: no line says \"- gate-<n>: \"" }' << 'THE_POLL_ENDS_HERE'
<what the poll printed>
THE_POLL_ENDS_HERE
```

Run "Close one" for each `default`, `noted` and `differs` line, with the words after that word as the answer. A `noted` line is the default left checked, with a note: read the note, and it is `differs` if it disagrees with the default and `default` if not. An `open` line closes nothing: ask for that question's answer here. Then end the session, as step 7 of "On a page" does. If the poll says the user ended the session instead, these questions stay open and are text from then on.

**Close one** when the user answers it, here or on a page. Put the question's number, the user's name, the time they answered, `default` or `differs`, and their words, as they said them, in place of the five placeholders:

```sh
n='<number>'
by="<the user's name>"
at='<YYYY-MM-DD HH:MM ZONE>'
which='<default or differs>'
the_answer() {
    paste -sd ' ' - << 'THE_ANSWER_ENDS_HERE'
<the user's answer, in their words>
THE_ANSWER_ENDS_HERE
}
ANSWER=$(the_answer)
case $which in
default | differs)
    if ! command -v jbus > /dev/null; then
        echo "not answered: jbus is not installed here"
    elif said=$(jbus answer "$n" --by "$by" --at "$at" "--$which" -- "$ANSWER" 2>&1); then
        printf '%s\n' "$said"
    else
        printf 'not answered: jbus said: %s\n' "$said"
    fi ;;
*) echo "not answered: say whether the answer is the default the thread took, default, or not, differs" ;;
esac
```

`default` is an answer that keeps the default the thread took, and `differs` one that does not: only the one who heard the answer knows which, so words such as "yes" are read against the question's default before the block is run. On `answered: question <number>`, the question is closed, and this home sends nothing and undoes nothing: jbus carries an answer that differs to the thread that asked, with the question's undo line, on its next pass. For a question this home asked under its own slug there is no thread to tell: change the plan entry it touches, or write the new brief. Where jbus says the slug `has no Thread: line`, or the thread is finished or its pull request merged, the answer is work for a new brief.

On `not answered: jbus said: refused:` the question is as it was. `only <name> answers` gives the name `--by` takes, and `--at is "<YYYY-MM-DD HH:MM ZONE>"` the form of the time: set that line and run it again. `was answered already` prints the first answer, which stands: the user answered it elsewhere, and a second answer is theirs to give as a new word, not as this question's.

A gate that came as a `<slug>: gate` message is one jbus could not take, so jbus holds no question for it and no command closes it: this thread is its record. Give it to the user in two lines, and send an answer that differs to the thread on its `Asked by:` line yourself (`t3_thread_send`, the answer and the gate's `Undo:` line). It is the one answer a home carries. Until it is answered, the handoff's note carries it under its labels, whole: nothing else outlasts this thread.
