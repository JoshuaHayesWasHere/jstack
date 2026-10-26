---
name: maintain-verification-skill
description: "Keep a repo's verify skill, `.claude/skills/verify-<app>/` or a `verify-<app>` project skill, and its feature map honest as the app changes: typed in the repo's home, it sends one scout per feature file to read the feature from source, then writes one crewmate brief for the live pass over every feature and at most one pull request of proven corrections. Use for /maintain-verification-skill or \"audit the verify skill\"."
tip: sends a scout per feature of the verify skill, then one crewmate drives them all and fixes the map | audit the verify skill | maintain the verify skill | is the feature map still right | verify skill drift
disable-model-invocation: true
card: "Distrust the change | 7 | Keeps the repo's verify skill honest: one scout per feature file reads the feature from source and reports the drift, then one crewmate drives every feature live and ships at most one pull request of proven corrections. | Reach for it, in the home, when the app has changed since the verify skill was written or last checked. | op: the operator; model: a home"
---

# Maintain a verification skill

Source: pstack, `pstack/skills/maintain-verification-skill/SKILL.md`

A feature map rots the moment the app changes.
This skill is the upkeep loop for a verify skill that `/create-verification-skill` wrote, or any project skill in `.claude/skills/verify-*/` with a `features/` map.
A repo that keeps its own skills in its features, as jstack does, names such a skill in `skills.json`, under `projectSkills`: its `path` is the skill's folder, which every worktree has.
The unit of rigor is the feature, not every sentence: every feature file is read from source, and every feature is driven live.

## Where it runs

Type it in the repo's home, `/maintain-verification-skill [<app>]`.
The home does no research and drives nothing: it writes requests and a brief, and launches threads.
The reading is done by scouts, one per feature file, and the live pass by one crewmate, each a durable thread with its own file under `$H`.
No step starts a subagent.

In each block below, set `app=` to the `<app>` typed, or leave it empty, and `scope=` to the scope's name in a scoped home, or leave it empty in the root home.

## 1. Send the scouts

Run this:
It finds the verify skill on the default branch, a tracked `.claude/skills/verify-<app>/` or a `verify-<app>` item of `skills.json`'s `projectSkills`, reads the names of its feature files and nothing in them, and writes one scout request for each, `$H/scouts/maintain-<app>-<commit>-<feature>.md`, where `<commit>` is the default branch's commit the audit reads:

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=${H:-~/.local/state/home/$R}
app=''
scope=''
git fetch -q origin 2> /dev/null
base=$(git symbolic-ref -q --short refs/remotes/origin/HEAD || echo HEAD)
tracked=$(git ls-tree -d --name-only "$base" .claude/skills/ 2> /dev/null | sed -n 's|^\.claude/skills/verify-\([^/]*\)$|\1 &|p')
declared=$(git show "$base:skills.json" 2> /dev/null | jq -r '.projectSkills[]? | select(.name | startswith("verify-")) | "\(.name | ltrimstr("verify-")) \(.path)"' 2> /dev/null || true)
found=$(printf '%s\n%s\n' "$tracked" "$declared" | sed '/^$/d' | sort -u -k 1,1)
if [ -n "$app" ]; then found=$(printf '%s\n' "$found" | grep "^$app " || true); fi
if [ -z "$found" ]; then
    echo "no verify skill: $base has no .claude/skills/verify-${app:-*}/ and its skills.json names no verify-${app:-*} project skill: brief a crewmate to run /create-verification-skill instead"
elif [ "$(printf '%s\n' "$found" | wc -l)" -gt 1 ]; then
    echo "which one: type /maintain-verification-skill <app> with one of these:"
    printf '%s\n' "$found" | sed 's|^\([^ ]*\) |  \1: |'
