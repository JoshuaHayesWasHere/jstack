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

`skillUsage` is no key of the main file's: all the accounts are one user, so it is pooled. Each
skill's entry in the pool has, field by field, the highest of every home's numbers, so the
highest count and the latest time, and a run writes the pool into `~/.claude.json` and into
each mirror. `--check` compares each home with the pool: a home behind it by use since the last
sync (`PERIOD`, the timer's longest gap) is `pooling`, no drift, and one that lacks a skill
whose last use is older than that, or whose skillUsage is not objects of numbers, fails.

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
USAGE = "skillUsage"
PERIOD = (5 + 1 + 1) * 60
"""The longest a use waits to be pooled, in seconds: the 5 minutes of `OnUnitActiveSec` in
`templates/jroles-mirror.timer`, its default `AccuracySec` of 1 minute, and 1 for the run."""


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
    are the shared keys of a `json` step whose values differ, and `usage` the skill use it pools
    in."""

    kind: str
    name: str
    keys: tuple[str, ...] = ()
    usage: dict | None = None

    def would(self, main: Main, mirror: Mirror) -> str:
        """What `--check` says of it."""
        at, there = mirror.home / self.name, main.home / self.name
        keys = ", ".join(self.keys)
        return {
            "link": f"would link {at} -> {there}",
            "backup": f"would back up {at} and link it -> {there}",
            "move": f"would move {at} into {main.home} and link it",
            "dangling": f"would remove dangling {at}",
            "json": f"would sync {keys} of {main.config} into {at}",
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


def plan(main: Main, mirror: Mirror, usage: dict | None = None) -> tuple[Step, ...]:
    """What differs between the mirror and the main home, read and never changed, with the
    pooled skill `usage`, none to leave the mirror's as it is."""
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
    found = shared(main, mirror, usage)
    if found is not None:
        steps.append(Step("json", JSON, found[1], usage))
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


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def usage_of(path: Path, found: dict) -> dict:
    """The skillUsage of `found`, the file at `path`, none when it has none. Refused, naming
    the skill, when an entry is not an object of numbers: its fields could not be pooled."""
    usage = found.get(USAGE, {})
    if not isinstance(usage, dict):
        raise Refused(f"jroles mirror: {path}: {USAGE} is not a JSON object")
    for skill, entry in usage.items():
        if not isinstance(entry, dict) or not all(map(_number, entry.values())):
            raise Refused(f"jroles mirror: {path}: {USAGE} {skill} is malformed: {entry!r}")
    return usage


def pooled(*usages: dict) -> dict:
    """Every skill of `usages`, each field the highest any of them has: the highest count and
    the latest time, so use in one home is never lost to another."""
    pool: dict[str, dict] = {}
    for usage in usages:
        for skill, entry in usage.items():
            kept = pool.get(skill, {})
            pool[skill] = {**kept, **{k: max(v, kept.get(k, v)) for k, v in entry.items()}}
    return pool


def pool_of(main: Main, homes: tuple[Path, ...]) -> dict:
    """The skillUsage pool of `~/.claude.json` and each of `homes`' `.claude.json`."""
    usages = []
    for path in (main.config, *(home / JSON for home in homes)):
        found = _read(path)
        if found is not None:
            usages.append(usage_of(path, found))
    return pooled(*usages)


def lags(path: Path, usage: dict, pool: dict, now: float) -> tuple[list[str], list[str]]:
    """What `--check` says of the skillUsage `usage` of the file at `path` against the pool:
    the failures, a skill it lacks that was last used more than `PERIOD` ago, which a sync
    since should have brought, and the use it is behind by that the next sync brings."""
    lost, behind = [], []
    for skill, entry in pool.items():
        if skill in usage:
            if pooled({skill: usage[skill]}, {skill: entry})[skill] != usage[skill]:
                behind.append(skill)
            continue
        last = entry.get("lastUsedAt")
        (behind if _number(last) and last / 1000 > now - PERIOD else lost).append(skill)
    return (
        [f"would pool {USAGE} {', '.join(lost)} into {path}"] if lost else [],
        [f"pooling   {USAGE} {', '.join(behind)} into {path}"] if behind else [],
    )


def shared(
    main: Main, mirror: Mirror, usage: dict | None = None
) -> tuple[dict, tuple[str, ...]] | None:
    """The mirror's `.claude.json` with the main file's shared keys and its skillUsage pooled
    with `usage`, and the shared keys whose values that changes, or None when it is so already,
    or when either file is not there: a home with none has no login to keep."""
    target = mirror.home / JSON
    ours, theirs = _read(target), _read(main.config)
    if ours is None or theirs is None:
        return None
    account = {key: value for key, value in ours.items() if ACCOUNT_KEYS.match(key)}
    rest = {key: value for key, value in ours.items() if not ACCOUNT_KEYS.match(key)}
    common = {
        key: value for key, value in theirs.items() if not ACCOUNT_KEYS.match(key) and key != USAGE
    }
    made = {**rest, **common, **account}
    made["projects"] = _deep(ours.get("projects") or {}, theirs.get("projects") or {})
    if usage is not None and (usage or USAGE in ours):
        made[USAGE] = pooled(usage_of(target, ours), usage)
    keys = tuple(
        sorted(
            key
            for key, value in made.items()
            if key != USAGE and (key not in ours or ours[key] != value)
        )
    )
    return (made, keys) if made != ours else None


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
    found = shared(main, mirror, step.usage)
    if found is None:
        return []
    made, keys = found
    target = mirror.home / JSON
    _write(target, made, 0o600)
    if keys:
        return [f"synced    shared keys of {main.config} into {target}"]
    return [f"pooled    {USAGE} into {target}"]


def _write(target: Path, made: dict, mode: int) -> None:
    """Write `made` to `target` at once, by a temporary file renamed over it."""
    temporary = target.with_name(f"{JSON}.mirror.{os.getpid()}")
    temporary.unlink(missing_ok=True)
    try:
        with os.fdopen(os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode), "w") as out:
            out.write(json.dumps(made, indent=2, ensure_ascii=False) + "\n")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def review(
    main: Main, mirror: Mirror, usage: dict | None, now: float
) -> tuple[list[str], list[str]]:
    """What `--check` says of one mirror against the skill `usage` pool, none to leave its
    skillUsage out: a line for each entry that differs, and the use it is behind that is no
    drift. With either `.claude.json` missing, `shared` pools nothing, so none is read."""
    if not mirror.home.is_dir():
        return [f"{mirror.instance}: {mirror.home} is missing"], []
    said = [
        step.would(main, mirror)
        for step in plan(main, mirror, usage)
        if step.kind != "json" or step.keys
    ]
    target = mirror.home / JSON
    found = _read(target)
    if usage is None or found is None or _read(main.config) is None:
        return said, []
    lost, behind = lags(target, usage_of(target, found), usage, now)
    return said + lost, behind


