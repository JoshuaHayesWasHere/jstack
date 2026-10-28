# Work items

Every piece of work is a work item, with one id, a source, an owner and one state, whether it started in chat, in the view or from a command.
An item is named `w<n>`, from the project's counter, and no id is given twice.
It has a slug once a row of the queue is linked to it, and none before.
An item proposed in chat has no row yet.

The record is `~/.local/state/jbus/<project>/items.jsonl`.
jbus only appends to it, and never trims it.
`events.jsonl` keeps 14 days, but an item's history is kept whole.
One line is one move, `{id, item, at, by, where, line, verb, ...}`.
`id` names the line, as `w3.2` for the second line of `w3`, `where` is `chat`, `view`, `cli` or `pass`, and `line` says what happened.
An item's state is what its lines come to, by one table of moves:

| State | Entered by |
|---|---|
| `proposed` | A proposal: `jbus item propose`, a new row, or a pass that finds a row with no item. |
| `approved` | Your go: `jbus item approve`, or the row's approval in the queue. |
| `queued` | A pass that finds its row approved and waiting to launch. |
| `running` | A pass that finds its row launched, at work, or with a pull request on its way. |
| `waiting_on_you` | A pass that finds a gate, a thread's request or a merge `jmerge` holds, from `queued` or `running`. It goes back to the state it came from. |
| `held` | A pass that finds a queued row's go taken back. A new go approves it again. |
| `done` | A pass that finds its row merged or done. |
| `dropped` | `jbus item drop`, or a pass that finds its row removed. |

jbus refuses a move the table does not have, in one sentence, and writes nothing.
Each line is also a quiet event of the kind `item.<verb>`, so `jbus events` and the view's feed show it.
The kinds are `item.proposed`, `item.approved`, `item.queued`, `item.launched`, `item.waiting`, `item.resumed`, `item.held`, `item.done` and `item.dropped`, and `item.linked` for a row linked to an item that already existed.
A pass writes a line only when its row moves the item to a new state.
A pass with nothing new writes none.

A decision made in your chat bot's chat does not come back through the relay ([Decisions from the chat](the-relay.md#decisions-from-the-chat)).

An item's risk is `review` for these, and `routine` for anything else:

- a merge that `jmerge` holds;
- a `config` wait;
- an open gate with a `Holds:` line, or whose words name a secret or the config.

`jbus item show` prints the risk.

| Verb | What it does |
|---|---|
| `jbus item propose --title <title> --by <name> [--where chat\|view\|cli] [--owner <owner>]` | Proposes an item with no row, and prints its id. `--where` is where it was said, `cli` with none, and is the item's source. `--owner` is who will do it, `home` with none. |
| `jbus item approve <id> --by <user> [--where chat\|view\|cli] [--words <words>] [--seen <line id>]` | Your go for an item, by its id. The command refuses a `--by` of anyone but you. `--words` keeps what you said, as you said it. `--seen` names the item's last line as the writer saw it, and the command refuses the move if the item has moved since. |
| `jbus item drop <id> --by <name> [--where chat\|view\|cli] [--words <words>] [--seen <line id>]` | Drops an item that will not be done. |
| `jbus item show <id>` | Prints the item, its state, its slug, its source, its owner, its risk, its last line, and each of its lines. |
| `jbus item list` | Prints every item, one line each: its id, state, risk, slug and title. |

## Redirecting an item

jbus has no verb that steers an item.
To redirect work, write in the thread of the item's home in T3 Code, or send that home your word with `jbus word`.
A log written before steers were removed may hold a `steered` line: `jbus item show` prints it, and it moves no item.
