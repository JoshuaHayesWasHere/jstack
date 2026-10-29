# The view's look

This page is reference for working on the page of `jbus view` ([The view](../jbus/the-view.md)).

The page follows the system's light or dark setting.
The header's button overrides it with Auto, Light or Dark, and `&theme=` in the address forces one.
Light is a canvas of `#FAF7F2`, with white cards.
Dark is `#14191A` with `#1C2324` cards.
Each colour is one token named for its role: `canvas`, `surface`, `sunk`, `ink`, `ink-2`, `ink-3`, `line` for a control's border, `hair` for a divider, `brand` and `on-brand` for the filled button, `due` and `missed` with their tints, and `focus`.
Each token is set once, as `light-dark(<light>, <dark>)`, in the page's one `:root` block.
The page uses colour only where it means something.
Amber (`due`) is what waits on you, and red (`missed`) is what broke.
The page shows who holds a task by a shape and a name, not by a colour, and draws nothing healthy or merged in green.
`features/jbus/tests/test_view_tokens.py` holds each token to WCAG 2.2 AA in both themes: text at 4.5:1 on every background, and a control's border and the focus ring at 3:1.

The text is set in Atkinson Hyperlegible Next, one variable font that the view serves itself at `/font.woff2`.
The page's policy is `font-src 'self'`, so it loads fonts from no other host.
The font's licence is beside it, in `features/jbus/src/jbus/view/OFL.txt`.
The sizes are 13 px for the scratch-home line, the smallest on the page, 15 for a caption, 18 for body text, 20 for a heading and 24 for a title.
Mono is for slugs and commits.

## The kept shots

`features/jbus/tests/fixtures/jbus-view/shots/` keeps a shot of each route, and of the overview on each day of `days.DAYS`, with `browser.txt` naming the browser that drew them.
The shot tests compare the page with them (`test_view_page_look.py`, `test_view_page_days.py`), and only the Chrome for Testing build that browser.yml pins draws them.
The kept shots are main's, and only the shots row redraws them (`features/jbus/src/jbus/shots.py`).

A feature's pull request leaves the shots as main has them.
The borders check fails a pull request that changes a kept shot or `browser.txt` beside any other file (`features/jbus/scripts/kept_shots.py`).
A pull request that changes only kept shots is the shots row's kind, and passes.

The browser run still runs on a pull request that changes the view, and compares its page with main's shots.
There a shot that moved, or a route with no kept shot, is a skip that says how much moved and where the shot it drew is, as is a browser that is not the one that drew them.
The same holds for a manual run on a branch and for a run on a desk.
What moved is the pull request's change, or a look that merged since the last shots row, so a skip is no verdict on the change: read the drawn shot to see it.
Every other browser test judges a pull request as before.

A CI run on main or on a tag, the nightly and a release, fails each shot that moved, with the line `keep the shots of this run's jbus-view-shots artifact`.
jbus reads that run and files the shots row of the day, `shots-<day>`, from its failed shot tests, approved by the rule for a row jbus filed from a red run.
Its other failures, if any, file `browser-red-<day>` as before.
A job where fewer tests said that line than shot tests failed had a shot test fail some other way, so that job's shot tests are in `browser-red-<day>` too (`jbus.shots.moved_in`).
A further red run that day folds into the same rows.
A run whose only failures were shots holds no pull request as a red main in `jmerge`.
On a day that also has a `browser-red-` row, a shots row's pull request whose own browser run fails waits for that fix as any other pull request does.

The shots row's pull request keeps the run's `jbus-view-shots` artifact under the shots directory and changes nothing else.
Its review is where a feature's change to the look is looked at, after that feature merged.
A bump of the pinned Chrome goes in a pull request of its own with no shot in it: the next nightly fails every shot, and its shots row redraws them.

`JSTACK_SHOTS=keep` still writes the shots afresh in place of comparing them, for a look on a desk, and `JSTACK_SHOTS_OUT=<dir>` writes each shot as drawn into that folder.
