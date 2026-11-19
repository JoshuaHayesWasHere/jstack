#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.." || exit 1

declare -A want
for name in prototype full-stop full-send; do want[$name]="Modes 1"; done
order=1
while IFS= read -r row; do
    order=$((order + 1))
    group=$(sed -E 's/^\| \[([A-Za-z]+)\].*/\1/' <<<"$row")
    for name in $(grep -oE '`[^`]+`' <<<"${row#*) |}" | tr -d '`'); do want[$name]="$group $order"; done
done < <(grep -E '^\| \[[A-Za-z]+\]\(' README.md)
principles="Principles $((order + 1))"

fails=0
fail() { echo "FAIL $1"; fails=$((fails + 1)); }
for dir in skills/*/; do
    name=$(basename "$dir")
    expected=${want[$name]:-}
    [[ -z $expected && $name == principle-* ]] && expected=$principles
    frontmatter=$(sed -n '2,/^---$/p' "$dir/SKILL.md")
    got="$(sed -nE 's/^  group: (.+)$/\1/p' <<<"$frontmatter") $(sed -nE 's/^  group-order: "([0-9]+)"$/\1/p' <<<"$frontmatter")"
    if [[ -z $expected ]]; then
        fail "$name is in no README group"
    elif [[ $got != "$expected" ]]; then
        fail "$name has metadata '$got', the README says '$expected'"
    fi
done
for name in "${!want[@]}"; do
    [[ -d skills/$name ]] || fail "the README lists $name, which has no skill folder"
done

if ((fails)); then echo "$fails failed"; exit 1; fi
echo "ok   every skill's metadata.group matches the README"
