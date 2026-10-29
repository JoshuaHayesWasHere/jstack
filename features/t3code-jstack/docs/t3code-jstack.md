# t3code-jstack

T3 Code's sidebar lists threads.
jstack's tree sidebar draws a jstack project from jbus's state instead: one row for the project and its root home, the domain homes under it, and each scout, crew and review as a quiet row with its stage.
Every other T3 project is a root row of the same size over its threads, and "No project" is pinned last.
Root rows sort into an active group and an idle one below a divider, on their own, and within each group a root row keeps the place you drag it to, or move it to with Alt+ArrowUp and Alt+ArrowDown.
A row's menu, by right-click, the ContextMenu key or Shift+F10, holds what the row can do, and a home's actions go to the home as your own message: New crew task and New scout fill its composer, New child home asks the root home for a scope, Archive home sends `/handoff`, and Start a home starts a root home in a project with none.
Upstream T3 Code knows nothing of jbus, so the tree is a patch series that this feature keeps, and `t3code-jstack` is T3 Code nightly built with it.
It is for Arch only, where it replaces `t3code-nightly-bin`, and `jinstall --doctor` lists it only where T3 Code is a nightly build.

## Install it

1. Install the build's tools: `yay -S vite-plus-bin imagemagick libxcrypt-compat`.
2. Run `jinstall --setup`.
   It downloads upstream's newest nightly tag, applies the patches, builds the AppImage, and installs it as the package `t3code-jstack`, which replaces `t3code-nightly-bin`.
   The build takes a few minutes, and everything it writes is under `~/.cache/t3code-jstack`, with its log in `build.log`.
3. Quit T3 Code and open it again, so that the new build runs and writes `~/.t3/bin/t3`.
4. Run `jinstall --doctor`, and read `ok optional t3 jstack build -> <version>+jstack.<series>`.

## Stay up to date

`yay` no longer updates T3 Code, because `t3code-jstack` is a local package.
`jinstall --setup` does: the doctor reads `old` when upstream has a newer nightly or jstack's patches changed, and setup builds and installs the newer one.

Each build tries three tags in turn: upstream's newest nightly, the nightly of the running build, and the tag in the PKGBUILD.
When the patches do not apply to a tag, setup writes the tag and the series to `~/.cache/t3code-jstack/failed`, so that it does not try that pair again, and tries the next tag.
While the newest nightly refuses the patches, the doctor reads `ok` with `<tag> does not take jstack's patches: rebase them`, and the build stays on the last nightly that took them.
Any other failure stops the build and names its log.

To build by hand, without jinstall, run the command below.
`T3CODE_JSTACK_TAG` picks the tag, and the PKGBUILD's tag is the default.

```sh
env BUILDDIR=~/.cache/t3code-jstack PKGDEST=~/.cache/t3code-jstack SRCDEST=~/.cache/t3code-jstack \
  makepkg -si -D <jstack>/features/t3code-jstack/packaging
```

The package keeps the nightly's commands, `t3code-nightly` and `t3-code-nightly-desktop`, and adds `t3code-jstack`.
Its updater is off, so the app never swaps itself back to upstream's build.
It is a nightly build, so it reads and writes the nightly's data.

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

`pkgver` is the nightly's version with `.jstack.<series>` added, where the series is the first 10 hex digits of the sha256 of the patches, read in name order.
The app's version carries it as `+jstack.<series>`, and the doctor compares that with the patches in the folder.

## Change the patches

The patches come from a T3 Code checkout with a `jstack` branch cut from the nightly tag in `_tag`.

1. Commit the change on the checkout's `jstack` branch.
2. Write the series again: `git -C <checkout> format-patch <tag>..jstack -o <jstack>/features/t3code-jstack/packaging`.
   Take out the patch files the new series no longer has, and list each new one in `_patches`.
3. Set the series in `pkgver`.
   Until you do, `make check` fails on `test_the_pkgbuild_names_the_series_and_each_patch_of_its_folder` and names the series.
4. Run `jinstall --setup` to build and install it.

When the doctor says a nightly does not take the patches, rebase the checkout's `jstack` branch onto that tag, write the series again, and set `_tag` and `pkgver` to it.
