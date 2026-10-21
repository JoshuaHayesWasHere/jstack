"""`jroles mirror`: every extra Claude home a mirror of `~/.claude`, its login aside.

T3 Code runs a second Claude account as an instance of its own, in a home of its own (the
`config.homePath` of a `claudeAgent` instance of `~/.config/jstack/providers.json`, such as
`~/.claude_prime`). A thread on it should have the memory, the transcripts, the skills, the
settings and the instructions of the main home, `~/.claude`, and only the login of its own.
So each entry of `~/.claude` is a symlink in the mirror, except the ones bound to a login or
to one process (`KEEP`), and `<home>/.claude.json` stays a file of the mirror's own: its
account keys (`ACCOUNT_KEYS`) are the mirror's, and every other key is the main file's,
`projects` merged per project with the main file winning.

`plan` reads a mirror and gives what differs, one `Step` an entry, and nothing else: so
`--check` and a run are the same reading. A run applies the steps under a lock in the mirror,
and a run with nothing to do writes nothing. These are infra #53's rules:

- an entry of `~/.claude` the mirror lacks is linked (`link`);
- a real entry the mirror holds where `~/.claude` has one, or a link elsewhere, is moved to
  `<name>.bak-<time>` and linked. A directory's files are merged into `~/.claude` first: a
  file `~/.claude` lacks is copied, and one it holds with other bytes wins and is named as a
  conflict, the mirror's copy staying in the backup (`backup`);
- an entry only the mirror has moves into `~/.claude` and is linked back (`move`);
- a link into `~/.claude` whose entry is gone is removed (`dangling`);
- `.claude.json` takes the main file's keys as above (`json`).

Each step is safe to repeat and to stop halfway: the merge is made before the move and again
after it, so a run that stopped between the two leaves nothing unmerged, and every other step
finds nothing to do once its entry is a link.
"""

from __future__ import annotations

import argparse
import fcntl
import filecmp
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from jroles import Refused, pool

KEEP = frozenset(
    {
        ".credentials.json",
        ".claude.json",
        "sessions",
        "session-env",
        "shell-snapshots",
        "cache",
        "backups",
        "debug",
        "statsig",
        "telemetry",
        "ide",
        "stats-cache.json",
        ".last-cleanup",
        ".last-update-result.json",
    }
)
ACCOUNT_KEYS = re.compile(
    r"^(oauthAccount|userID|summonSidKey|firstStartTime|firstStartVersion|numStartups"
    r"|claudeCodeFirstTokenDate|claudeAiMcpEverConnected|penguinModeOrgEnabled|hasVisitedPasses"
    r"|clientDataCacheSlots|cached.*|.*Cache|.*CacheAt|additionalModel.*|passes.*|overage.*"
    r"|promoStartup.*|modelAccess.*|orgModel.*|groveConfig.*|s1mAccessCache.*)$"
)
LOCK = ".jroles-mirror.lock"
JSON = ".claude.json"
_OURS = re.compile(r".*\.bak[-.].*|\.jroles-mirror\.lock|\.prime-sync\.lock|\.claude\.json\..*")
DRIFT, BROKEN = 1, 2


@dataclass(frozen=True)
class Mirror:
    """One home to keep a mirror of the main one, and the instance it is the home of."""

    instance: str
    home: Path


@dataclass(frozen=True)
class Main:
    """The main home, `~/.claude`, and its `.claude.json`, which is beside it in `$HOME`."""

    home: Path
    config: Path

    @classmethod
    def of(cls, user: Path) -> Main:
        return cls(user / ".claude", user / JSON)


@dataclass(frozen=True)
class Step:
    """One entry of a mirror that is not as it should be. `kind` is `link`, `backup`,
    `move`, `dangling` or `json`; `name` is the entry's name in the mirror's home, and `keys`
    are the shared keys of a `json` step whose values differ."""

    kind: str
    name: str
    keys: tuple[str, ...] = ()

    def would(self, main: Main, mirror: Mirror) -> str:
        """What `--check` says of it."""
        at, there = mirror.home / self.name, main.home / self.name
        return {
            "link": f"would link {at} -> {there}",
            "backup": f"would back up {at} and link it -> {there}",
            "move": f"would move {at} into {main.home} and link it",
            "dangling": f"would remove dangling {at}",
            "json": f"would sync {', '.join(self.keys)} of {main.config} into {at}",
        }[self.kind]


