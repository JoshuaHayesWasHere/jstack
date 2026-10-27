# Set up jbus

These steps take a machine from a release install to a jbus that launches the work you approve.
You need T3 Code running on this machine, and `gh` signed in to GitHub.
The commands are on your `PATH` after the install, as `jinstall` and `jbus`.

## 1. Let the setup write the config

Run the setup.
The release's `install.sh` runs it for you, and a second run writes nothing:

```sh
jinstall --setup
```

Among its lines you see these two:

```text
done jbus config /home/you/.config/jbus/config.toml
missing optional jbus sign-in /home/you/.config/jbus/t3.json -> jbus t3 login
```

The config it wrote has the T3 Code server and no project, and it launches nothing:

```toml
# Written once by install.sh --setup. Edit it: setup never writes over it.
server = "http://127.0.0.1:3773"
dispatch = false
```

The setup also linked jbus's systemd units and turned on `jbus.timer`, so a pass runs every minute from now on.
With `dispatch = false` and no project, a pass does nothing.
If T3 Code listens on another address, `jq -r .origin ~/.t3/userdata/server-runtime.json` prints it.
Put that address in `server`.

## 2. Sign jbus in to T3 Code

Run the sign-in:

```sh
jbus t3 login
```

It prints a link to the T3 Code server's approval page and waits for you, 600 seconds at most:

```text
approve jbus in the browser, with a code from `t3 auth pairing create`:
http://127.0.0.1:3773/...
```

1. Run `t3 auth pairing create` in another shell.
   T3 Code installs `t3` as `~/.t3/bin/t3`.
2. Open the link, and enter the code that `t3 auth pairing create` printed.
3. Approve with full access, since jbus launches threads.

The sign-in then prints `signed in: the token is in /home/you/.config/jbus/t3.json`.
The token lasts as long as T3 Code gave it, and jbus reminds you before it runs out ([The sign-in](the-sign-in.md)).

## 3. Add your first project

A project is one repo that jbus looks after, tied to its T3 Code project.
Pick one of the two ways.

### With a thread: `/new-home`

In any T3 Code thread, type the command with the repo's path:

```text
/new-home ~/code/app
```

The skill finds the repo's T3 Code project, makes one when there is none, and adds the project to jbus's config.
Its third line says so: `3 jbus project: done, one [[project]] table, ...`.

### From a shell: `jbus project add`

You need the id of the repo's T3 Code project.
To find it in the app, open a thread in that project and ask it for the project's id.
The thread reads the id with T3 Code's `t3_project_list` tool.
The `t3` command has no way to list projects.
As a fallback, read T3 Code's own store from a shell.
This command does not change the store, and T3 Code may change its layout in a later version:

```sh
sqlite3 -readonly ~/.t3/userdata/statev2.sqlite "select project_id, workspace_root from projection_projects where deleted_at is null"
```

Each line is a project id and the folder of its repo.
If your repo is not there, add it to T3 Code first, in the app or with `t3 project add <path>`.
Then add the project, named for the repo's folder:

```sh
jbus project add app --checkout ~/code/app --project-id <the id>
```

It prints one line:

```text
added: one [[project]] table, the file as it was is /home/you/.config/jbus/config.toml.<time>.bak: the next pass works it, restart no unit
```

[Add a project](add-a-project.md) lists what it refuses.

### Check the project

Run a test launch:

```sh
jbus t3 launch-test
```

It starts one thread, titled `jbus: launch test`, in the project, and prints the thread's id, such as `mcp:3f1c...`.
The thread runs in a new worktree on a branch `jbus-launch-test-<time>` from `origin/main`, and is told to say hello and stop.
Archive the thread in T3 Code once it has answered, and delete the branch.

## 4. Turn dispatch on

Edit `~/.config/jbus/config.toml`, and change `dispatch = false` to:

```toml
dispatch = true
```

The next pass reads the file, so you restart nothing.
[Configuration](../../../jinstall/docs/configuration.md#jbus) has every other key of the file.

## 5. Check that it works

Run one pass by hand:

```sh
jbus poll
```

Before step 4 it printed `dispatch is off in the config: nothing is launched`, and now it does not.
jbus sends its wakes to each project's home thread through T3 Code ([Where wakes go](events-and-wakes.md#where-wakes-go)).
The relay and a Chef are optional add-ons.

Then read what the last pass left:

```sh
jbus status
```

`last_pass` is this minute, `token_expires` is when the sign-in runs out, and the project's `last_error` is empty.
`systemctl --user list-timers jbus.timer` shows when the timer runs the next pass.

jbus now launches the rows you approve.
To give it the first one, follow [Approve a row](the-queue.md#approve-a-row).
jbus tells you what waits on you in the project's home thread, on the desktop with `notify-send`, and in `jbus status`.

## Stop jbus

To stop every launch, run `touch ~/.local/state/jbus/stop`.
The passes go on, and jbus still merges, reads and sends.
To stop the passes, run `systemctl --user disable --now jbus.timer`.
[The units](the-units.md) lists each unit the setup linked.
