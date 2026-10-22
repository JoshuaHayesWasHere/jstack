"""A release: the wheel that `uv build` makes from this checkout. The tests install it with
`uv tool install`, in a directory with no checkout above it, and run its `jinstall` under a
HOME of the test's own. That `jinstall` assembles each harness's layout from the source tree
that the wheel carries, as `install.sh` does from a checkout (`test_install`)."""

import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import tomllib
import zipfile

import pytest

from jinstall import layout
from jinstall.harnesses import HARNESSES
from test_install import (
    INSTALL,
    ROOTS,
    SCRUBBED,
    SYSTEMCTL,
    hook_parts,
    laid,
    layouts,
    line_for,
    lines_of,
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


def release_parts(home, source):
    """The line of each part that a release puts, without the leading state word. Each
    layout's line comes first, then the rest."""
    settings = home / ".claude" / "settings.json"
    names = layout.skills(source)
    return [
        *layouts(home),
        *(f"hard {home / root / name}" for root in ROOTS for name in names),
        f"optional patterns {home / '.config' / 'jstack' / 'outbound.toml'}",
        *hook_parts(home, source),
        "hard commands jstack",
        f"optional statusline {settings}",
    ]


def stand_ins(tmp_path):
    """A directory with the fake systemctl, for a release's commands to find first on PATH."""
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    (stub / "systemctl").symlink_to(SYSTEMCTL)
    return {"PATH": f"{stub}:{os.environ['PATH']}", "FAKE_SYSTEMCTL_LOG": str(tmp_path / "log")}


def test_a_release_links_every_skill_hook_and_status_line_into_its_layouts_and_checks_ok(
    released, tmp_path
):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    put = released.run(home, "jinstall", **env)
    assert (put.returncode, put.stderr) == (0, "")
    assert put.stdout.splitlines() == lines_of("ok", release_parts(home, released.source), home)
    checked = released.run(home, "jinstall", "--check", **env)
    assert (checked.returncode, checked.stdout) == (0, put.stdout)
    names = layout.skills(released.source)
    for harness in HARNESSES:
        links = sorted((home / harness.root).iterdir())
        assert [link.name for link in links] == names
        for link in links:
            assert os.readlink(link) == str(laid(home, harness.name) / "skills" / link.name)
            assert os.path.realpath(link / "SKILL.md").startswith(f"{released.source}/")
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"]
        for groups in settings["hooks"].values()
        for group in groups
        for hook in group["hooks"]
    ]
    assert all(f"sh '{laid(home)}/hooks/" in command for command in commands), commands
    assert settings["statusLine"]["command"] == f"sh '{laid(home) / 'hooks' / 'limits.sh'}'"
    assert not line_for(put.stdout.splitlines(), "pre-push")


def test_a_release_with_jbus_set_up_links_its_units_into_its_source(released, tmp_path):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    (home / ".config" / "jbus").mkdir(parents=True)
    (home / ".config" / "jbus" / "config.toml").write_text("")
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".local" / "bin" / "jbus").symlink_to(released.bin / "jbus")
    put = released.run(home, "jinstall", **env)
    assert put.stdout.splitlines()[-1] == f"ok optional units {home / '.config/systemd/user'}"
    unit = home / ".config" / "systemd" / "user" / "jbus.timer"
    assert os.readlink(unit) == str(released.source / "features" / "jbus" / "units" / "jbus.timer")


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
    for program in ("dirname", "readlink", "cat"):
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


@pytest.fixture
def served(tmp_path):
    """A web server for a directory, in place of GitHub's release downloads."""
    root = tmp_path / "served"
    root.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield root, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_a_releases_install_sh_piped_to_sh_with_no_checkout_and_no_uv_installs_and_sets_up(
    dist, served, tmp_path
):
    root, url = served
    version = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]
    for asset in dist.iterdir():
        shutil.copy(asset, root / asset.name)
    (root / "uv-installer.sh").write_text(
        f'mkdir -p "$HOME/.local/bin" && ln -s {shutil.which("uv")} "$HOME/.local/bin/uv"\n'
    )
    home, tools = tmp_path / "home", tmp_path / "tools"
    bin = home / ".local" / "bin"
    home.mkdir()
    narrow = tmp_path / "narrow"
    narrow.mkdir()
    for program in ("sh", "curl", "dirname", "mkdir", "ln", "cat", "readlink"):
        (narrow / program).symlink_to(shutil.which(program))
    (narrow / "systemctl").symlink_to(SYSTEMCTL)
    cache = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True).stdout.strip()
    env = {
        "HOME": str(home),
        "PATH": f"{bin}:{narrow}",
        "UV_TOOL_DIR": str(tools),
        "UV_TOOL_BIN_DIR": str(bin),
        "UV_CACHE_DIR": cache,
        "UV_PYTHON": os.path.realpath(sys.executable),
        "FAKE_SYSTEMCTL_LOG": str(tmp_path / "systemctl.log"),
        "JSTACK_RELEASE_URL": url,
        "JSTACK_UV_INSTALLER": f"{url}/uv-installer.sh",
    }
    fetched = subprocess.run(
        ["curl", "-fsSL", f"{url}/install.sh"], capture_output=True, text=True, check=True
    ).stdout
    assert f"\nversion={version}\n" in fetched
    setup = subprocess.run(["sh"], input=fetched, env=env, cwd=home, capture_output=True, text=True)
    assert os.path.islink(home / ".local" / "bin" / "uv"), setup.stdout + setup.stderr
    said = setup.stdout.splitlines()
    source = tools / "jstack" / "share" / "jstack"
    assert f"done {home / '.claude' / 'skills' / 'crew'}" in said, setup.stdout + setup.stderr
    assert "already commands jstack" in said
    checked = subprocess.run(
        [str(bin / "jinstall"), "--check"], env=env, cwd=home, capture_output=True, text=True
    )
    assert checked.returncode == 0, checked.stdout
    units = f"optional units {home / '.config' / 'systemd' / 'user'}"
    parts = [*release_parts(home, source), units]
    assert checked.stdout.splitlines() == lines_of("ok", parts, home)
    assert os.readlink(home / ".config/systemd/user/jbus.timer") == str(
        source / "features/jbus/units/jbus.timer"
    )
    for harness in HARNESSES:
        for link in (home / harness.root).iterdir():
            assert os.readlink(link) == str(laid(home, harness.name) / "skills" / link.name)
            assert os.path.realpath(link / "SKILL.md").startswith(f"{source}/")


def test_install_sh_run_from_no_checkout_and_no_release_says_how_to_get_one(tmp_path):
    loose = tmp_path / "install.sh"
    shutil.copy(INSTALL, loose)
    for argv, kwargs in (
        (["sh", str(loose)], {}),
        (["sh"], {"input": INSTALL.read_text()}),
    ):
        ran = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, **kwargs)
        assert ran.returncode == 1
        assert ran.stdout.startswith("missing hard a checkout of jstack around ")
        assert "releases/latest/download/install.sh | sh" in ran.stdout
