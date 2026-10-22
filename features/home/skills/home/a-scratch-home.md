## A scratch home

A scratch home is a home with no repo, for throwaway questions and drafts.
It runs in T3 Code's "No project", whose workspace is `~/.t3/scratch`, and it is a jbus project of the kind `scratch` ([A scratch home](../../../../docs/jbus/a-scratch-home.md)).
None of the rest of this skill is for it: it has no plan, no brief, no crewmate, no gate and no merge.

### How it starts

The user types `/home`, or `/home <name>`, in a thread of "No project".
Get this thread's id from the `t3-code` server's `t3_thread_configuration` with no arguments (if your harness defers it, load it first), as `threadId`.
Run this in one call, with the id in place of `<threadId>`, and in place of `<name>` the name the user typed or nothing:

```sh
ME='<threadId>'
NAME='<name>'
case $NAME in *'<'* | *'>'*) NAME= ;; esac
S=$HOME/.local/state/home
if git rev-parse --git-dir > /dev/null 2>&1; then
    echo "not scratch: this thread runs in a repo, so it starts as that repo's home"
elif ! command -v jbus > /dev/null; then
    echo "not added: jbus is not installed here, so no word reaches this home"
elif ! listed=$(jbus status 2> /dev/null | jq -r '(.scratch // {}) | keys[]'); then
    echo "not known: jbus status did not answer, so nothing is written"
elif [ -z "$NAME" ] && [ "$(printf '%s\n' "$listed" | grep -c .)" != 1 ]; then
    echo "which: name the scratch home, one of: $(printf '%s ' $listed)"
else
    NAME=${NAME:-$listed}
    case $NAME in
    [A-Za-z0-9]*) bad=$(printf '%s' "$NAME" | tr -d 'A-Za-z0-9._-'; echo .) && bad=${bad%.} ;;
    *) bad=x ;;
    esac
    if [ -n "$bad" ]; then
        echo "not a name: a scratch home's name is letters, digits, dots, dashes and underscores, and starts with a letter or a digit"
    elif ! printf '%s\n' "$listed" | grep -Fqx -- "$NAME"; then
        echo "not added: jbus has no scratch home ${NAME}: add it with jbus project add ${NAME} --scratch --project-id <the No project id>"
    else
        mkdir -p "$S/$NAME"
        printf '%s\n' "$ME" > "$S/$NAME/home-id"
        echo "started: $ME is the scratch home $NAME, in $S/$NAME/home-id"
    fi
fi
```

On `started`, tell the user in one line that this thread is the scratch home and that `jbus word --to <name>` reaches it.
On `not added` with a name, find the "No project" id with `t3_project_list` (the entry whose `workspaceRoot` is `~/.t3/scratch`), run the command the line gives with it, and run the block again: `jbus project add` is the only writer of jbus's config, so never open, print or edit that file.
On `which`, ask the user which name, once.
On `not a name`, ask the user for a name of that form, once.
On any other line, tell the user the line as it is.
A later start writes its own id over the last one, so the newest scratch home thread is the one a word reaches.

### What it may do

It answers questions, drafts text and thinks a problem through with the user, in this thread.
A word that jbus carries here is the user's word, as "The user's word, carried by jbus" says: act on it inside these limits.

### What it may not do

It touches no repo: it clones none, opens no checkout, and writes no file outside `~/.t3/scratch` and its own `home-id`.
It pushes nothing and opens no pull request.
It launches no crewmate, scout or reviewer, and queues no row.
It sends nothing outside this thread: no email, no message to any person or service, and no post anywhere, even when a draft is ready.
A draft is handed to the user in this thread, and the user sends it, or does not.
A task that needs any of these goes to the home of the repo it is about, by the user's word there.
