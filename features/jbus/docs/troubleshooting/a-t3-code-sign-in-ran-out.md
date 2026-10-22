# A T3 Code sign-in ran out

`jbus` does not renew its sign-in to T3 Code. When the sign-in runs out, `jbus` cannot ask T3 Code, so it launches nothing.

You see one of these:

- `gate <project>: T3 sign-in expires <YYYY-MM-DD> <zone>, run jbus t3 login`, from 5 days before the end.
- `gate <project>: T3 Code could not be asked`, once a day after the end.
- `old optional jbus sign-in <path> -> expired <date>, run jbus t3 login`, from the doctor.

Sign in again:

1. Run `jbus t3 login`. It opens the approval page of the T3 Code server.
2. Run `t3 auth pairing create` and enter the code it prints on that page. Approve with full access, because `jbus` launches threads.
3. Run `jbus t3 launch-test`. It starts one thread and prints its id.
