"""The machine a verb acts on, and every effect the install has on it.

A kind writes only through Machine, so this file can enforce these rules:
- The install puts each directory or JSON file it creates into the record before the file
  exists. A folder inside a harness's layout is the exception: the layout's own drop removes
  it.
- Machine writes a JSON file where its symlink points, by a rename, and never over a change
  made after it read the file. One install or uninstall runs at a time for a HOME, because
  `alone` holds a lock on it.
- Machine runs systemctl only when the user manager reads this HOME.
- Machine runs uv with nothing forced, so uv never replaces a program that is not its own.
- Machine writes a file that `--setup` seeds once, with the digest of its bytes in a record,
  and removes it only while its bytes still have that digest.
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
    """A JSON file that the machine parses as it reads it: one object, or no file yet, when
    `existed` is False. `real` is the path that a write goes to, so a symlink into a dotfiles
    repo stays a symlink. `seen` holds the bytes read, which `Machine.write_object` compares
    before it writes."""

    path: Path
    real: Path
    value: dict
    existed: bool
    seen: bytes


@dataclass(frozen=True)
class Unreadable:
    """A file that is there and is not one JSON object. The install never rewrites it."""

    path: Path
    why: str


@dataclass(frozen=True)
class Dropped:
    """What an uninstall step did, as it prints: `removed <piece>` or
    `kept <piece> -> <why>`."""

    removed: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()


class Moved(Exception):
    """A file changed between the install's read and its write. The caller reads it again,
    once."""


class Refused(Exception):
    """An effect the machine did not carry out, with the reason as the line prints it."""


@dataclass(frozen=True)
class Machine:
    """`account` is the account's home directory by its passwd entry. Compared with `home`,
    it tells the user's real HOME from a sandbox's or a test's.

    `checkout` is the git checkout that jstack's install runs from, or None for a release. A
    release's source is `release`, the tree its wheel installed (`jbriefs.skills.packaged`)."""

    checkout: Path | None
    home: Path
    env: Mapping[str, str]
    run: Callable[[Sequence[str]], Ran]
    account: Path
    release: Path | None = None

    @property
    def source(self) -> Path:
        """The tree the install assembles each harness's layout from: the checkout, or else
        the release's tree."""
        source = self.checkout if self.checkout is not None else self.release
        assert source is not None, "a machine has a checkout or a release"
        return source

    @classmethod
    def here(cls, checkout: Path | None, release: Path | None = None) -> "Machine":
        """The real machine. It takes HOME and PATH from the environment, and `run` goes
        through subprocess."""
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
        """The program that typing `name` would run, by this machine's PATH."""
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
        """The directory that uv's tool `tool` is an editable install of. The method reads
        it from the PEP 610 record under uv's tool directory, and never runs uv. It returns
        None when there is no such tool or the tool is not an editable install, and
        `has_tool` tells those two cases apart."""
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
        """The directories that the `.pth` files of uv's tool `tool` put on its path. An
        editable install lists one for each package root that uv built it with. uv does not
        rebuild it when the checkout moves a package. A line that runs code (`import ...`) is
        not a path."""
        found: set[Path] = set()
        for path in sorted((self._tools() / tool).glob("lib/python*/site-packages/*.pth")):
            try:
                lines = path.read_text().splitlines()
            except OSError:
                continue
            found |= {Path(line.strip()) for line in lines if line.strip().startswith("/")}
        return frozenset(found)

    def tool_version(self, tool: str) -> str | None:
        """The version of uv's tool `tool`, from the `Version:` of its package's METADATA.
        It is None when there is no such tool or no record gives a version."""
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
        worktree. That is so when HOME is the account's own and the checkout's `.git` is a
        worktree's file."""
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
        """Put `path` into the record. This method makes the missing levels above the record
        and records them too, since the record cannot hold them before it exists. With `path`
        None, it makes only the record's directory."""
        record = self._record()
        above = [level for level in _levels(record.parent.parent) if not level.exists()]
        record.parent.mkdir(parents=True, exist_ok=True)
        known = self._recorded()
        new = [each for each in dict.fromkeys((*above, path)) if each and each not in known]
        if new:
            self._write_record([*known, *new])

    def make_dirs(self, path: Path) -> None:
        """Make the directory and its parents, as mkdir -p does. Each level that was not
        there goes into the record first."""
        for level in _levels(path):
            if not level.is_dir():
                self._note(level)
                level.mkdir(exist_ok=True)

    def link(self, path: Path, target: Path) -> None:
        """Make or repoint the symlink `path`. The method refuses a path that is there and is
        not a link, unless it is a regular file whose bytes equal `target`'s."""
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
        """Write `value` at `was.real`, with a two-space indent and the keys in the order
        read. A file that did not exist goes into the record first. A value equal to the one
        read writes nothing. The method raises Moved when the bytes on disk are no longer
        `was.seen`."""
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
        """The record of seeded files, one `<sha256> <path>` on each line, as a map from
        path to digest."""
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
        """Write a file that is not there, and record the digest of what it wrote. The file
        has `mode` from the moment it is created, before its first byte. The method refuses any
        path that is there, even a link to nothing, so it never writes over a file of the
        user's."""
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
        """Remove a seeded file while its bytes are the ones `seed` wrote. Return True when
        it removed the file, False when it kept the file, and None when no seeded file is
        there. The method drops a file that is gone from the record, and keeps the entry of a
        file that stays."""
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
        """The machine's own time zone as an IANA name. It is $TZ, or else where
        /etc/localtime points under a zoneinfo directory, and None when neither names one."""
        named = self.env.get("TZ", "").removeprefix(":")
        if named:
            return named
        local = os.path.realpath("/etc/localtime")
        _, found, name = local.partition("/zoneinfo/")
        return name if found else None

    def uv(self, *args: str) -> Ran:
        """Run uv. First make, through `make_dirs`, each directory under HOME that uv would
        make by itself (`tool_bin()`), so the record has them."""
        self.make_dirs(self.tool_bin())
        return self.run(["uv", *args])

    def systemctl(self, *args: str) -> Ran | None:
        """Run `systemctl --user <args>`, or return None without running it when the manager
        does not read this HOME. The manager does not read this HOME when
        `systemctl --user show-environment` gives another HOME, or does not answer. In a
        sandbox with no stand-in, the manager is the real one, so this method asks it only
        that one question."""
        asked = self.run(["systemctl", "--user", "show-environment"])
        if asked.code != 0 or f"HOME={self.home}" not in asked.out.splitlines():
            return None
        return self.run(["systemctl", "--user", *args])

    def sweep(self) -> Dropped:
        """The last step of uninstall, over the record
        (${XDG_STATE_HOME:-~/.local/state}/jstack/created, one path on each line).

        Deepest first, it removes each recorded directory that is empty and each recorded
        JSON file that holds `{}`, and takes its line out. It keeps one that holds anything
        else, with its line. When the only lines left are those of the levels above the
        record, it removes the record and its directory, then each of those levels that is
        empty."""
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
    """A name beside `path` that is this process's own. This context renames the file
    over `path` when the block ends, and removes it when the block raises."""
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
    """Remove a directory that is empty, or a JSON file that holds `{}`. Return True when
    this call removed it, False when it kept it, and None when it was not there."""
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
