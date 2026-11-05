# A T3 Code sign-in ran out

`jbus` does not renew its sign-in to T3 Code.
When the sign-in runs out, `jbus` cannot ask T3 Code, so it launches nothing.

You see one of these:

- A `sign-in` alert on the desk and in the infra home, as the end comes near and once after it.
  [The reminder](../jbus/the-sign-in.md#the-reminder) has each of its lines and the day it comes.
- `T3 sign-in expires <YYYY-MM-DD> <zone>, run jbus t3 login`, in each project's `sign_in` field of the status file that `jbus status` prints, from `warn_days` (5) days before the end.
- `wait <project>: T3 Code could not be asked (<why>)`, from each pass after the end.
- `old hard jbus sign-in <path> -> expired <date>, run jbus t3 login`, from `jinstall --doctor`.
  The need is `optional` only while jbus's config has no project.

Sign in again:

1. Run `jbus t3 login`.
   It prints a link to the approval page of the T3 Code server.
2. Run `t3 auth pairing create`, and enter the code it prints on that page.
   Approve with full access, because `jbus` launches threads.
3. Run `jinstall --doctor`.
   Its line is `ok hard jbus sign-in <path>`.

The next pass ends the sign-in alert and launches again.
[The sign-in](../jbus/the-sign-in.md) has when each line comes.
