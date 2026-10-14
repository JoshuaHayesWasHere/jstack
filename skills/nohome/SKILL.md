---
name: nohome
description: Opt out of the automatic home - make this thread an ordinary thread, or switch the automatic home off or back on for the whole repo, or switch the repo's automatic merge off or back on. Use when the user invokes /nohome or $nohome, or says this thread should not be a home, should just do the work itself, or should stop planning and handing out.
tip: makes this thread an ordinary one that does the work itself | not be a home | not a home | stop planning | do the work yourself | stop handing out
user-invocable: true
card: "Run the pipeline | 7 | Opts this thread, or every new thread in the repo, out of the automatic home. With `merge` it switches the repo's automatic merge off or on. | Reach for it when a thread should just do the work itself, or merges should wait. | op: the operator"
---

# nohome

A new T3 Code thread in any repo's main checkout becomes that repo's home by itself: a session-start hook (`hooks/home-start.sh` in the checkout that holds this skill) tells it to follow the `home` skill. This skill is the way out.

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
```

## `/nohome`: this thread only

This thread is not a home. Disregard the session-start `[home]` instruction and the `home` skill's rules: this thread may edit the repo, run its checks and do the work itself, like any ordinary thread. Do not read or write anything in `$H` unless the user asks.

Say so in one line, then carry on with what the user asked. If the thread had already handed tasks to crewmates, name them: they keep running, and the next home will pick up their results.

## `/nohome repo`: every new thread in this repo

Run this with the block at the top. It also works in a repo where no home has ever started:

```sh
mkdir -p "$H" && touch "$H/off"
```

New threads in this repo start as ordinary threads until it is switched back on. `/home` still works when typed. This thread also stops being a home, as above.

## `/nohome on`: switch it back on

Run this with the block at the top:

```sh
rm -f "$H/off"
```

New threads in this repo start as homes again. This thread does not change: type `/home` to make it one.

## `/nohome merge`: no automatic merge in this repo

Every repo is merged automatically until it is switched off: `jmerge` merges each pull request that is reviewed, fixed and green. Run this with the block at the top to switch that off for this repo. It also works in a repo where no home has ever started:

```sh
mkdir -p "$H" && : > "$H/merge-off"
```

From then on `jmerge` merges nothing in this repo, whether a home runs it or `jbus` does, and prints `wait <number> <url>: auto-merge is off for this repo` for each pull request it would have merged: those are the user's to merge. Everything else goes on as before, the reviews and the sweep included. This thread stays what it was, a home or not.

## `/nohome merge on`: switch the merge back on

Run this with the block at the top:

```sh
if [ -e "$H/merge-off" ]; then rm "$H/merge-off"; fi
```

The next run of `jmerge` merges what is ready again.
