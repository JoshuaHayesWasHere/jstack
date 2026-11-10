#!/bin/bash
# The crew's proof of the tests a branch changes: each runs at the head, then laid over a copy
# of the merge-base's code, and the `Proved:` line `jmerge` reads is printed, and appended to the
# brief once it has a Result. Both sides run in the one slot a run gets, since a side that gave its
# slot back would find every slot taken on a busy machine when it asked again. A side the short
# lane's limit cut runs again alone in a full slot. A side that exited 0 is kept in the worktree's
# `crew-proof-sides`, and a run at the same head and base runs only the side still owed. features/crew/do-the-task.md
# says what it proves and how.
# A crew runs it by its path, `bash "$T/proved.sh" <brief> <thread id>`, from its worktree: the
# command it sends then holds no `rm`, which Claude Code stops to ask about, even in full access.
B=$1
thread=$2
T=$(dirname "$0")
exempt='(^|/)(docs|\.github)/|(^|/)\.[^/]*$|\.(md|txt|rst|toml|json|yml|yaml|cfg|ini|lock)$'
fork='^features/[^/]+/packaging/'
# A branch whose every file is under a fork's `packaging/` folder, or docs or config, changes only
# the fork's patches, whose tests are inside them. Each side lays its own series over its own
# PKGBUILD's tag, the base's with the head's test files over it, installs, and runs the vitest
# files the changed patches add or change, each with its package's own `test` script.
prove_fork() {
    local dir patches files side rev at file list ran at_head at_base
    dir=$(printf '%s\n' "$changed" | command grep -E "$fork" | sed -E 's|^(features/[^/]+/packaging)/.*|\1|' | sort -u)
    if [[ $dir == *$'\n'* ]]; then
        echo "no proof: the branch changes more than one fork's packaging: $(printf '%s\n' "$dir" | paste -sd ' ' -)"
        return
    fi
    patches=$(git diff --name-only --diff-filter=d "$base" HEAD -- "$dir" | command grep -E '\.patch$')
    files=$(printf '%s\n' "$patches" | while read -r file; do
        [ -n "$file" ] && git show "HEAD:$file" | sed -n 's|^+++ b/||p'
    done | command grep -E '\.test\.[cm]?[jt]sx?$' | sort -u)
    if [ -z "$files" ]; then
        echo "no proof: the fork patches it changes add or change no vitest file, so the fork's tests prove nothing: add one in the patch"
        return
    fi
    if ! tree=$(mktemp -d "${TMPDIR:-/tmp}/fork.XXXXXX"); then
        echo "no proof: no fork tree could be made in ${TMPDIR:-/tmp}"
        return
    fi
    trap 'rm -rf "$tree"' EXIT
    for side in head base; do
        if [ "$side" = head ]; then rev=$head; else rev=$base; fi
        at=$tree/$side
        mkdir -p "$at"
        git show "$rev:$dir/PKGBUILD" > "$tree/PKGBUILD.$side"
        set -- $(env -u T3CODE_JSTACK_TAG bash -c 'source "$1" > /dev/null && printf "%s %s\n" "$_tag" "${source[0]#*::}" && printf "%s\n" "${_patches[@]}"' _ "$tree/PKGBUILD.$side")
        echo "$side: $dir at ${rev:0:12}, $1 and $(($# - 2)) patches"
        [ -f "$tree/$1.tar.gz" ] || curl -fsSL -o "$tree/$1.tar.gz" "$2" || {
            echo "no proof: $2 could not be fetched"
            return
        }
        tar -xzf "$tree/$1.tar.gz" -C "$at" --strip-components=1
        shift 2
        for file in "$@"; do
            git show "$rev:$dir/$file" | patch -d "$at" -p1 --forward --quiet || {
                echo "no proof: $file of the $side does not apply"
                return
            }
        done
    done
    printf '%s\n' "$files" | while read -r file; do
        mkdir -p "$tree/base/$(dirname "$file")"
        cp "$tree/head/$file" "$tree/base/$file"
    done
    list=$(printf '%s\n' "$files" | paste -sd ' ' -)
    PROOF_TREE=$tree PROOF_TESTS=$list uv run --project "$T/../source" jgauge test-slot --thread "$thread" -- bash -c '
        for side in head base; do
            at=$PROOF_TREE/$side
            (cd "$at" && vp i --frozen-lockfile) > "$PROOF_TREE/.install-$side" 2>&1 || {
                echo "$side install failed: $(tail -n 1 "$PROOF_TREE/.install-$side")"
                continue
            }
            worst=0
            for pkg in $(for file in $PROOF_TESTS; do
                d=$(dirname "$file")
                while [ "$d" != . ] && [ ! -f "$at/$d/package.json" ]; do d=$(dirname "$d"); done
                echo "$d"
            done | sort -u); do
                group=
                for file in $PROOF_TESTS; do
                    case $file in "$pkg"/*) group="$group ${file#"$pkg"/}" ;; esac
                done
                script=$(jq -r ".scripts.test // \"vp test run\"" "$at/$pkg/package.json")
                (cd "$at/$pkg" && bash -c "$script \"\$@\"" _ $group) >> "$PROOF_TREE/.proof-$side" 2>&1
                code=$?
                [ "$code" -gt "$worst" ] && worst=$code
            done
            echo "$side exit $worst: $(command grep -E "^ *Tests +[0-9]" "$PROOF_TREE/.proof-$side" | tr -s " " | paste -sd , -)"
        done
    ' | tee "$tree/.proof-said"
    ran=${PIPESTATUS[0]}
    at_head=$(sed -n 's/^head exit \([0-9]*\):.*/\1/p' "$tree/.proof-said")
    at_base=$(sed -n 's/^base exit \([0-9]*\):.*/\1/p' "$tree/.proof-said")
    if [ "$ran" != 0 ] || [ -z "$at_head" ] || [ -z "$at_base" ]; then
        echo "no proof: the slot's run ended $ran"
        return
    fi
    line="Proved: $list base exit $at_base at $base, head exit $at_head at $head, fork patches"
    echo "$line"
    if command grep -q '^## Result' "$B"; then printf '%s\n' "$line" >> "$B"; fi
}
on=$(awk '/^## / {exit} /^Stacked on:/ {print $(4); exit}' "$B" 2> /dev/null)
on=origin/${on:-main}
git rev-parse -q --verify "$on^{commit}" > /dev/null || on=origin/main
head=$(git rev-parse HEAD)
if [ -n "$(git status --porcelain)" ]; then
    echo "no proof: commit the work first"
