"""A release: the wheel that `uv build` makes from this checkout. The tests install it with
`uv tool install`, in a directory with no checkout above it, and run its `jinstall` under a
HOME of the test's own. That `jinstall` assembles each harness's layout from the source tree
that the wheel carries, as `install.sh` does from a checkout (`test_install`)."""

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from jbus.launchd import label
from jinstall import launchd, layout
from jinstall.harnesses import HARNESSES
from test_install import (
    INSTALL,
    MAC,
    ROOTS,
    SCRUBBED,
    SYSTEMCTL,
    UNITS_DIR,
    laid,
    line_for,
)
from testing.paths import REPO

PACKAGES = ("jbriefs", "jbus", "jdrift", "jgauge", "jinstall", "jleak", "jmerge", "jpack")
PACKAGES += ("jroles", "jsettings")


def no_checkout_above(path):
    return not any((up / "pyproject.toml").is_file() for up in path.parents)


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    built = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out), str(REPO)],
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stderr
    (found,) = out.glob("*.whl")
    return found


class Release:
    """A release: the wheel that `uv build` makes from this checkout, as
    `uv tool install <wheel>` leaves it. It sits in a tool directory of its own under the
    test's temporary directory. So no checkout of jstack is on any parent path of the tool,
    of its source, or of the HOME it runs under."""

    def __init__(self, root, wheel):
        self.root, self.tools, self.bin = root, root / "tools", root / "bin"
        env = {k: v for k, v in os.environ.items() if not k.startswith(SCRUBBED)}
        self.uv_env = env | {"UV_TOOL_DIR": str(self.tools), "UV_TOOL_BIN_DIR": str(self.bin)}
        done = subprocess.run(
            ["uv", "tool", "install", str(wheel)], env=self.uv_env, capture_output=True, text=True
        )
        assert done.returncode == 0, done.stderr
        self.source = self.tools / "jstack" / "share" / "jstack"
        assert no_checkout_above(self.source)

    def run(self, home, *args, **env):
        home.mkdir(exist_ok=True)
        path = f"{self.bin}:{os.environ['PATH']}"
        return subprocess.run(
            [str(self.bin / args[0]), *args[1:]],
            env=self.uv_env | {"HOME": str(home), "PATH": path} | env,
            cwd=home,
            capture_output=True,
            text=True,
        )


@pytest.fixture(scope="module")
def released(wheel, tmp_path_factory):
    return Release(tmp_path_factory.mktemp("release"), wheel)


def test_the_wheel_carries_every_package_the_source_of_each_layout_and_the_jinstall_command(
    wheel,
):
    with zipfile.ZipFile(wheel) as built:
        names = set(built.namelist())
        (points,) = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        scripts = built.read(points).decode()
    for package in PACKAGES:
        assert f"{package}/__init__.py" in names, package
    data = next(name.split("/")[0] for name in names if ".data/" in name)
    shared = f"{data}/data/share/jstack"
    sources = {
        entry.source.relative_to(REPO).as_posix()
        for harness in HARNESSES
        for entry in layout.assemble(REPO, harness).entries.values()
        if isinstance(entry, layout.Linked) and entry.source != REPO
    }
    carried = {f"{shared}/{path}" for path in (*sources, "skills.json", "plugin.json")}
    assert carried <= names, sorted(carried - names)[:5]
    assert f"{shared}/features/jpack/docs/context.md" in names
    inner = [name for name in names if name.startswith(f"{shared}/")]
    left_out = r"/(src|tests|__pycache__)/|/features/[^/]+/evals/"
    assert not [name for name in inner if re.search(left_out, name)]
    assert not [name for name in names if "harness/" in name or "claude-code/" in name]
    assert "jinstall = jinstall.cli:main" in scripts.splitlines()


def test_with_no_checkout_above_it_a_release_reads_its_playbooks_and_skills_from_its_source(
    released, tmp_path
):
    home = tmp_path / "home"
    asked = tmp_path / "req.md"
    asked.write_text("Playbook: investigation\nSkills: tdd\n")
    opened = released.run(home, "jbus", "playbook", "scout", str(asked))
    assert opened.returncode == 0, opened.stderr
    assert opened.stdout.splitlines()[0] == str(
        released.source / "features" / "scout" / "playbooks" / "investigation.md"
    )
    loaded = released.run(home, "jbriefs", "--skills", str(asked))
    assert loaded.returncode == 0, loaded.stderr
    assert loaded.stdout.splitlines()[0].startswith("loaded: tdd")
    assert "==> features/tdd/SKILL.md <==" in loaded.stdout


