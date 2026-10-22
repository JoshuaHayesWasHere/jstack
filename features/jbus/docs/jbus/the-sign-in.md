# The sign-in

`jbus t3 login` signs jbus in to the T3 Code server and keeps the token in `~/.config/jbus/t3.json`, mode 600.
jbus does not renew the sign-in.
It lasts as long as the token says, or 30 days when the token gives no lifetime.
Once it runs out, T3 Code refuses jbus and jbus launches nothing.

## The reminder

jbus reminds you with a `sign-in` event, which is a `user` event of the machine and not of a project.
It is posted once to the top-level webhook, or to the first project's own webhook when there is no top-level pair, and kept in the first project's `jbus events`.
The days are counted by the calendar of your zone, to the day the sign-in runs out:

| When | The line |
|---|---|
| The first pass 7 days out or fewer | `sign-in: jbus's T3 sign-in expires <YYYY-MM-DD HH:MM zone>, 7 days left: run jbus t3 login` |
| The first pass of each day from 3 days out, the last day included | The same line, with the days left |
| The first pass after it ran out | `sign-in: jbus's T3 sign-in expired <YYYY-MM-DD HH:MM zone>, no days left: run jbus t3 login` |
| The first pass after `jbus t3 login` stored a token that runs out later | `sign-in: jbus's T3 sign-in was renewed, and now expires <YYYY-MM-DD HH:MM zone>` |

A pass sends the line for the mark it is in, and none for a mark already behind it.
The renewal starts the count over for the new expiry.
`~/.local/state/jbus/sign-in.json` keeps the expiry jbus saw last and the marks it has sent for it, so a project added or moved in the config sends nothing again.
`sign_in_reminder` in `jbus status` names the webhook the reminder goes to and the days still ahead, or says `none: no top-level webhook, and <project> has none of its own`.

## The quiet lines

From `warn_days` days before the sign-in runs out (5 by default), the first pass of each day records `condition <project>: T3 sign-in expires <YYYY-MM-DD> <zone>, run jbus t3 login` and raises it on the desktop.
Each project's `sign_in` in `jbus status` says the same, and `token_expires` gives the time.

Once T3 Code refuses the token, each pass prints `wait <project>: T3 Code could not be asked (<why>)`, launches nothing and watches no thread.
The first such pass of each day records `condition <project>: T3 Code could not be asked`.
`jinstall --doctor` prints `old optional jbus sign-in <path> -> expired <date>, run jbus t3 login`.

[A T3 Code sign-in ran out](../troubleshooting/a-t3-code-sign-in-ran-out.md) says how to sign in again.
