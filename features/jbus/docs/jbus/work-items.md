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
| `held` | A pass that finds a queued row's go taken back, or a hold steer. A new go approves it again. |
| `done` | A pass that finds its row merged or done. |
| `dropped` | `jbus item drop`, or a pass that finds its row removed. |

jbus refuses a move the table does not have, in one sentence, and writes nothing.
Each line is also a quiet event of the kind `item.<verb>`, so `jbus events` and the view's feed show it.
The kinds are `item.proposed`, `item.approved`, `item.queued`, `item.launched`, `item.waiting`, `item.resumed`, `item.held`, `item.done` and `item.dropped`, and `item.linked` for a row linked to an item that already existed.
A pass writes a line only when its row moves the item to a new state.
A pass with nothing new writes none.

Each line is also a card in your chat bot's chat, and a decision made on a card comes back through the relay ([The relay](the-relay.md#cards-in-your-chat-bots-chat)).

An item's risk is `review` for these, and `routine` for anything else:

- a merge that `jmerge` holds;
- a `config` wait;
- an open gate with a `Holds:` line, or whose words name a secret or the config.

`jbus item show` prints the risk.

| Verb | What it does |
|---|---|
| `jbus item propose --title <title> --by <name> [--where chat\|view\|cli] [--owner <owner>]` | Proposes an item with no row, and prints its id. `--where` is where it was said, `cli` with none, and is the item's source. `--owner` is who will do it, `home` with none. |
| `jbus item approve <id> --by <user> [--where chat\|view\|cli] [--words <words>] [--seen <line id>]` | Your go for an item, by its id. The command refuses a `--by` of anyone but you. `--words` keeps what you said, as you said it. `--seen` names the item's last line as the writer saw it, and the command refuses the move if the item has moved since. From `chat`, the command takes the go only when the words name the item, by its id or its slug, and its risk is `routine`. It refuses a review item or a redirected one, with the view's link `#/<project>/item/<id>`. |
| `jbus item steer <id> message\|hold\|redirect --seen <line id> --by <name> [--where chat\|view\|cli] [--from <thread id>] [--confirm] [--message <thread id>/<message id>\|--word <id>\|--answer <number>] [<words>]` | Steers an item, as [Steering an item](#steering-an-item) says. |
| `jbus item drop <id> --by <name> [--where chat\|view\|cli] [--words <words>] [--seen <line id>]` | Drops an item that will not be done. |
| `jbus item show <id>` | Prints the item, its state, its slug, its source, its owner, its risk, its last line, and each of its lines. |
| `jbus item list` | Prints every item, one line each: its id, state, risk, slug and title. |

## Steering an item

`jbus item steer` is the one way to steer an item, from chat, the view or the command, and `jbus.steer` decides it.
A steer is one line, `steered`, with its `action`, and one quiet event `item.steered`.
`--seen` is the item's last line as the steerer saw it.
jbus refuses a steer whose `--seen` is not the item's last line, quotes the line that came after, and writes nothing.
So the same steer sent twice is written once.

| Action | What it does |
|---|---|
| `message` | Sends the words to the thread of the item's home, as one queued message with the retry key `item\|<project>\|<id>\|<line id>`. The item does not move. |
| `hold` | Takes the row's go back, as `jbus queue hold` does, and moves the item to `held`. It is refused without `--confirm`. |
| `redirect` | Writes the brief on stdin as the row's brief, takes the row's go back, and moves the item to `proposed`. |

jbus records a message whether or not T3 Code takes it, and the command says which.
The next pass sends a message that did not go, and `item-sends.json` beside the log says where each went and why one waits.
jbus does not redirect a running item, since its thread has the brief already.
A message steers it instead.

An agent steers only as itself.
`--by` is its role and `--from` is its thread.
The line keeps both, and keeps who ran the command (`ran_by`), as an approval does.
jbus takes a steer `--by` you only when the steer names a word of yours (`--message`, `--word` or `--answer`), as an approval must.
In the view, `POST /steer` records the words you typed there as that word, with the basis `view` ([The view](the-view.md#steer-a-work-item)).

You approve a redirected item only by its id, with `jbus item approve <id>` from the view or the command.
Until then, a pass does not approve it, and `jbus item approve` from chat refuses it.
`jbus queue approve` refuses its row on any basis, `--rule` with `--follows` included.
A redirect writes its line, with the new brief, before it changes the row.
If a redirect died between the two, its line is already written.
Then the first step of the next pass writes the brief and takes the go back before anything launches.