def made_from(home):
    """The tree the install made jbus's timer from: the one its unit links into, or on a Mac the
    one its agent's plist names."""
    if MAC:
        return Path(
            launchd.made_from((home / UNITS_DIR / f"{label('jbus.timer')}.plist").read_text())
        )
    link = Path(os.readlink(home / UNITS_DIR / "jbus.timer"))
    assert link.relative_to(link.parents[3]) == Path("features", "jbus", "units", "jbus.timer")
    return link.parents[3]


def stand_ins(tmp_path):
    """A directory with the fake systemctl, for a release's commands to find first on PATH."""
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    (stub / "systemctl").symlink_to(SYSTEMCTL)
    return {"PATH": f"{stub}:{os.environ['PATH']}", "FAKE_SYSTEMCTL_LOG": str(tmp_path / "log")}


def test_a_release_with_jbus_set_up_links_its_units_into_its_source(released, tmp_path):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    (home / ".config" / "jbus").mkdir(parents=True)
    (home / ".config" / "jbus" / "config.toml").write_text("")
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".local" / "bin" / "jbus").symlink_to(released.bin / "jbus")
    put = released.run(home, "jinstall", **env)
    assert put.stdout.splitlines()[-1] == f"ok optional units {home / UNITS_DIR}"
    assert made_from(home) == released.source


def test_a_release_whose_version_is_not_its_plugins_is_told_so_and_not_put_over(released, tmp_path):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    plugin = json.loads((released.source / "plugin.json").read_text())
    metadata = next(released.tools.glob("jstack/lib/python*/site-packages/jstack-*.dist-info"))
    said = (metadata / "METADATA").read_text()
    (metadata / "METADATA").write_text(said.replace(f"Version: {plugin['version']}", "Version: 9"))
    try:
        checked = released.run(home, "jinstall", "--check", **env)
    finally:
        (metadata / "METADATA").write_text(said)
    assert checked.returncode == 1
    assert line_for(checked.stdout.splitlines(), "commands") == [
        f"old hard commands jstack -> tool jstack is 9, and its plugin is {plugin['version']}"
    ]


def test_uninstall_from_a_release_removes_what_it_put_and_keeps_the_tool_it_runs_from(
    released, tmp_path
):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    assert released.run(home, "jinstall", **env).returncode == 0
    gone = released.run(home, "jinstall", "--uninstall", **env)
    assert gone.returncode == 0, gone.stderr
    assert "kept commands jstack -> the release this jinstall runs from" in gone.stdout
    assert not any((home / root).exists() for root in ROOTS)
    assert (released.bin / "jinstall").exists()


def test_a_releases_outbound_hook_checks_a_push_on_the_tools_own_python_with_no_python_on_path(
    released, tmp_path
):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    assert released.run(home, "jinstall", **env).returncode == 0
    narrow = tmp_path / "narrow"
    narrow.mkdir()
    for program in ("dirname", "realpath", "cat"):
        (narrow / program).symlink_to(shutil.which(program))
    hook = laid(home) / "hooks" / "outbound-command.sh"

    def told(command):
        said = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return subprocess.run(
            ["/bin/sh", str(hook)],
            input=said,
            env={"HOME": str(home), "PATH": str(narrow)},
            capture_output=True,
            text=True,
        )

    clean = told("git push origin a-branch")
    assert (clean.returncode, clean.stderr) == (0, "")
    leaked = told(f"gh pr create --body 'see {home}/notes'")
    assert leaked.returncode == 2
    assert "home-path" in leaked.stderr


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    """A release's assets, which `make dist` writes into a directory of the test's own."""
    out = tmp_path_factory.mktemp("assets") / "dist"
    made = subprocess.run(
        ["make", "-s", "-C", str(REPO), "dist", f"DIST={out}"], capture_output=True, text=True
    )
    assert made.returncode == 0, made.stderr
    return out


