# Work items

Every piece of work is a work item: one id, a source, an owner and one state, whatever it started from, chat, the view or a command. An item is named `w<n>`, from the project's counter, and no id is given twice. It has a slug once a row of the queue is linked to it, and none before: an item proposed in chat has no row yet.

The record is `~/.local/state/jbus/<project>/items.jsonl`. It is only ever appended to, and never trimmed: `events.jsonl` keeps 14 days, and an item's history is kept whole. One line is one move, `{id, item, at, by, where, line, verb, ...}`: `id` names the line, as `w3.2` for the second line of `w3`, `where` is `chat`, `view`, `cli` or `pass`, and `line` says what happened. An item's state is what its lines come to, by one table of moves:

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

A move the table does not have is refused in one sentence, and nothing is written. Each line is also a quiet event of the kind `item.<verb>` (`item.proposed`, `item.approved`, `item.queued`, `item.launched`, `item.waiting`, `item.resumed`, `item.held`, `item.done`, `item.dropped`, and `item.linked` for a row linked to an item there was), so `jbus events` and the view's feed show it. A pass writes a line only when the state its row comes to changes: a pass with nothing new writes none.

Each line is also a card in your chat bot's chat, and a decision made on a card comes back through the relay ([The relay](the-relay.md#cards-in-your-chat-bots-chat)).

An item's risk is `review` for a merge `jmerge` holds, a `config` wait, and an open gate with a `Holds:` line or whose words name a secret or the config, and `routine` for anything else. `jbus item show` prints it.

| Verb | What it does |
|---|---|
| `jbus item propose --title <title> --by <name> [--where chat\|view\|cli] [--owner <owner>]` | Proposes an item with no row, and prints its id. `--where` is where it was said, `cli` with none, and is the item's source. `--owner` is who will do it, `home` with none. |
| `jbus item approve <id> --by <user> [--where chat\|view\|cli] [--words <words>] [--seen <line id>]` | Your go for an item, by its id. `--by` is refused for anyone but you. `--words` keeps what you said, as you said it. `--seen` names the item's last line as the writer saw it, and a move is refused where the item has moved since. From `chat` it is taken only where the words name the item, by its id or its slug, and its risk is `routine`: a review item, and a redirected one, is refused with the view's link `#/<project>/item/<id>`. |
| `jbus item steer <id> message\|hold\|redirect --seen <line id> --by <name> [--where chat\|view\|cli] [--from <thread id>] [--confirm] [--message <thread id>/<message id>\|--word <id>\|--answer <number>] [<words>]` | Steers an item, as [Steering an item](#steering-an-item) says. |
| `jbus item drop <id> --by <name> [--where chat\|view\|cli] [--words <words>] [--seen <line id>]` | Drops an item that will not be done. |
| `jbus item show <id>` | Prints the item, its state, its slug, its source, its owner, its risk, its last line, and each of its lines. |
| `jbus item list` | Prints every item, one line each: its id, state, risk, slug and title. |

## Steering an item

`jbus item steer` is the one way an item is steered, from chat, the view or the command, and `jbus.steer` decides it.
A steer is one line, `steered`, with its `action`, and one quiet event `item.steered`.
`--seen` is the item's last line as the steerer saw it.
A steer whose `--seen` is not the item's last line is refused, quotes the line that came after, and writes nothing.
So the same steer sent twice is written once.

| Action | What it does |
|---|---|
| `message` | Sends the words to the thread of the item's home, as one queued message with the retry key `item\|<project>\|<id>\|<line id>`. The item does not move. |
| `hold` | Takes the row's go back, as `jbus queue hold` does, and moves the item to `held`. It is refused without `--confirm`. |
| `redirect` | Writes the brief on stdin as the row's brief, takes the row's go back, and moves the item to `proposed`. |

A message is recorded whether or not T3 Code takes it, and the command says which.
One that did not go is sent by the next pass, and `item-sends.json` beside the log says where each went and why one waits.
A running item is not redirected, since its thread has the brief already: a message steers it.

An agent steers only as itself.
`--by` is its role and `--from` its thread, and the line keeps both, with who ran the command (`ran_by`) as an approval keeps it.
A steer `--by` you is taken only with a word of yours it rests on, `--message`, `--word` or `--answer`, as an approval takes one.
In the view, `POST /steer` records the words you typed there as that word, with the basis `view` ([The view](the-view.md#steer-a-work-item)).

A redirected item is approved only by its id: `jbus item approve <id>` from the view or the command.
Until then a pass does not approve it, `jbus item approve` from chat is refused, and `jbus queue approve` refuses its row by any basis, `--rule` with `--follows` included.
A redirect writes its line, with the new brief, before it changes the row.
A redirect that died between the two is marked already, and the first step of the next pass writes the brief and takes the go back before anything is launched.
