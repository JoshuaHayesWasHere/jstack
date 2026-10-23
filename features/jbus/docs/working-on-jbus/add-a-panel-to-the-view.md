# Add a panel to the view

These steps add a drawer to the page of `jbus view`, in a checkout of jstack.

A panel is one folder, `features/jbus/src/jbus/view/panels/<name>/`, with two files.
No other file names the panel.

1. Make the folder.
2. Write `panel.py`, which builds the panel's data.
   `build(read)` returns a dict, `SHAPE` lists the keys that dict may have, and `SOURCES` names each file the panel reads and who writes that file.
3. Write `panel.js`, which draws the panel with one call, `panel({ drawer: function (arg, data) { ... } })`.
   The `drawer` function returns the drawer's HTML.
   Add `card` for a card on the first screen.
4. Give the drawer a way to open.
   Put `data-open="<name>"` on its card, or add it to `adds.task` or `adds.you`, which put a line in the task drawer or a count beside the Needs you queue.
5. Set `FIRST = True` in `panel.py` only when the first screen needs the data.
   Without it the page asks `/panel/<name>.json` when the drawer opens.

When the server reads a panel's data itself, the panel says so with `reads`.
The head of the panel's drawer then says that the server read the data at that request.

An edit of `panel.js` is live on the next request, and the server restarts itself after an edit of `panel.py`.
`features/jbus/src/jbus/view/panels/__init__.py` lists everything a panel may declare.
