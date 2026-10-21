"""The machine a verb acts on, and every effect the install has on it.

A kind writes only through Machine, which is what lets this file hold four rules:
- A directory or JSON file the install creates is in the record before it exists, but for a
  folder inside a harness's layout, which the layout's own drop removes.
- A JSON file is written where it points, by a rename, and not over a change it saw before
  the rename. One install or uninstall runs at a time for a HOME: `alone` holds a lock on it.
- systemctl is run only when the user manager reads this HOME.
- uv is run with nothing forced: it never replaces a program that is not its own.
- A file `--setup` seeds is written once, with the digest of its bytes in a record, and is
  removed only while its bytes still have that digest.
"""

import fcntl
import hashlib
import json
import os
import pwd
import shutil
import subprocess
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class Ran:
    """What a process said. `code` is None when the program is not on PATH."""

    code: int | None
    out: str


@dataclass(frozen=True)
class JsonObject:
    """A JSON file parsed at the boundary: one object, or no file yet (`existed` False).
    `real` is where a write lands, so a symlink into a dotfiles repo stays a symlink.
    `seen` is the bytes read, which `Machine.write_object` compares before it writes."""

    path: Path
    real: Path
    value: dict
    existed: bool
    seen: bytes


@dataclass(frozen=True)
class Unreadable:
    """A file that is there and is not one JSON object. It is never rewritten."""

    path: Path
    why: str


@dataclass(frozen=True)
class Dropped:
    """What an uninstall step did, as printed: `removed <piece>`, `kept <piece> -> <why>`."""

    removed: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()


class Moved(Exception):
    """A file changed between the install's read and its write. The caller reads again, once."""


class Refused(Exception):
    """An effect the machine did not carry out, with the reason as it is printed."""


