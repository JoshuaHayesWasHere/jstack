# t3code-jstack

`t3code-jstack` is T3 Code's newest stable release built with a patch series that this feature keeps.
The series adds jstack's tree sidebar, which draws each jstack project from jbus's state in place of T3 Code's list of threads ([What the tree shows](#what-the-tree-shows)).
Upstream T3 Code knows nothing of jbus, so only this build has the tree.
The series also makes a Cursor instance's agent run its commands in bash or zsh, whichever the `SHELL` of the instance's environment names, so that it can run bash while your login shell and T3's terminals stay zsh.
The Cursor SDK runs only those two, so another `SHELL` there falls back as the SDK chooses.
With no `SHELL` there, or an empty one, it runs the server's shell, as upstream does.
`t3code-jstack` is for Arch only, where it replaces `t3code-bin`.
`jinstall --doctor` lists it only where T3 Code is already a jstack build or upstream's prerelease channel, which it moves to the stable build; upstream's stable `t3code-bin` stays as it is until you build the package once by hand ([Stay up to date](#stay-up-to-date)).

## Install it

1. Install the build's tools: `yay -S vite-plus-bin imagemagick libxcrypt-compat`.
2. Run `jinstall --setup`.
   It downloads upstream's newest stable release tag, `v<major>.<minor>.<patch>`, applies the patches, builds the AppImage, and installs it as the package `t3code-jstack`, which replaces `t3code-bin`.
   The build takes a few minutes, and everything it writes is under `~/.cache/t3code-jstack`, with its log in `build.log`.
3. Quit T3 Code and open it again, so that the new build runs and writes `~/.t3/bin/t3`.
4. Run `jinstall --doctor`, and read `ok optional t3 jstack build -> <version>+jstack.<series>`.

## Stay up to date

`yay` does not update T3 Code, because `t3code-jstack` is a local package.
`jinstall --setup` does: the doctor reads `old` when upstream has a newer stable release or jstack's patches changed, and setup builds and installs the newer one.
A running build of a prerelease reads `old` too, and setup moves it to the stable release.

Each build tries three tags in turn: upstream's newest stable release, the release of the running build, and the tag in the PKGBUILD.
When the patches do not apply to a tag, setup writes the tag and the series to `~/.cache/t3code-jstack/failed`, so that it does not try that pair again, and tries the next tag.
While the newest release refuses the patches, the doctor reads `ok` with `<tag> does not take jstack's patches: rebase them`, and the build stays on the last release that took them.
Any other failure stops the build and names its log.

To build by hand, without jinstall, run the command below.
`T3CODE_JSTACK_TAG` picks the tag, and the PKGBUILD's tag, a stable release, is the default.
To pick a nightly by hand, set `T3CODE_JSTACK_TAG` to its tag, such as `v0.1.6-nightly.20261030.3917`; jinstall never picks one, and its doctor reads that build as `old`.

```sh
env BUILDDIR=~/.cache/t3code-jstack PKGDEST=~/.cache/t3code-jstack SRCDEST=~/.cache/t3code-jstack \
  makepkg -si -D <jstack>/features/t3code-jstack/packaging
```

The package has the stable package's commands, `t3code` and `t3-code-desktop`, adds `t3code-jstack`, and keeps the two commands of the earlier jstack builds as links, so that autostart entries and scripts that call them keep working.
Its updater is off, so the app never swaps itself back to upstream's build.
T3 Code's stable and prerelease builds share their data in `~/.t3`, so the move to the stable build keeps every thread and setting.

## Switch the tree

The tree is on by default.
Its switch and its options are in T3 Code's Settings, under Labs.
Switched off, the sidebar is upstream's.
The doctor never reads the switch, so it stays quiet whatever you choose.

## What is in the folder

| Path | Holds |
|---|---|
| `packaging/PKGBUILD` | The package: upstream's tag in `_tag`, the patches in `_patches`, and the version in `pkgver`. |
| `packaging/*.patch` | The patch series, in the order of its names. |
| `packaging/probe/` | `frames.mjs`, which times a jbus write to the tree's websocket frame ([How fresh the tree is](#how-fresh-the-tree-is)). |

`pkgver` is the release's version with `.jstack.<series>` added, where the series is the first 10 hex digits of the sha256 of the patches, read in name order.
The app's version carries it as `+jstack.<series>`, and the doctor compares that with the patches in the folder.

## Change the patches

The patches come from a T3 Code checkout with a `jstack` branch cut from the stable tag in `_tag`.

1. Commit the change on the checkout's `jstack` branch.
2. Write the series again: `git -C <checkout> format-patch <tag>..jstack -o <jstack>/features/t3code-jstack/packaging`.
   Take out the patch files the new series no longer has, and list each new one in `_patches`.
3. Set the series in `pkgver`.
4. Run `jinstall --setup` to build and install it.

When the doctor says a release does not take the patches, rebase the checkout's `jstack` branch onto that tag, write the series again, and set `_tag` and `pkgver` to it.

## What the tree shows

The tree draws one row for the project and its root home, the domain homes under it, and each scout, crew and review as a quiet row with its stage.
A domain home with no live work is one line, its name and its age, with nothing to unfold.
A home lists only its open rows: a task leaves the tree once it merges or is done, and the project row counts what merged since you last opened its root home.
A task in review says which part it is in, "review 1", "fixing", "review 2", "checks" or "rebase".
A crew task's row draws its stage as one ring filled by thirds, crew, review and merge, empty while it is queued.
A scout's row draws a diamond, hollow while queued, half filled while it scouts and filled once its report is in, beside the word "queued", "scouting" or "report in", which it reads from jbus's `work.json`.
One colour, sky, marks live work only: a ring or diamond at work, and the badge of a project with live work under it.
Live is a launched task that does not ask you, is not quiet, stalled or held, and is not a scout whose report is in.
Amber marks what asks you, and every other mark and badge is neutral.
The tree keeps to two type sizes and one weight: every name is 13px and every word beside it 11px, all at 400, and its levels step by ink and row height.
A row's "Open brief" draws the brief as what it says: its one line, chips for Size, Review, Playbook, Pull request and Home, what it must not touch, then its lines in its order, with the rest under "More" and the Markdown one click away.
A Builds on or Follows link in it selects that row in the tree.
A task says "stalled" and for how long, beside its stage, only when its crew sits idle past the quiet threshold while jbus's `work.json` says the crew owes its pull request's next move (`who` is `crew`), and a crew idle while CI, jmerge or another row holds its pull request is not stalled.
A row's hover and the head of its menu say what jbus says it waits on, such as "waits on the check runner".
A task jmerge or jbus holds is shown with "held" and for how long, its reason on hover and at the head of its menu.
Every other T3 project is a root row of the same size over its threads, and "No project" is pinned last.
A project added to T3 is a root row at once, before it has a thread, and asks once whether to start a jstack home for it.
Root rows sort into an active group and an idle one below a divider, on their own, and within each group a root row keeps the place you drag it to, or move it to with Alt+ArrowUp and Alt+ArrowDown.
A row's menu, by right-click, the ContextMenu key or Shift+F10, holds what the row can do, and a home's actions go to the home as your own message: New crew task and New scout fill its composer, New child home asks the root home for a scope, Archive home sends `/handoff`, and Start a home starts a root home in a project with none.

## How fresh the tree is

The server sends the tree a change to a file it reads from jbus or a home within a tenth of a second.
It refreshes on the first write to such a file, and folds the writes that come in the next 50 ms into one more refresh, so a write never waits longer than 50 ms and two refreshes.
It wakes only on the files it reads, `work.json`, `merged.json`, `questions.json`, `waiting-on-user.json` and `held.json` of jbus, a home's `home-id`, a scope's `home-id`, `prefix`, `plan.md` and `handoff.md`, a task's or a scout's brief, and a folder made or removed, and never on jbus's locks and logs beside them.
Each refresh is a span, `JbusWork.refresh`, and logs its duration at the debug level.

The tree is as fresh as jbus's files, and jbus writes `work.json` at each pass.

To time it, run the probe against a T3 Code checkout with its packages installed:

```sh
node features/t3code-jstack/packaging/probe/frames.mjs <checkout> 60
```

It runs the checkout's own `JbusWork` behind the websocket protocol of the server's `subscribeJbusWork`, on a copy of the state in a temp folder, and makes every write jbus and the homes make in the live folders again in the copy while it runs.
Then it writes `work.json` the way jbus does, with one more row, 60 times, and prints the delay from each write to the frame that carries it.
It only reads the live state.