def mirrors(text: str, user: Path) -> tuple[Mirror, ...]:
    """Each `claudeAgent` instance of providers.json `text` whose home is not `~/.claude`.
    A home is `config.homePath`, `~` for `user`, with no slash at the end, as
    `hooks/limits.sh` reads it. Refused when the file is not T3's shape."""
    pool.declared(text)
    main = os.path.realpath(user / ".claude")
    found = []
    for name, entry in json.loads(text).items():
        config = entry.get("config")
        path = config.get("homePath") if isinstance(config, dict) else None
        if entry["driver"] != "claudeAgent" or not isinstance(path, str) or not path:
            continue
        if path == "~" or path.startswith("~/"):
            path = str(user) + path[1:]
        home = Path(path.rstrip("/") or "/")
        if not home.is_absolute():
            raise Refused(f"refused: {name}'s homePath {path} is not absolute")
        if os.path.realpath(home) != main:
            found.append(Mirror(str(name), home))
    return tuple(found)


def declared(user: Path) -> tuple[Mirror, ...]:
    """The mirrors this machine's providers.json declares, none with no file."""
    try:
        text = (pool.config_dir() / "providers.json").read_text()
    except FileNotFoundError:
        return ()
    except (OSError, UnicodeDecodeError) as error:
        raise Refused(f"refused: providers.json cannot be read ({error})") from error
    return mirrors(text, user)


def _entries(directory: Path) -> list[str]:
    return sorted(
        name for name in os.listdir(directory) if name not in KEEP and not _OURS.fullmatch(name)
    )


def _linked(at: Path, there: Path) -> bool:
    return at.is_symlink() and os.readlink(at) == str(there)


def plan(main: Main, mirror: Mirror) -> tuple[Step, ...]:
    """What differs between the mirror and the main home, read and never changed."""
    steps = []
    for name in _entries(main.home):
        at, there = mirror.home / name, main.home / name
        if not there.exists() or _linked(at, there):
            continue
        steps.append(Step("backup" if os.path.lexists(at) else "link", name))
    named = {step.name for step in steps}
    for name in _entries(mirror.home):
        at, there = mirror.home / name, main.home / name
        if name in named:
            continue
        if at.is_symlink():
            if os.readlink(at).startswith(f"{main.home}/") and not at.exists():
                steps.append(Step("dangling", name))
        elif not os.path.lexists(there):
            steps.append(Step("move", name))
    found = shared(main, mirror)
    if found is not None:
        steps.append(Step("json", JSON, found[1]))
    return tuple(steps)


def _deep(kept: object, over: object) -> object:
    """`kept * over` as jq merges two values: objects key by key, `over` winning elsewhere."""
    if not (isinstance(kept, dict) and isinstance(over, dict)):
        return over
    return {**kept, **{key: _deep(kept.get(key), value) for key, value in over.items()}}


def _read(path: Path) -> dict | None:
    try:
        found = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise Refused(f"jroles mirror: {path} cannot be read as JSON ({error})") from error
    if not isinstance(found, dict):
        raise Refused(f"jroles mirror: {path} is not a JSON object")
    return found


def shared(main: Main, mirror: Mirror) -> tuple[dict, tuple[str, ...]] | None:
    """The mirror's `.claude.json` with the main file's shared keys, and the keys whose values
    that changes, or None when it is so already, or when either file is not there: a home
    with none has no login to keep."""
    ours, theirs = _read(mirror.home / JSON), _read(main.config)
    if ours is None or theirs is None:
        return None
    account = {key: value for key, value in ours.items() if ACCOUNT_KEYS.match(key)}
    rest = {key: value for key, value in ours.items() if not ACCOUNT_KEYS.match(key)}
    common = {key: value for key, value in theirs.items() if not ACCOUNT_KEYS.match(key)}
    made = {**rest, **common, **account}
    made["projects"] = _deep(ours.get("projects") or {}, theirs.get("projects") or {})
    keys = tuple(
        sorted(key for key, value in made.items() if key not in ours or ours[key] != value)
    )
    return (made, keys) if keys else None


def _files(directory: Path) -> Iterator[Path]:
    for root, _, names in os.walk(directory):
        for name in sorted(names):
            path = Path(root) / name
            if path.is_file() and not path.is_symlink():
                yield path.relative_to(directory)


