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

The text is set in Atkinson Hyperlegible Next, one variable font the view serves itself at `/font.woff2` (`font-src 'self'`, and no other host), with its licence beside it in `features/jbus/src/jbus/view/OFL.txt`.
The sizes are 15 px for a caption, the smallest on the page, 18 for body text, 20 for a heading and 24 for a title.
Mono is for slugs and commits.
