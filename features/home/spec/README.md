# The TLA+ models of home

Each model has its prose in `<Model>.md` beside its `<Model>.tla`: what it models, its rules, how to check them, how to draw its chart, and what it leaves out.
A new model adds its own `<Model>.md` and edits nothing here, so two pull requests that each add a model touch no file in common; `ls *.md` lists them.

`HomeTree.tla` holds the rules that `HomeTreeToday.tla` extends with the code's steps, so `HomeTreeToday.md` tells both.