elif ! base=$(git merge-base "$on" HEAD); then
    echo "no proof: the branch shares no commit with $on"
elif ! tests=$(git diff --name-only --diff-filter=d "$base" HEAD | command grep -E '(^|/)(test_[^/]*|[^/]*_test)\.py$') &&
    changed=$(git diff --name-only --no-renames "$base" HEAD) &&
    printf '%s\n' "$changed" | command grep -E "$fork" | command grep -qvE "$exempt" &&
    ! printf '%s\n' "$changed" | command grep -vE "$fork" | command grep -qvE "$exempt"; then
    prove_fork
elif [ -z "$tests" ]; then
    # A .py file whose change is to its docstrings and comments alone is docs, which only its
    # parsed code can tell, so jbriefs names the kinds (`jbriefs.proved.none_kinds`).
    if line=$(uv run --project "$T/../source" jbriefs --proved-none "$base..$head"); then
        echo "$line"
        if command grep -q '^## Result' "$B"; then printf '%s\n' "$line" >> "$B"; fi
    else
        echo "no test changed: the Result says Proved: none, <kind>, where every file it changes is of that kind${line:+ ($line)}"
    fi
else
    kept='(^|/)tests?/|(^|/)(test_[^/]*|[^/]*_test|conftest)\.py$'
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
    ran=0
    owed=
    for side in $sides; do
        if had=$(command grep -m 1 "^$side exit 0: " "$passed"); then
            echo "$side: exited 0 at this head and base already, $had"
            printf '%s\n' "$had" >> "$tree/.proof-said"
        else
            owed="$owed $side"
        fi
    done
    for lane in --short ''; do
        [ -n "$owed" ] || break
        # The short lane's worker count is the Makefile's SHORT_WORKERS; a full slot takes the
        # desk's quarter of the processors, at least two, as the Makefile's PER_CORE does.
        if [ -n "$lane" ]; then
            proof_workers=4
        else
            proof_workers=$(($(getconf _NPROCESSORS_ONLN 2> /dev/null || echo 8) / 4))
            [ "$proof_workers" -ge 2 ] || proof_workers=2
        fi
        PROOF_WORKERS=$proof_workers PROOF_HEAD=$PWD PROOF_BASE=$tree PROOF_SIDES=$owed PROOF_TESTS=$list uv run --project "$T/../source" jgauge test-slot $lane --thread "$thread" -- bash -c '
            for side in $PROOF_SIDES; do
                if [ "$side" = head ]; then at=$PROOF_HEAD more=; else at=$PROOF_BASE more=--continue-on-collection-errors; fi
                cd "$at" || exit
                workers=
                if env -u VIRTUAL_ENV uv run python -c "import xdist" > /dev/null 2>&1; then workers="-n $PROOF_WORKERS --dist worksteal"; fi
                env -u VIRTUAL_ENV uv run pytest -q -p no:cacheprovider $workers $more $PROOF_TESTS > "$PROOF_BASE/.proof-$side" 2>&1
                echo "$side exit $?: $(tail -n 1 "$PROOF_BASE/.proof-$side")"
            done
        ' | tee -a "$tree/.proof-said"
        ran=${PIPESTATUS[0]}
        left=
        for side in $owed; do
            command grep "^$side exit 0: " "$tree/.proof-said" >> "$passed"
            command grep -q "^$side exit " "$tree/.proof-said" || left="$left $side"
        done
        owed=$left
        [ "$ran" = 124 ] && [ -n "$lane" ] || break
        for side in $owed; do
            echo "$side: stopped at the short lane's limit, no verdict: it runs again alone in a full slot"
        done
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
