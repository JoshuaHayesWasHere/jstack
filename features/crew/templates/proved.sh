#!/bin/bash
# The crew's proof of the tests a branch changes: each runs at the head, then laid over a copy
# of the merge-base's code, and the `Proved:` line `jmerge` reads is printed, and appended to the
# brief once it has a Result. A side that exited 0 is kept in the worktree's `crew-proof-sides`,
# and a run at the same head and base runs only the side still owed. features/crew/do-the-task.md
# says what it proves and how.
# A crew runs it by its path, `bash "$T/proved.sh" <brief> <thread id>`, from its worktree: the
# command it sends then holds no `rm`, which Claude Code stops to ask about, even in full access.
B=$1
thread=$2
T=$(dirname "$0")
on=$(awk '/^## / {exit} /^Stacked on:/ {print $(4); exit}' "$B" 2> /dev/null)
on=origin/${on:-main}
git rev-parse -q --verify "$on^{commit}" > /dev/null || on=origin/main
head=$(git rev-parse HEAD)
if [ -n "$(git status --porcelain)" ]; then
    echo "no proof: commit the work first"
elif ! base=$(git merge-base "$on" HEAD); then
    echo "no proof: the branch shares no commit with $on"
elif ! tests=$(git diff --name-only --diff-filter=d "$base" HEAD | command grep -E '(^|/)(test_[^/]*|[^/]*_test)\.py$'); then
    echo "no test changed: the Result says Proved: none, <kind>, where every file it changes is of that kind"
else
    kept='(^|/)tests?/|(^|/)(test_[^/]*|[^/]*_test|conftest)\.py$'
    exempt='(^|/)(docs|\.github)/|(^|/)\.[^/]*$|\.(md|txt|rst|toml|json|yml|yaml|cfg|ini|lock)$'
    if ! tree=$(mktemp -d "${TMPDIR:-/tmp}/base.XXXXXX"); then
        echo "no proof: no copy of the base could be made in ${TMPDIR:-/tmp}"
        exit 1
    fi
    trap 'rm -rf "$tree"' EXIT
    if git diff --name-only --no-renames "$base" HEAD | command grep -vE "$kept" | command grep -qvE "$exempt"; then
        only=
        sides='head base'
        git clone -q --shared --no-checkout . "$tree"
        git -C "$tree" checkout -q --detach "$base"
        git diff --name-only --diff-filter=d "$base" HEAD | command grep -E "$kept" |
            while read -r file; do
                mkdir -p "$tree/$(dirname "$file")"
                git show "HEAD:$file" > "$tree/$file"
            done
        (cd "$tree" && env -u VIRTUAL_ENV uv sync -q)
    else
        only=1
        sides=head
        echo "tests only: every file the branch changes is a test, docs or config, so its tests run at the head alone"
    fi
    list=$(printf '%s\n' "$tests" | paste -sd ' ' -)
    : > "$tree/.proof-said"
    passed=$(git rev-parse --git-path crew-proof-sides)
    [ "$(sed -n 1p "$passed" 2> /dev/null)" = "$head $base" ] || printf '%s %s\n' "$head" "$base" > "$passed"
    for side in $sides; do
        if had=$(command grep -m 1 "^$side exit 0: " "$passed"); then
            echo "$side: exited 0 at this head and base already, $had"
            printf '%s\n' "$had" >> "$tree/.proof-said"
            ran=0
            continue
        fi
        if [ "$side" = head ]; then at=$PWD more=; else at=$tree more=--continue-on-collection-errors; fi
        for lane in --short ''; do
            PROOF_AT=$at PROOF_MORE=$more PROOF_SIDE=$side PROOF_OUT=$tree/.proof-$side PROOF_TESTS=$list uv run --project "$T/../source" jgauge test-slot $lane --thread "$thread" -- bash -c '
                cd "$PROOF_AT" || exit
                workers=
                if env -u VIRTUAL_ENV uv run python -c "import xdist" > /dev/null 2>&1; then workers="-n auto --dist worksteal"; fi
                env -u VIRTUAL_ENV uv run pytest -q -p no:cacheprovider $workers $PROOF_MORE $PROOF_TESTS > "$PROOF_OUT" 2>&1
                echo "$PROOF_SIDE exit $?: $(tail -n 1 "$PROOF_OUT")"
            ' | tee -a "$tree/.proof-said"
            ran=${PIPESTATUS[0]}
            [ "$ran" = 124 ] && [ -n "$lane" ] || break
            echo "$side: stopped at the short lane's limit, no verdict: it runs again alone in a full slot"
        done
        [ "$ran" = 0 ] || break
        command grep "^$side exit 0: " "$tree/.proof-said" >> "$passed"
    done
    at_head=$(sed -n 's/^head exit \([0-9]*\):.*/\1/p' "$tree/.proof-said" | tail -n 1)
    at_base=$(sed -n 's/^base exit \([0-9]*\):.*/\1/p' "$tree/.proof-said" | tail -n 1)
    line=
    if [ "$ran" != 0 ] || [ -z "$at_head" ] || { [ -z "$only" ] && [ -z "$at_base" ]; }; then
        echo "no proof: the slot's run ended $ran"
    elif [ -n "$only" ]; then
        line="Proved: $list head exit $at_head at $head, tests only"
    else
        line="Proved: $list base exit $at_base at $base, head exit $at_head at $head"
    fi
    if [ -n "$line" ]; then
        echo "$line"
        if command grep -q '^## Result' "$B"; then printf '%s\n' "$line" >> "$B"; fi
    fi
fi
