# Add a panel to the view

These steps add a drawer to the page of `jbus view`, in a checkout of jstack.

A panel is one folder, `features/jbus/src/jbus/view/panels/<name>/`, with two files, and no other file names it.

1. Make the folder.
2. Write `panel.py`, its data: `build(read)` returns a dict, `SHAPE` lists the keys that dict may have, and `SOURCES` names each file it reads and who writes it.
3. Write `panel.js`, its drawing: one call, `panel({ drawer: function (arg, data) { ... } })`, that returns the drawer's HTML.
   Add `card` for a card on the first screen.
4. Open it from somewhere: put `data-open="<name>"` on its card, or add it to `adds.task` or `adds.you`, which put a line in the task drawer or a count beside the Needs you queue.
5. Set `FIRST = True` in `panel.py` only when the first screen needs the data.
   Without it the page asks `/panel/<name>.json` when the drawer opens.

A panel whose data the server reads itself says so with `reads`, and its drawer's head then says it is read now.

An edit of `panel.js` is live on the next request, and the server restarts itself for `panel.py`.
`features/jbus/src/jbus/view/panels/__init__.py` lists everything a panel may declare.