def merge(source: Path, into: Path, kept: Path) -> list[str]:
    """Copy each file under `source` that `into` lacks; name each that both hold with other
    bytes, whose copy from the mirror is under `kept`."""
    said = []
    for relative in _files(source):
        there = into / relative
        if not os.path.lexists(there):
            there.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, there)
        elif not (there.is_file() and filecmp.cmp(source / relative, there, shallow=False)):
            said.append(f"conflict  {there} kept; the mirror's copy is in {kept / relative}")
    return said


def _backup(at: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    made, count = at.with_name(f"{at.name}.bak-{stamp}"), 1
    while os.path.lexists(made):
        made, count = at.with_name(f"{at.name}.bak-{stamp}-{count}"), count + 1
    return made


def apply(main: Main, mirror: Mirror, step: Step) -> list[str]:
    """Make one step so, and say what it did."""
    at, there = mirror.home / step.name, main.home / step.name
    if step.kind == "link":
        at.symlink_to(there)
        return [f"linked    {at} -> {there}"]
    if step.kind == "backup":
        backup = _backup(at)
        merging = at.is_dir() and not at.is_symlink() and there.is_dir()
        said = merge(at, there, backup) if merging else []
        os.rename(at, backup)
        at.symlink_to(there)
        if merging:
            said += [line for line in merge(backup, there, backup) if line not in said]
        return [f"backup    {at} -> {backup}", *said, f"linked    {at} -> {there}"]
    if step.kind == "move":
        if os.path.lexists(there):
            return [f"kept      {at}: {there} is there now, and the next run merges it"]
        shutil.move(at, there)
        at.symlink_to(there)
        return [f"moved     {at} -> {there}, linked"]
    if step.kind == "dangling":
        at.unlink()
        return [f"removed   dangling {at}"]
    found = shared(main, mirror)
    if found is None:
        return []
    made, _ = found
    target = mirror.home / JSON
    temporary = target.with_name(f"{JSON}.mirror.{os.getpid()}")
    temporary.unlink(missing_ok=True)
    try:
        with os.fdopen(os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as out:
            out.write(json.dumps(made, indent=2, ensure_ascii=False) + "\n")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return [f"synced    shared keys of {main.config} into {target}"]


def check(main: Main, mirror: Mirror) -> list[str]:
    """What `--check` says of one mirror: a line for each entry that differs."""
    if not mirror.home.is_dir():
        return [f"{mirror.instance}: {mirror.home} is missing"]
    return [step.would(main, mirror) for step in plan(main, mirror)]


def run(main: Main, mirror: Mirror) -> list[str]:
    """Make one mirror so, under its lock and the main home's, and say what changed: nothing
    when nothing did. The main home's lock is what keeps two runs on two mirrors from moving
    the same new name into `~/.claude` at once: each plan is read and applied with no other
    run writing there."""
    if not mirror.home.is_dir():
        raise Refused(f"jroles mirror: {mirror.instance}: {mirror.home} is missing")
    with (mirror.home / LOCK).open("a") as own, (main.home / LOCK).open("a") as shared_lock:
        fcntl.flock(own, fcntl.LOCK_EX)
        fcntl.flock(shared_lock, fcntl.LOCK_EX)
        return [line for step in plan(main, mirror) for line in apply(main, mirror, step)]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="jroles mirror",
        description="Make each extra Claude home of providers.json a mirror of ~/.claude.",
    )
    parser.add_argument(
        "--check", action="store_true", help="change nothing; exit 1 if anything differs"
    )
    parser.add_argument("--instance", help="the one instance to mirror or check")
    args = parser.parse_args(argv)
    user = Path.home()
    try:
        chosen = declared(user)
    except Refused as refused:
        print(refused, file=sys.stderr)
        return BROKEN
    if args.instance:
        chosen = tuple(one for one in chosen if one.instance == args.instance)
        if not chosen:
            print(f"jroles mirror: {args.instance} is no mirror of providers.json", file=sys.stderr)
            return BROKEN
    home, code = Main.of(user), 0
    if not home.home.is_dir():
        print(f"jroles mirror: {home.home} is missing", file=sys.stderr)
        return BROKEN
    for one in chosen:
        try:
            said = check(home, one) if args.check else run(home, one)
        except (Refused, OSError) as error:
            said = error if isinstance(error, Refused) else f"jroles mirror: {error}"
            print(said, file=sys.stderr)
            code = BROKEN
            continue
        for line in said:
            print(line)
        if args.check and said:
            code = code or DRIFT
        elif args.check:
            print(f"ok        {one.home} mirrors {home.home}")
    return code