else
    app=${found%% *}
    dir=${found#* }
    run="maintain-$app-$(git rev-parse --short=7 "$base")"
    features=$(git ls-tree --name-only "$base" "$dir/features/" | sed -n 's|.*/\([^/]*\)\.md$|\1|p' | grep -vx README || true)
    if [ -z "$features" ]; then
        echo "no feature map: $dir/features/ on $base has no feature file: where $dir/SKILL.md keeps its map elsewhere, this audit cannot read it, so stop; otherwise brief a crewmate to seed it, as section 3 of /create-verification-skill says"
    else
        mkdir -p "$H/scouts"
        echo "$dir" > "$H/scouts/$run.dir"
        for feature in $features; do
            S="$run-$feature"
            if [ -f "$H/scouts/$S.md" ]; then
                echo "kept: scouts/$S.md"
                continue
            fi
            {
                echo "# $S: how the feature $feature works from source, where \`$dir/features/$feature.md\` drifts from it, and one recipe to drive it live"
                echo "Request: \"/maintain-verification-skill: keep \`$dir\` and its feature map honest\" (the user, typed in the home, $(date +%Y-%m-%d))"
                echo "Questions:"
                echo "- How does the feature in \`$dir/features/$feature.md\` work, from source: its user-facing entry points, each with its \`path:line\`?"
                echo "- Which statements of that file does the code no longer bear out, each with the statement and the \`path:line\` that contradicts it, or none?"
                echo "- Which user-facing surface of this feature changed since the file last changed (\`git log\` on the paths it names) and is missing from the file, each with a concrete source path, or none?"
                echo "- One live-verification recipe: the commands, in the harness that \`$dir/SKILL.md\` names, that drive every sub-feature from as few app states as practical, and the end state that proves each."
                echo "Deliver:"
                echo "- Under \"## Report\" in this file, in the scout report's shape: the four answers under Answers, and a first Findings item \`Verdict: clean\` or \`Verdict: drift\`."
                echo "Playbook: investigation"
                echo "Out of bounds: read-only. Never launch, doctor or drive the app, never run a script of \`$dir/scripts/\`, and edit no file: the crewmate that follows does the live pass."
                if [ -n "$scope" ]; then echo "Home: $scope"; fi
            } > "$H/scouts/$S.md"
            echo "wrote: scouts/$S.md"
        done
        echo "run: $run, $(printf '%s\n' $features | wc -l) feature files, launch them ten at a time"
    fi
fi
```

On `no verify skill`, `no feature map` or `which one`, do what it says and stop.
On `run:`, launch each request it wrote or kept as the home skill's "Sending a scout" launches a durable scout, from its step 2, with the slug the line names.
Launch at most ten in a step, as `features/arena-swarm/skills/swarm/playbooks/swarm.md` has it: the next ten go out once the reports of the first are in.
Run again at the same commit, the block keeps every request of the run and writes only the ones missing.
Once the default branch has moved, the same command starts a new audit, with a new run name.

## 2. Write the crewmate's brief

Once every scout of the run has reported, or has gone quiet after one message from the home, run this, with `run=` set to the run the first block printed:

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=${H:-~/.local/state/home/$R}
T=$(realpath ~/.claude/skills/maintain-verification-skill/../../templates 2> /dev/null)
scope=''
run='<run>'
dir=$(cat "$H/scouts/$run.dir" 2> /dev/null)
B="$H/tasks/$run.md"
if [ -z "$dir" ]; then
    echo "no run: scouts/$run.dir is not there: run the first block"
elif [ -f "$B" ]; then
    echo "kept: tasks/$run.md is there"
else
    mkdir -p "$H/tasks"
    read=
    gaps=
    for S in $(cd "$H/scouts" && ls "$run"-*.md | sed 's/\.md$//'); do
        status=$(sed -n '/^## Report/,$ s/^Status: \([a-z][a-z ]*\).*/\1/p' "$H/scouts/$S.md" | tail -n 1)
        verdict=$(sed -n '/^## Report/,$ s/^[-* ]*Verdict: \([a-z]*\).*/\1/p' "$H/scouts/$S.md" | tail -n 1)
        if [ -z "$status" ]; then
            gaps="$gaps ${S#"$run"-}"
        else
            read="$read; \`scouts/$S.md\`, $status, ${verdict:-no verdict given}"
        fi
    done
    {
        echo "# $run: drive every feature of \`$dir\` live, fix the drift the scouts proved, and ship at most one pull request"
        echo "Task: \"/maintain-verification-skill: keep \`$dir\` and its feature map honest\" (the user, typed in the home, $(date +%Y-%m-%d))"
        echo "Done when:"
        echo "- \`$dir/features/README.md\` lists each feature file once, and every file it lists is there"
        echo "- every feature file has its scout's report or, for a gap, a source reading of your own, and every drift a report names is checked against the line it cites"
        echo "- every feature is driven live at least once in one pass that follows the Launch section of \`$dir/SKILL.md\`: Doctor before the first drive, after every failed drive and on each fresh session, the evidence still at its named place after every cleanup, and nothing a drive started left running at the end"
        echo "- a feature that cannot be reached is \`verified-unreachable\` with the prerequisite it lacks and the route tried, and a prerequisite the map omits is drift"
        echo "- each finding is one of three: doc drift (the map is fixed), a harness gap (the harness is fixed, its scripts executable and their invocation in \`$dir/SKILL.md\`, and driven live again), or a product gap (in the Result for the user, and out of the diff)"
        echo "- the Result says the outcome, \`clean\`, \`changed\` or \`blocked\`, with every feature and how it was covered: \`clean\` and \`blocked\` open no pull request, \`changed\` opens one"
        echo "Proves it: the live pass, with each feature's evidence listed after the final cleanup, and the existing CI check on the pull request, green, when there is one"
        echo "Size: M"
        echo "Where: \`$dir/\`"
        echo "Do not touch: product code, and anything outside \`$dir/\`"
        echo "Decisions: none"
        echo "Design: none, the scouts' reports are the source reading and the map is the shape"
        echo "Skills: blast-radius, prove-it-works"
        echo "Pull request: open one when done"
        echo "Review: review"
        echo "Playbook: authoring-a-skill"
        if [ -n "$scope" ]; then echo "Home: $scope"; fi
        echo "Read: \`$dir/SKILL.md\` and \`$dir/features/\`${read}"
        echo "Rests on: the scouts' reports above${gaps:+; no report for:$gaps, which you read from source yourself}"
        echo "Sources: \`features/skill-library/skills/maintain-verification-skill/SKILL.md\`, the steps this brief carries"
        echo "Ruled out: a subagent per feature (not durable), driving the app from the home or a scout"
    } > "$B"
    echo "wrote: tasks/$run.md"
    uv run --project "${T:?the templates of jstack are not found}/../source" python -c '
import sys
from jbriefs.parse import faults
found = faults(open(sys.argv[1]).read())
print("\n".join("fault: " + one for one in found) or "lint: ok")
' "$B"
fi
```

On `lint: ok`, hand the brief to a crewmate as the home skill's "Handing a task to a crewmate" says.
On a `fault:` line, fix the brief by hand and run the lint again before it goes out.
The crewmate's Result names the outcome, and the home reads it there.