def check(main: Main, mirror: Mirror) -> list[str]:
    """What `--check` finds wrong with one mirror: a line for each entry that differs, against
    the pool of every home providers.json declares, as `jroles mirror --check` reads it."""
    try:
        homes = [one.home for one in declared(main.config.parent) if one.home.is_dir()]
    except Refused:
        homes = []
    usage = pool_of(main, tuple(dict.fromkeys([*homes, mirror.home])))
    return review(main, mirror, usage, time.time())[0]


def run(main: Main, mirror: Mirror, usage: dict | None = None) -> list[str]:
    """Make one mirror so, under its lock and the main home's, with the skill `usage` pooled
    in, and say what changed: nothing when nothing did. The main home's lock is what keeps two
    runs on two mirrors from moving the same new name into `~/.claude` at once: each plan is
    read and applied with no other run writing there."""
    if not mirror.home.is_dir():
        raise Refused(f"jroles mirror: {mirror.instance}: {mirror.home} is missing")
    with (mirror.home / LOCK).open("a") as own, (main.home / LOCK).open("a") as shared_lock:
        fcntl.flock(own, fcntl.LOCK_EX)
        fcntl.flock(shared_lock, fcntl.LOCK_EX)
        steps = plan(main, mirror, usage)
        return [line for step in steps for line in apply(main, mirror, step)]


def pool_main(main: Main, usage: dict) -> list[str]:
    """Pool the skill `usage` into `~/.claude.json`, under the main home's lock, its every
    other key as it is, and say so: nothing when it has it all already."""
    with (main.home / LOCK).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        found = _read(main.config)
        if found is None:
            return []
        made = pooled(usage_of(main.config, found), usage)
        if made == found.get(USAGE, {}):
            return []
        _write(main.config, {**found, USAGE: made}, main.config.stat().st_mode & 0o777)
        return [f"pooled    {USAGE} into {main.config}"]


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
        chosen = every = declared(user)
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
    try:
        usage: dict | None = pool_of(home, tuple(one.home for one in every if one.home.is_dir()))
    except (Refused, OSError) as error:
        usage, code = None, _broken(error)
    if args.check:
        return max(code, _check(home, chosen, usage, main_too=not args.instance))
    for one in chosen:
        try:
            said = run(home, one, usage)
        except (Refused, OSError) as error:
            code = _broken(error)
            continue
        for line in said:
            print(line)
    if usage is not None:
        try:
            for line in pool_main(home, usage):
                print(line)
        except (Refused, OSError) as error:
            code = _broken(error)
    return code


def _broken(error: Exception) -> int:
    print(error if isinstance(error, Refused) else f"jroles mirror: {error}", file=sys.stderr)
    return BROKEN


def _check(main: Main, chosen: tuple[Mirror, ...], usage: dict | None, main_too: bool) -> int:
    """`--check`: each chosen mirror against the pool, and `~/.claude.json` with them unless
    one instance was asked for. A line that is only `pooling` is no drift, and with no pool, a
    home's skillUsage being malformed, the rest is still read."""
    code, now = 0, time.time()
    if main_too and usage is not None:
        try:
            found = _read(main.config)
            lost, behind = (
                ([], [])
                if found is None
                else lags(main.config, usage_of(main.config, found), usage, now)
            )
        except (Refused, OSError) as error:
            code, lost, behind = _broken(error), [], []
        for line in lost + behind:
            print(line)
        code = code or (DRIFT if lost else 0)
    for one in chosen:
        try:
            said, behind = review(main, one, usage, now)
        except (Refused, OSError) as error:
            code = _broken(error)
            continue
        for line in said + behind:
            print(line)
        if said:
            code = code or DRIFT
        else:
            print(f"ok        {one.home} mirrors {main.home}")
    return code
