# Windows through WSL2

jstack runs on Windows inside WSL2, as on any Linux machine.
T3 Code runs on Windows and starts its server, its agents and its terminals inside a WSL distro.
jstack, Claude Code and the programs jstack needs are installed in that distro, and nothing of jstack runs on the Windows side.
Native Windows is not supported.

## 1. A distro with systemd on

Install WSL2 and a distro from PowerShell, Ubuntu for example:

```powershell
wsl --install -d Ubuntu
```

jstack's background jobs are systemd `--user` units, so turn systemd on in the distro.
In the distro, put these lines in `/etc/wsl.conf`:

```ini
[boot]
systemd=true
```

Then restart WSL from PowerShell with `wsl --shutdown`, and open the distro again.
`systemctl --user status` now answers.
Run `loginctl enable-linger "$USER"` in the distro, so the units run while no terminal is open.

## 2. T3 Code on Windows, with a WSL connection

Install the T3 Code desktop app on Windows, stable `0.1.2` or newer or the nightly build, as the [Requirements](../../../README.md#requirements) say.
`winget install T3Tools.T3Code` installs the stable build.
For the nightly, take the newest release titled "T3 Code Nightly" from [its releases](https://github.com/pingdotgg/t3code/releases), its `T3-Code-<version>-x64.exe`.
The doctor cannot see which build the app is, since it reads the `t3` command of step 4, so keep the app and that command on the same channel.
Open it, then open **Settings → Connections** and choose your distro.
T3 Code installs its own server runtime in the distro, under `~/.t3/wsl-runtime`, and runs your projects and agents there.

Keep your repos in the distro's file system, under your Linux home, and not under `/mnt/c`.

## 3. Claude Code and the other programs in the distro

Install Claude Code inside the distro, with the Linux steps of [Set up Claude Code](https://code.claude.com/docs/en/setup), and sign in there.
Install `uv`, `git`, `jq` and `gh` in the distro too, and run `gh auth login` there.
[Where to get each program](troubleshooting/the-platform-and-the-programs.md#where-to-get-each-program) links each one's install page.

## 4. The `t3` command in the distro

The doctor's `t3` need runs `t3 --version`, from `~/.t3/bin/t3` or from `PATH`, in the distro.
The desktop app does not put a `t3` there.
It writes its `t3` launcher only on the Windows side, as `%USERPROFILE%\.t3\bin\t3.cmd`.
Its runtime in the distro sits under `~/.t3/wsl-runtime/<id>/`, which is neither of those places.

Install the `t3` command in the distro with T3 Code's own installer, on the channel of your app, here the nightly:

```sh
curl -fsSL https://t3.codes/install.sh | T3CODE_CHANNEL=nightly sh
```

It puts `t3` in `~/.local/bin`, which `uv` also needs on `PATH`.
Run `t3 update` in the distro after each update of the app, so the version the doctor reads keeps up with the app.

## 5. jstack, the Linux way

Inside the distro, follow the [Quickstart](../../../README.md#quickstart).
`jinstall --doctor` should end `doctor: ok`.

## Where T3 Code keeps its files

The server in the distro runs with its own home, `~/.t3` in the distro, and not the Windows `%USERPROFILE%\.t3`.
Its settings, with the provider instances the doctor reads, are `~/.t3/userdata/settings.json` in the distro.
Its worktrees are under `~/.t3/worktrees` in the distro.
So the doctor and the threads read the same files, and the Windows `%USERPROFILE%\.t3` holds only the desktop app's own state and its `t3.cmd`.

These facts come from T3 Code's source at commit `51273020db32`:

- `apps/desktop/src/backend/DesktopBackendConfiguration.ts`: the WSL backend starts with no `t3Home` and with `T3CODE_HOME` taken out of its environment, "so the Linux backend uses its own home dir instead of the Windows-side baseDir".
- `apps/server/src/os-jank.ts`, `resolveBaseDir`: with no home given, the server's home is `.t3` in the home directory.
- `apps/server/src/config.ts`, `deriveServerPaths`: `settings.json` is in `userdata` under that home, and the worktrees are in `worktrees`.
- `apps/desktop/src/app/DesktopCliShim.ts`, `launcherPath`: the launcher is `bin/t3.cmd` under the Windows app's home.
- `apps/desktop/src/wsl/DesktopWslEnvironment.ts`: the runtime in the distro is installed under `$HOME/.t3/wsl-runtime`.
