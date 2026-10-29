# The sign-in

`jbus t3 login` signs jbus in to the T3 Code server and keeps the token in `~/.config/jbus/t3.json`, mode 600.
jbus does not renew the sign-in.
It lasts as long as the token says, or 30 days when the token gives no lifetime.
Once it runs out, T3 Code refuses jbus and jbus launches nothing.

## The reminder

jbus reminds you with a `sign-in` alert, an open item of the machine's and not of a project.
It goes to the desk and to the infra home ([Who an item is for](events-and-wakes.md#who-an-item-is-for)), and is logged in the infra project's `jbus events`.
jbus counts the days by the calendar of your zone, up to the day the sign-in runs out:

| When | The line |
|---|---|
| From 7 days out, until 3 days out | `sign-in: jbus's T3 sign-in expires <YYYY-MM-DD HH:MM zone>, at most a week left: run jbus t3 login` |
| Each day from 3 days out, the last day included | `sign-in: jbus's T3 sign-in expires <YYYY-MM-DD HH:MM zone>, <n> days left: run jbus t3 login` |
| After it ran out | `sign-in: jbus's T3 sign-in expired <YYYY-MM-DD HH:MM zone>, no days left: run jbus t3 login` |

The alert is one item, `sign-in`, and each row is a new line of it, so the infra home hears each line once.
A home is told the item again only when its line changed.
`jbus t3 login` with a token that runs out more than 7 days later ends the alert.
`sign_in_reminder` in `jbus status` names where the reminder goes and the days still ahead, or says `none: no sign-in is stored`.

## The quiet lines

From `warn_days` days before the sign-in runs out (5 by default), the first pass of each day records `condition <project>: T3 sign-in expires <YYYY-MM-DD> <zone>, run jbus t3 login` and shows it as a desktop notification.
On macOS, which has no `notify-send`, it shows no desktop notification.
Each project's `sign_in` in `jbus status` says the same, and `token_expires` gives the time.

Once T3 Code refuses the token, each pass prints `wait <project>: T3 Code could not be asked (<why>)`, launches nothing and watches no thread.
The first such pass of each day records `condition <project>: T3 Code could not be asked`.
`jinstall --doctor` prints `old optional jbus sign-in <path> -> expired <date>, run jbus t3 login`.

[A T3 Code sign-in ran out](../troubleshooting/a-t3-code-sign-in-ran-out.md) says how to sign in again.
