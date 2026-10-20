# Set up jbus

1. Write the config, `~/.config/jbus/config.toml`, mode 600, as [Configuration](../configuration.md#jbus) shows. jbus refuses to start when group or others can read it, or the token beside it.
2. Sign in once with `jbus t3 login`. It registers jbus with the T3 Code server and opens its approval page. Approve it there with a code from `t3 auth pairing create`, with full access, because jbus launches threads. jbus keeps the token in `~/.config/jbus/t3.json`, mode 600. `jbus t3 launch-test` then starts one thread and prints its id.
3. Run `sh <checkout>/install.sh` again. With the config there, it links every unit of `templates/` into `~/.config/systemd/user/`, reloads systemd and enables `jbus.timer`, `jbus-stale.timer`, `jbus-snapshot.timer` and `jbus-ci.timer`. `jbus.timer` runs a pass every minute (`OnUnitActiveSec=1min`), through `jbus.service` and `jbus-failed.service`. `jbus-stale.timer` looks every 15 minutes for a pass that ended in the last 2 hours, from 2 hours after it starts ([When jbus fails](when-jbus-fails.md)). `jbus-snapshot.timer` backs up the homes' state ([Back up the homes' state](back-up-the-homes-state.md)). `jbus-ci.timer` writes the week's CI report ([Measure the CI](measure-the-ci.md)). Each unit's `Documentation=` names its page of these docs by where its template is (`%Y`), so `systemctl --user show -p Documentation <unit>` leads here. A unit copied in place of the link loses that, and `install.sh --check` reports the copy as old.

[Configuration](../configuration.md#jbus) has every key of the file and its default. `dispatch = false` launches nothing, and `max_running` is how many crewmates may be out at once, 24 when the file does not set it.

jbus does not renew the sign-in. It lasts as long as the token says, or 30 days when the token gives no lifetime. Once it runs out jbus launches nothing, so jbus reminds you, with a `sign-in` event for you, posted once for the machine to the top-level webhook (to the first project's own webhook when there is no top-level pair) and kept in the first project's `jbus events`. The days are counted by the calendar of your zone, to the day the sign-in runs out:

- 7 days out or fewer, on the first pass: `sign-in: jbus's T3 sign-in expires <YYYY-MM-DD HH:MM zone>, 7 days left: run jbus t3 login`;
- from 3 days out, on the first pass of each day, the day it runs out included, the same line with the days left;
- once it has run out: `sign-in: jbus's T3 sign-in expired <YYYY-MM-DD HH:MM zone>, no days left: run jbus t3 login`;
- after `jbus t3 login` stores a token that runs out later, once: `sign-in: jbus's T3 sign-in was renewed, and now expires <YYYY-MM-DD HH:MM zone>`, and the count starts over for the new expiry.

The expiry jbus saw last, and which of these it has said of it, are in `~/.local/state/jbus/sign-in.json`, so a project added or moved in the config says nothing again. `sign_in_reminder` in `jbus status` names the webhook it goes to and the days still ahead. Apart from the reminder, from `warn_days` days before the sign-in runs out the first pass of each day records a quiet `condition <project>: T3 sign-in expires <YYYY-MM-DD> <zone>, run jbus t3 login` and raises it on the desktop, and each project's `sign_in` in `jbus status` says the same. After that a pass sends `gate <project>: T3 Code could not be asked` once a day until you run `jbus t3 login` again.

To stop every launch, run `touch ~/.local/state/jbus/stop`. The passes go on, and jbus still merges, reads and sends. To stop the passes, run `systemctl --user disable --now jbus.timer`.