@dataclass(frozen=True)
class Machine:
    """`account` is the home directory the account has by its passwd entry: with `home` it
    tells the user's real HOME from a sandbox's or a test's. `checkout` is the git checkout
    jstack is installed from, None for a release, whose source is `release`: the tree its
    wheel installed (`jbriefs.skills.packaged`)."""

    checkout: Path | None
    home: Path
    env: Mapping[str, str]
    run: Callable[[Sequence[str]], Ran]
    account: Path
    release: Path | None = None

    @property
    def source(self) -> Path:
        """The tree each harness's layout is assembled from: the checkout, else the release's."""
        source = self.checkout if self.checkout is not None else self.release
        assert source is not None, "a machine has a checkout or a release"
        return source

    @classmethod
    def here(cls, checkout: Path | None, release: Path | None = None) -> "Machine":
        """The real one: HOME and PATH from the environment, `run` through subprocess."""
        env = dict(os.environ)

        def run(args: Sequence[str]) -> Ran:
            try:
                done = subprocess.run(
                    list(args),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except OSError:
                return Ran(None, "")
            return Ran(done.returncode, done.stdout)

        account = Path(pwd.getpwuid(os.getuid()).pw_dir)
        return cls(checkout, Path(env.get("HOME") or account), env, run, account, release)

    def which(self, name: str) -> Path | None:
        """What typing `name` would run, by this machine's PATH."""
        found = shutil.which(name, path=self.env.get("PATH", ""))
        return Path(found) if found else None

    def config_home(self) -> Path:
        """${XDG_CONFIG_HOME:-~/.config}."""
        return Path(self.env.get("XDG_CONFIG_HOME") or self.home / ".config")

    def state_home(self) -> Path:
        """${XDG_STATE_HOME:-~/.local/state}."""
        return Path(self.env.get("XDG_STATE_HOME") or self.home / ".local" / "state")

    def tool_bin(self) -> Path:
        """Where uv puts a tool's commands: $UV_TOOL_BIN_DIR, $XDG_BIN_HOME, else ~/.local/bin."""
        named = self.env.get("UV_TOOL_BIN_DIR") or self.env.get("XDG_BIN_HOME")
        return Path(named) if named else self.home / ".local" / "bin"

    def data_home(self) -> Path:
        """${XDG_DATA_HOME:-~/.local/share}."""
        return Path(self.env.get("XDG_DATA_HOME") or self.home / ".local" / "share")

    def layout(self, harness: str) -> Path:
        """Where the install assembles `harness`'s layout (`jinstall.layout`):
        ${XDG_DATA_HOME:-~/.local/share}/jstack/harness/<harness>."""
        return self.data_home() / "jstack" / "harness" / harness

    def _tools(self) -> Path:
        return Path(self.env.get("UV_TOOL_DIR") or self.data_home() / "uv" / "tools")

    def has_tool(self, tool: str) -> bool:
        """Whether uv has a tool of this name, however it was installed."""
        return (self._tools() / tool).is_dir()

    def tool_source(self, tool: str) -> Path | None:
        """The directory uv's tool `tool` is an editable install of, read from the PEP 610
        record under uv's tool directory and never by running uv. None when there is no such
        tool or it is not an editable install: `has_tool` tells the two apart."""
        record = f"lib/python*/site-packages/{tool.replace('-', '_')}-*.dist-info/direct_url.json"
        for path in sorted((self._tools() / tool).glob(record)):
            try:
                said = json.loads(path.read_text())
                url = urlparse(said["url"])
                if url.scheme == "file" and said["dir_info"]["editable"] is True:
                    return Path(unquote(url.path))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return None

    def tool_paths(self, tool: str) -> frozenset[Path]:
        """The directories the `.pth` files of uv's tool `tool` put on its path: an editable
        install lists one for each package root it was built with, and is not rebuilt when the
        checkout moves a package. A line that runs code (`import ...`) is not a path."""
        found: set[Path] = set()
        for path in sorted((self._tools() / tool).glob("lib/python*/site-packages/*.pth")):
            try:
                lines = path.read_text().splitlines()
            except OSError:
                continue
            found |= {Path(line.strip()) for line in lines if line.strip().startswith("/")}
        return frozenset(found)

    def tool_version(self, tool: str) -> str | None:
        """The version uv's tool `tool` has, from the `Version:` of its package's METADATA.
        None when there is no such tool or no record says."""
        record = f"lib/python*/site-packages/{tool.replace('-', '_')}-*.dist-info/METADATA"
        for path in sorted((self._tools() / tool).glob(record)):
            try:
                lines = path.read_text().splitlines()
            except OSError:
                continue
            for line in lines:
                if line.startswith("Version:"):
                    return line.removeprefix("Version:").strip()
        return None

    def in_a_worktree_of_the_account(self) -> bool:
        """Whether a plain install here would point the account's live skills at a linked
        worktree: HOME is the account's own, and the checkout's `.git` is a worktree's file."""
        if self.checkout is None:
            return False
        git = self.checkout / ".git"
        try:
            return self.home == self.account and git.is_file() and "/worktrees/" in git.read_text()
        except OSError:
            return False

    @contextmanager
    def alone(self) -> Iterator[None]:
        """Hold HOME's lock for as long as a verb writes, and wait for the run that has it.
        The lock is on the directory itself, so it leaves no file."""
        try:
            held = os.open(self.home, os.O_RDONLY)
        except OSError:
            yield
            return
        try:
            fcntl.flock(held, fcntl.LOCK_EX)
            yield
        finally:
            os.close(held)

    def _record(self) -> Path:
        return self.state_home() / "jstack" / "created"

    def _recorded(self) -> list[Path]:
        try:
            return [Path(line) for line in self._record().read_text().splitlines() if line]
        except OSError:
            return []

    def _write_record(self, paths: Sequence[Path]) -> None:
        with _beside(self._record()) as next_to:
            next_to.write_text("".join(f"{path}\n" for path in paths))

    def _note(self, path: Path | None) -> None:
        """Put `path` into the record. The levels above the record that are not there are
        made here and go into it too, since the record cannot hold them before it exists.
        With `path` None only the record's directory is made."""
        record = self._record()
        above = [level for level in _levels(record.parent.parent) if not level.exists()]
        record.parent.mkdir(parents=True, exist_ok=True)
        known = self._recorded()
        new = [each for each in dict.fromkeys((*above, path)) if each and each not in known]
        if new:
            self._write_record([*known, *new])

    def make_dirs(self, path: Path) -> None:
        """mkdir -p. Each level that was not there goes into the record first."""
        for level in _levels(path):
            if not level.is_dir():
                self._note(level)
                level.mkdir(exist_ok=True)

    def link(self, path: Path, target: Path) -> None:
        """Make or repoint the symlink `path`. Refuses a path that is there and is no link,
        unless it is a regular file whose bytes equal `target`'s."""
        if not path.is_symlink() and path.exists():
            if not (path.is_file() and target.is_file() and same_bytes(path, target)):
                raise Refused(f"{path} is not a link")
        self.make_dirs(path.parent)
        with _beside(path) as next_to:
            next_to.symlink_to(target)

    def unlink(self, path: Path) -> None:
        path.unlink()

    def write_text(self, path: Path, text: str) -> None:
        """Write a file that is not there yet. Each level above it that was not there goes
        into the record first, so an uninstall that removes the file leaves no directory."""
        self.make_dirs(path.parent)
        with _beside(path) as next_to:
            next_to.write_text(text)

    def read_object(self, path: Path) -> JsonObject | Unreadable:
        real = Path(os.path.realpath(path))
        try:
            seen = real.read_bytes()
        except FileNotFoundError:
            return JsonObject(path, real, {}, False, b"")
        except OSError as error:
            return Unreadable(path, error.strerror or "not readable")
        if not seen.strip():
            return JsonObject(path, real, {}, True, seen)
        try:
            value = json.loads(seen)
        except ValueError:
            return Unreadable(path, "not JSON")
        if not isinstance(value, dict):
            return Unreadable(path, "not a JSON object")
        return JsonObject(path, real, value, True, seen)

    def write_object(self, was: JsonObject, value: dict) -> None:
        """Write `value` at `was.real`, two-space indent, keys in the order read. A file that
        did not exist goes into the record first. A value equal to the one read writes
        nothing. Raises Moved when the bytes on disk are no longer `was.seen`."""
        if value == was.value:
            return
        now = self.read_object(was.path)
        if not isinstance(now, JsonObject) or (now.existed, now.seen) != (was.existed, was.seen):
            raise Moved(f"{was.path} changed while it was being written")
        if not was.existed:
            self.make_dirs(was.real.parent)
            self._note(was.real)
        with _beside(was.real) as next_to:
            next_to.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
            if was.existed:
                shutil.copymode(was.real, next_to)

    def _seeds(self) -> Path:
        return self.state_home() / "jstack" / "seeded"

    def _seeded(self) -> dict[Path, str]:
        """The record of seeded files, `<sha256> <path>` a line, as path to digest."""
        try:
            lines = self._seeds().read_text().splitlines()
        except OSError:
            return {}
        return {Path(path): digest for digest, _, path in (line.partition(" ") for line in lines)}

    def _write_seeded(self, seeded: dict[Path, str]) -> None:
        if not seeded:
            self._seeds().unlink(missing_ok=True)
            return
        self._note(None)
        with _beside(self._seeds()) as next_to:
            next_to.write_text("".join(f"{digest} {path}\n" for path, digest in seeded.items()))

    def seed(self, path: Path, text: str, mode: int) -> None:
        """Write a file that is not there, at `mode` from its first byte, and record the
        digest of what was written first. Refuses a path that is there, a link to nothing
        included: a file of the user's is never written over."""
        if path.is_symlink() or path.exists():
            raise Refused(f"{path} is there and is not written over")
        data = text.encode()
        self._write_seeded(self._seeded() | {path: hashlib.sha256(data).hexdigest()})
        self.make_dirs(path.parent)
        with _beside(path) as next_to:
            next_to.touch(mode=0o600)
            next_to.chmod(mode)
            next_to.write_bytes(data)

    def unseed(self, path: Path) -> bool | None:
        """Remove a seeded file while its bytes are the ones `seed` wrote. True when it was
        removed, False when it is kept, None when it is not a seeded file that is there. The
        record forgets a file that is gone, and a file that is kept stays in it."""
        seeded = self._seeded()
        if path not in seeded:
            return None
        try:
            same = hashlib.sha256(path.read_bytes()).hexdigest() == seeded[path]
        except FileNotFoundError:
            same = None
        except OSError:
            same = False
        if same is False:
            return False
        if same:
            path.unlink()
        del seeded[path]
        self._write_seeded(seeded)
        return same

    def zone(self) -> str | None:
        """The machine's own time zone as an IANA name: $TZ, else where /etc/localtime
        points under a zoneinfo directory. None when neither names one."""
        named = self.env.get("TZ", "").removeprefix(":")
        if named:
            return named
        local = os.path.realpath("/etc/localtime")
        _, found, name = local.partition("/zoneinfo/")
        return name if found else None

    def uv(self, *args: str) -> Ran:
        """Run uv. Before it, make through `make_dirs` each directory under HOME that uv would
        make by itself (`tool_bin()`), so the record has them."""
        self.make_dirs(self.tool_bin())
        return self.run(["uv", *args])

    def systemctl(self, *args: str) -> Ran | None:
        """Run `systemctl --user <args>`, or return None without running it when the manager
        does not read this HOME: `systemctl --user show-environment` gives another HOME, or
        does not answer. In a sandbox with no stand-in that is the real manager, so nothing
        is asked of it but that one question."""
        asked = self.run(["systemctl", "--user", "show-environment"])
        if asked.code != 0 or f"HOME={self.home}" not in asked.out.splitlines():
            return None
        return self.run(["systemctl", "--user", *args])

    def sweep(self) -> Dropped:
        """The last step of uninstall, over the record
        (${XDG_STATE_HOME:-~/.local/state}/jstack/created, one path a line). Deepest first:
        remove a recorded directory that is empty and a recorded JSON file that holds `{}`,
        and take its line out. One that holds anything else is kept, with its line. When no
        line is left but those of the levels above the record, remove the record and its
        directory, then each of those levels that is empty."""
        record = self._record()
        if not record.is_file():
            return Dropped()
        above = set(_levels(record.parent.parent))
        removed, left = [], []
        for path in sorted(set(self._recorded()), key=lambda each: len(each.parts), reverse=True):
            if path in above:
                left.append(path)
                continue
            emptied = _emptied(path)
            if emptied is False:
                left.append(path)
            elif emptied:
                removed.append(path)
        if any(path not in above for path in left):
            self._write_record(sorted(left))
            return Dropped(tuple(str(path) for path in removed))
        record.unlink()
        if _emptied(record.parent) is not False:
            removed += [path for path in left if _emptied(path)]
        return Dropped(tuple(str(path) for path in removed))


def same_bytes(one: Path, other: Path) -> bool:
    try:
        return one.read_bytes() == other.read_bytes()
    except OSError:
        return False


@contextmanager
def _beside(path: Path) -> Iterator[Path]:
    """A name beside `path` that is this process's own, renamed over `path` when the block
    ends and removed when it raises."""
    next_to = path.with_name(f"{path.name}.{os.getpid()}.new")
    try:
        yield next_to
        os.replace(next_to, path)
    except BaseException:
        if next_to.is_symlink() or next_to.exists():
            next_to.unlink()
        raise


def _levels(path: Path) -> list[Path]:
    """`path` and every directory above it, the top one first."""
    return [*reversed(path.parents), path]


def _emptied(path: Path) -> bool | None:
    """Remove a directory that is empty, or a JSON file that holds `{}`. True when this
    removed it, False when it is kept, None when it was not there."""
    try:
        if path.is_symlink():
            return False
        if path.is_dir():
            path.rmdir()
        elif path.is_file() and path.read_bytes().strip() == b"{}":
            path.unlink()
        else:
            return False if path.exists() else None
    except OSError:
        return False
    return True
