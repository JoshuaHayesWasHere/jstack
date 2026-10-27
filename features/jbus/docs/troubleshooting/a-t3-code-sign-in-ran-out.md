# A T3 Code sign-in ran out

`jbus` does not renew its sign-in to T3 Code.
When the sign-in runs out, `jbus` cannot ask T3 Code, so it launches nothing.

You see one of these:

- `sign-in: jbus's T3 sign-in expires <YYYY-MM-DD HH:MM zone>, <n> days left: run jbus t3 login`, sent to the first project's home thread from 7 days before the end.
- `condition <project>: T3 sign-in expires <YYYY-MM-DD> <zone>, run jbus t3 login`, on the desktop from 5 days before the end.
- `sign-in: jbus's T3 sign-in expired <YYYY-MM-DD HH:MM zone>, no days left: run jbus t3 login`, once after the end.
- `wait <project>: T3 Code could not be asked (<why>)`, from each pass after the end.
- `old optional jbus sign-in <path> -> expired <date>, run jbus t3 login`, from `jinstall --doctor`.

Sign in again:

1. Run `jbus t3 login`.
   It prints a link to the approval page of the T3 Code server.
2. Run `t3 auth pairing create`, and enter the code it prints on that page.
   Approve with full access, because `jbus` launches threads.
3. Run `jinstall --doctor`.
   Its line is `ok optional jbus sign-in <path>`.

The next pass sends `sign-in: jbus's T3 sign-in was renewed, and now expires <YYYY-MM-DD HH:MM zone>` and launches again.
[The sign-in](../jbus/the-sign-in.md) has when each line comes.