def a_new_user(tmp_path):
    """A HOME with no uv and no checkout, the env that `curl ... | sh` runs install.sh in: a
    PATH of the few programs it needs, then the HOME's own bin, and a stand-in uv installer
    that links this machine's uv there."""
    home, tools = tmp_path / "home", tmp_path / "tools"
    bin = home / ".local" / "bin"
    home.mkdir()
    narrow = tmp_path / "narrow"
    narrow.mkdir()
    for program in (
        "sh",
        "curl",
        "dirname",
        "mkdir",
        "ln",
        "cat",
        "readlink",
        "git",
        "basename",
        "sed",
        "uname",
    ):
        (narrow / program).symlink_to(shutil.which(program))
    (narrow / "systemctl").symlink_to(SYSTEMCTL)
    installer = tmp_path / "uv-installer.sh"
    installer.write_text(
        f'mkdir -p "$HOME/.local/bin" && ln -s {shutil.which("uv")} "$HOME/.local/bin/uv"\n'
    )
    cache = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True).stdout.strip()
    env = {
        "HOME": str(home),
        "PATH": f"{bin}:{narrow}",
        "UV_TOOL_DIR": str(tools),
        "UV_TOOL_BIN_DIR": str(bin),
        "UV_CACHE_DIR": cache,
        "UV_PYTHON": os.path.realpath(sys.executable),
        "FAKE_SYSTEMCTL_LOG": str(tmp_path / "systemctl.log"),
        "JSTACK_UV_INSTALLER": installer.as_uri(),
    }
    return home, tools, env


def test_install_sh_piped_to_sh_with_no_checkout_and_no_release_installs_main_from_git(tmp_path):
    """Its origin is a commit of HEAD's tree in a repo of its own: CI's checkout is shallow, and
    a fetch from a shallow repo into another makes no branch.

    The second install fetches into a git db that already holds a pack. uv fetches into its git
    db, then clones the db at once, and the fetch would start `git maintenance run --auto
    --detach`, which can repack the db and rename a `.tmp-<pid>-pack` file the clone is copying.
    install.sh runs that fetch with no auto maintenance, and keeps the git config the user set in
    the env, as the `insteadOf` here shows."""
    origin = tmp_path / "jstack"
    origin.mkdir()
    tree = subprocess.run(
        ["git", "-C", str(REPO), "archive", "HEAD"], capture_output=True, check=True
    )
    subprocess.run(["tar", "-x", "-C", str(origin)], input=tree.stdout, check=True)
    git = [
        "git",
        "-C",
        str(origin),
        "-c",
        "user.name=jstack",
        "-c",
        "user.email=jstack@example.com",
    ]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "--no-verify", "-m", "main"], check=True)
    home, tools, env = a_new_user(tmp_path)
    env |= {
        "JSTACK_GIT_URL": "git+https://jstack.invalid/jstack@main",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{origin.as_uri()}.insteadOf",
        "GIT_CONFIG_VALUE_0": "https://jstack.invalid/jstack",
    }
    assert "\nversion=\n" in INSTALL.read_text()

    setup = subprocess.run(
        ["sh"], input=INSTALL.read_text(), env=env, cwd=home, capture_output=True, text=True
    )

    assert os.path.islink(home / ".local" / "bin" / "uv"), setup.stdout + setup.stderr
    said = setup.stdout.splitlines()
    folded = [line for line in said if re.fullmatch(r"done skills claude-code: \d+ links", line)]
    assert folded, setup.stdout + setup.stderr
    assert said[-2:-1] == [f"done units {home / UNITS_DIR}"]
    assert said[-1].startswith("setup: ") and "needs you: " in said[-1]
    assert made_from(home) == tools / "jstack" / "share" / "jstack"
    loose = tmp_path / "install.sh"
    shutil.copy(INSTALL, loose)
    trace = tmp_path / "git-trace.log"
    env["GIT_TRACE"] = str(trace)
    checked = subprocess.run(
        ["sh", str(loose), "--check"], env=env, cwd=tmp_path, capture_output=True, text=True
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert all(line.startswith("ok ") for line in checked.stdout.splitlines()), checked.stdout
    traced = trace.read_text()
    assert " fetch " in traced and " init" not in traced
    assert not re.search(r"\bgit (maintenance|repack|gc)\b", traced), traced
