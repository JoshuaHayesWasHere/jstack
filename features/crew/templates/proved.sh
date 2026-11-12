#!/bin/bash
# The crew's proof of the tests a branch changes: each runs at the head, then laid over a copy
# of the merge-base's code, and the `Proved:` line `jmerge` reads is printed, and appended to the
# brief once it has a Result. Both sides run in the one slot a run gets, since a side that gave its
# slot back would find every slot taken on a busy machine when it asked again. A side the short
# lane's limit cut runs again alone in a full slot. A side that exited 0 is kept in the worktree's
# `crew-proof-sides`, and a run at the same head and base runs only the side still owed. A test is
# a `test_*.py` or `*_test.py`, run on pytest, which leaves out the tests marked `browser`, as
# `make check` and CI do, or a `*.test.*` or `*.spec.*` of JavaScript or TypeScript, run from the
# directory of the nearest package.json above it on that package's own Vitest, or Playwright for a
# `*.spec.*` where that package has a `playwright.config.*`.
# features/crew/do-the-task.md says what it proves and how.
# A crew runs it by its path, `bash "$T/proved.sh" <brief> <thread id>`, from its worktree: the
# command it sends then holds no `rm`, which Claude Code stops to ask about, even in full access.

# One side's run of each runner's tests, in the slot: `bash proved.sh --sides`, with the copies,
# the sides and the tests of each runner in PROOF_* variables. It prints `<side> exit <n>: <what
# each runner said>`, the worst exit of its runners. Vitest and Playwright end 1 on a failed test
# and on a run that never reached one alike (no file found, a web server that would not start),
# and a base exit 1 is what proves the change: each one's JSON report says whether a test failed or
# a test file did not load, and a run that ends 1 with neither is written 2.
prove_sides() {
    local side at more workers code worst said ran runner groups n pkg files name out bin dir report failed
    for side in $PROOF_SIDES; do
        if [ "$side" = head ]; then at=$PROOF_HEAD more=; else at=$PROOF_BASE more=--continue-on-collection-errors; fi
        cd "$at" || exit
        worst=0
        said=
        if [ -n "$PROOF_PYTEST" ]; then
            workers=
            if env -u VIRTUAL_ENV uv run python -c "import xdist" > /dev/null 2>&1; then workers="-n $PROOF_WORKERS --dist worksteal"; fi
            env -u VIRTUAL_ENV uv run pytest -q -p no:cacheprovider -m "not browser" $workers $more $PROOF_PYTEST > "$PROOF_BASE/.proof-$side" 2>&1
            worst=$?
            said=$(tail -n 1 "$PROOF_BASE/.proof-$side")
        fi
        for runner in vitest playwright; do
            if [ "$runner" = vitest ]; then groups=$PROOF_VITEST; else groups=$PROOF_PLAYWRIGHT; fi
            n=0
            while IFS=$'\t' read -r -u 3 pkg files; do
                [ -n "$pkg" ] || continue
                n=$((n + 1))
                name=$runner
                [ "$pkg" = . ] || name="$runner $pkg"
                out=$PROOF_BASE/.proof-$side-$runner-$n
                : > "$out.json"
                if [ ! -f "$at/$pkg/package.json" ]; then
                    # A repo's or a package's first pull request: its base has no project for the
                    # tests to run on.
                    if [ "$side" = base ]; then code=1; else code=2; fi
                    ran="$name: no package.json at the $side, so its tests have nothing of the project to run on"
                else
                    # The package's own runner, or the one a workspace's install put further up.
                    bin=./node_modules/.bin/$runner
                    dir=$pkg
                    while :; do
                        if [ -x "$at/$dir/node_modules/.bin/$runner" ]; then
                            bin=$at/$dir/node_modules/.bin/$runner
                            break
                        fi
                        [ "$dir" != . ] || break
                        dir=$(dirname "$dir")
                    done
                    if [ "$runner" = vitest ]; then
                        (cd "$at/$pkg" && CI=1 "$bin" run --reporter=default --reporter=json --outputFile.json="$out.json" $files) > "$out" 2>&1 < /dev/null
                        code=$?
                        report=$(jq -r --arg name "$name" '(.testResults | map(select(.status == "failed"))) as $f
                            | ($f | map(select((.assertionResults // []) | length == 0)) | length) as $unloaded
                            | [($f | length), "\($name): \(.numPassedTests) passed, \(.numFailedTests) failed"
                                + (if $unloaded > 0 then ", \($unloaded) files did not load" else "" end)] | @tsv' "$out.json" 2> /dev/null)
                    else
                        (cd "$at/$pkg" && CI=1 PLAYWRIGHT_JSON_OUTPUT_NAME=$out.json "$bin" test --reporter=list,json $files) > "$out" 2>&1 < /dev/null
                        code=$?
                        report=$(jq -r --arg name "$name" '(.errors | map(select(.location != null)) | length) as $unloaded
                            | ([.errors[] | select(.location == null) | .message | split("\n")[0]] | first // "") as $error
                            | [.stats.unexpected + $unloaded, "\($name): \(.stats.expected) passed, \(.stats.unexpected) failed"
                                + (if $unloaded > 0 then ", \($unloaded) files did not load" else "" end)
                                + (if $error != "" then ", \($error)" else "" end)] | @tsv' "$out.json" 2> /dev/null)
                    fi
                    if [ -z "$report" ]; then
                        ran="$name: $(tail -n 1 "$out")"
                        failed=0
                    else
                        failed=${report%%$'\t'*}
                        ran=${report#*$'\t'}
                    fi
                    if [ "$code" != 0 ] && [ "$failed" -gt 0 ]; then
                        code=1
                    elif [ "$code" = 1 ]; then
                        code=2
                    fi
                fi
                [ "$code" -gt "$worst" ] && worst=$code
                said="${said:+$said, }$ran"
            done 3<<< "$groups"
        done
        echo "$side exit $worst: $said"
    done
}
if [ "$1" = --sides ]; then
    prove_sides
    exit
fi
B=$1
thread=$2
T=$(dirname "$0")
exempt='(^|/)(docs|\.github)/|(^|/)\.[^/]*$|\.(md|txt|rst|toml|json|yml|yaml|cfg|ini|lock)$'
fork='^features/[^/]+/packaging/'
py_test='(^|/)(test_[^/]*|[^/]*_test)\.py$'
js_test='(^|/)[^/]*\.(test|spec)\.[cm]?[jt]sx?$'
# The tests and what they lean on, laid over the base with them, as jbriefs.proved.TEST_FILE has
# it: a file under a `tests/`, `test/`, `__tests__/` or `__snapshots__/` directory, each test and
# each `conftest.py`.
kept='(^|/)(tests?|__tests__|__snapshots__)/|(^|/)(test_[^/]*|[^/]*_test|conftest)\.py$|'$js_test
# Each copy installs what its tests run on: a venv where pytest runs them, and where Vitest or
# Playwright does, the node_modules each test's package gets from its lockfile, or from the
# lockfile of the workspace above it. A package with no package.json in the copy installs none.
lockfile='pnpm-lock.yaml yarn.lock bun.lock bun.lockb package-lock.json'
locked() {
    local file
    for file in $lockfile; do [ -f "$1/$file" ] && return 0; done
    return 1
}
install() {
    local at=$1 side=$2 pkg dir installed=
    if [ -n "$pytests" ]; then (cd "$at" && env -u VIRTUAL_ENV uv sync -q); fi
    : > "$tree/.install-$side"
    for pkg in $packages; do
        [ -f "$at/$pkg/package.json" ] || continue
        dir=$pkg
        while [ "$dir" != . ] && ! locked "$at/$dir"; do dir=$(dirname "$dir"); done
        locked "$at/$dir" || dir=$pkg
        case " $installed " in *" $dir "*) continue ;; esac
        installed="$installed $dir"
        if (
            cd "$at/$dir" || exit
            if [ -f pnpm-lock.yaml ]; then
                pnpm install --frozen-lockfile
            elif [ -f yarn.lock ]; then
                yarn install --frozen-lockfile
            elif [ -f bun.lock ] || [ -f bun.lockb ]; then
                bun install --frozen-lockfile
            elif [ -f package-lock.json ]; then
                npm ci --no-audit --no-fund
            else
                npm install --no-audit --no-fund
            fi
        ) >> "$tree/.install-$side" 2>&1; then
            continue
        fi
        if [ "$dir" = . ]; then dir=; else dir=" in $dir"; fi
        echo "no proof: the $side's install$dir failed: $(tail -n 1 "$tree/.install-$side")"
        exit 1
    done
}
# A test's package: the directory of the nearest package.json above it at the head, `.` for the
# root's, or for none.
package_of() {
    local dir
    dir=$(dirname "$1")
    while [ "$dir" != . ] && ! git cat-file -e "$head:$dir/package.json" 2> /dev/null; do dir=$(dirname "$dir"); done
    echo "$dir"
}
# Lines of `<package>\t<file>`, sorted, as one line a package, `<package>\t<its files from it>`.
by_package() {
    local pkg file at= files=
    while IFS=$'\t' read -r pkg file; do
        [ -n "$pkg" ] || continue
        if [ "$pkg" != "$at" ] && [ -n "$files" ]; then
            printf '%s\t%s\n' "$at" "$files"
            files=
        fi
        at=$pkg
        files="${files:+$files }$file"
    done
    [ -z "$files" ] || printf '%s\t%s\n' "$at" "$files"
}
# A Proved: line of a head the branch has left, or with work not committed, is no proof of the
# branch as it is: a commit or an edit made while the call sat in the background ends the run
# with no line, and exit 1. Each side ran on a copy of its commit, so a side kept in
# crew-proof-sides still holds.
still_at_head() {
    local now dirty
    now=$(git rev-parse HEAD)
    if [ "$now" != "$head" ]; then
        echo "no proof: the head or the worktree moved while it ran: HEAD $head is now $now"
        exit 1
    fi
    dirty=$(git status --porcelain | sed 's/^ *//' | paste -sd , - | sed 's/,/, /g')
    if [ -n "$dirty" ]; then
        echo "no proof: the head or the worktree moved while it ran: the worktree has changes: $dirty"
        exit 1
    fi
}
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
    still_at_head
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
on=$(uv run --project "$T/../source" jbriefs line base "$B" 2> /dev/null)
[ "$on" != none ] || on=
on=origin/${on:-main}
git rev-parse -q --verify "$on^{commit}" > /dev/null || on=origin/main
head=$(git rev-parse HEAD)
if [ -n "$(git status --porcelain)" ]; then
    echo "no proof: commit the work first"
elif ! base=$(git merge-base "$on" HEAD); then
    echo "no proof: the branch shares no commit with $on"
elif ! tests=$(git diff --name-only --diff-filter=d "$base" HEAD | command grep -E "$py_test|$js_test") &&
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
    pytests=$(printf '%s\n' "$tests" | command grep -E "$py_test" | paste -sd ' ' -)
    # Each Node test runs from its package's directory, on that package's own install and config,
    # and a `*.spec.*` runs on Playwright where its package has a `playwright.config.*`.
    vitests=
    specs=
    while read -r file; do
        [ -n "$file" ] || continue
        pkg=$(package_of "$file")
        if [ "$pkg" = . ]; then rel=$file path=; else rel=${file#"$pkg"/} path=$pkg; fi
        if [[ $file =~ \.spec\.[^/]*$ ]] && git ls-tree --name-only "$head:$path" | command grep -qE '^playwright\.config\.[cm]?[jt]s$'; then
            specs="$specs$pkg"$'\t'"$rel"$'\n'
        else
            vitests="$vitests$pkg"$'\t'"$rel"$'\n'
        fi
    done <<< "$(printf '%s\n' "$tests" | command grep -E "$js_test")"
    vitests=$(printf '%s' "$vitests" | sort | by_package)
    specs=$(printf '%s' "$specs" | sort | by_package)
    packages=$(printf '%s\n%s\n' "$vitests" "$specs" | while IFS=$'\t' read -r pkg _; do
        [ -z "$pkg" ] || echo "$pkg"
    done | sort -u | paste -sd ' ' -)
    if ! tree=$(mktemp -d "${TMPDIR:-/tmp}/base.XXXXXX"); then
        echo "no proof: no copy of the base could be made in ${TMPDIR:-/tmp}"
        exit 1
    fi
    tip=
    trap 'rm -rf "$tree" ${tip:+"$tip"}' EXIT
    if git diff --name-only --no-renames "$base" HEAD | command grep -vE "$kept" | command grep -qvE "$exempt"; then
        only=
        sides='head base'
        git clone -q --shared --no-checkout . "$tree"
        git -C "$tree" checkout -q --detach "$base"
        git diff --name-only --diff-filter=d "$base" HEAD | command grep -E "$kept" |
            while read -r file; do
                mkdir -p "$tree/$(dirname "$file")"
                git show "$head:$file" > "$tree/$file"
            done
        install "$tree" base
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
    # The head side runs in a checkout of the head it began at, as the base runs in its copy: a
    # crew whose proof call sits in the background may edit, commit or drop an edit in the
    # worktree meanwhile, and a run there would be of files that are not the head's.
    case " $owed " in *" head "*)
        if ! tip=$(mktemp -d "${TMPDIR:-/tmp}/head.XXXXXX"); then
            echo "no proof: no copy of the head could be made in ${TMPDIR:-/tmp}"
            exit 1
        fi
        git clone -q --shared --no-checkout . "$tip"
        git -C "$tip" checkout -q --detach "$head"
        install "$tip" head
        ;;
    esac
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
        PROOF_WORKERS=$proof_workers PROOF_HEAD=$tip PROOF_BASE=$tree PROOF_SIDES=$owed PROOF_PYTEST=$pytests PROOF_VITEST=$vitests PROOF_PLAYWRIGHT=$specs \
            uv run --project "$T/../source" jgauge test-slot $lane --thread "$thread" -- bash "$0" --sides | tee -a "$tree/.proof-said"
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
    still_at_head
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
