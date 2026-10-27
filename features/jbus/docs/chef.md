# The Chef

The Chef is an agent of yours, outside a home, that keeps the queue for you with `jbus queue`.
`jbus` does the routine work with no model, and the Chef is a model that reads what `jbus` found and puts your decisions into the queue.

The Chef is optional.
`jbus` sends the Chef nothing: it sends its wakes to each project's home thread through T3 Code, and has no webhook ([Where wakes go](jbus/events-and-wakes.md#where-wakes-go)).
A Chef reads what it needs itself, with `jbus queue show` and `jbus digest --json`.

The Chef is not the relay's chat bot.
The Chef may run `jbus queue`.
[The relay](jbus/the-relay.md) is a separate, optional server that sends what blocks on to a chat bot of your own, and the chat bot runs no command of jbus's.
A machine may have either, both or neither.

[What the Chef may run](jbus/what-the-chef-may-run.md) is its contract.
