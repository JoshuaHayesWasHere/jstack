"""`jroles mirror`: make every extra Claude home a mirror of `~/.claude`, except for its login.

T3 Code runs a second Claude account as an instance of its own, in a home of its own. That
home is the `config.homePath` of a `claudeAgent` instance of `~/.config/jstack/providers.json`,
such as `~/.claude_prime`. A thread on that instance should have the memory, the transcripts,
the skills, the settings and the instructions of the main home, `~/.claude`, and only the
login of its own. So each entry of `~/.claude` is a symlink in the mirror, except the entries
that belong to a login or to one process (`KEEP`). `<home>/.claude.json` stays the mirror's own
file. The run keeps the mirror's values for its account keys (`ACCOUNT_KEYS`), and copies every
other key from the main file. The run merges `projects` project by project, and where the two
files differ, it keeps the main file's value.

`plan` reads a mirror and returns what differs, one `Step` for each entry, and does nothing
else. So `--check` and a run read the mirror the same way. A run applies the steps under a
lock in the mirror, and a run with nothing to do writes nothing. These are infra #53's rules:

- `link`: the run links an entry of `~/.claude` that the mirror lacks.
- `backup`: the mirror holds a real entry where `~/.claude` has one, or a link that points
  elsewhere. The run moves it to `<name>.bak-<time>` and links it. For a directory, the run
  first merges its files into `~/.claude`. It copies a file that `~/.claude` lacks. When
  `~/.claude` holds the file with other bytes, the run keeps the `~/.claude` copy and names
  the file as a conflict. The mirror's copy stays in the backup.
- `move`: the run moves an entry that only the mirror has into `~/.claude`, and links it back.
- `dangling`: the run removes a link into `~/.claude` whose entry is gone.
- `json`: the run gives `.claude.json` the main file's keys, as above.

The run does not copy `skillUsage` from the main file. All the accounts are one user, so the
run pools it. For each skill, the run takes the highest of every home's numbers, field by
field, which gives the highest count and the latest time. A run writes the pool into
`~/.claude.json` and into each mirror.

`--check` compares each home with the pool. A home may lack only the use since the last sync,
within `PERIOD`, the timer's longest gap. Such a home is `pooling`, which is not drift. A home
fails when it lacks a skill whose last use is older than `PERIOD`, or when its skillUsage holds
an entry that is not an object of numbers.

Each step is safe to repeat and to stop halfway. The run merges before the move and again
after it, so a run that stopped between the two leaves nothing unmerged. Once an entry is a
link, the run has nothing to do for any other step on it.
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

from jroles import Refused, inventory, pool

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
"""The longest time, in seconds, between a skill use and the run that pools it. It is the sum
of the 5 minutes of `OnUnitActiveSec` in `features/jroles/units/jroles-mirror.timer`, its
default `AccuracySec` of 1 minute, and 1 minute for the run."""


@dataclass(frozen=True)
class Mirror:
    """One home to keep as a mirror of the main one, and the instance that the home
    belongs to."""

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
    `move`, `dangling` or `json`. `name` is the entry's name in the mirror's home. For a
    `json` step, `keys` are the shared keys whose values differ, and `usage` is the skill use
    that the step pools in."""

    kind: str
    name: str
    keys: tuple[str, ...] = ()
    usage: dict | None = None

    def would(self, main: Main, mirror: Mirror) -> str:
        """What `--check` says of the step."""
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
    A home is `config.homePath`. The function reads `~` as `user` and drops the slash at the
    end, as `features/jgauge/hooks/limits.sh` does. The function refuses a file that is not in
    T3's shape."""
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
    """The mirrors that this machine's providers.json declares, or none when there is no
    file."""
    try:
        text = inventory.path().read_text()
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
    """What differs between the mirror and the main home. The function only reads, and
    changes nothing. `usage` is the pooled skill use, or None to leave the mirror's skillUsage
    as it is."""
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
    """`kept * over`, merged as jq merges two values. jq merges two objects key by key, and
    for any other value it takes `over`."""
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
    """The skillUsage of `found`, the file at `path`, or an empty one when it has none. The
    function refuses, and names the skill, when an entry is not an object of numbers, since
    `pooled` could not pool its fields."""
    usage = found.get(USAGE, {})
    if not isinstance(usage, dict):
        raise Refused(f"jroles mirror: {path}: {USAGE} is not a JSON object")
    for skill, entry in usage.items():
        if not isinstance(entry, dict) or not all(map(_number, entry.values())):
            raise Refused(f"jroles mirror: {path}: {USAGE} {skill} is malformed: {entry!r}")
    return usage


def pooled(*usages: dict) -> dict:
    """Every skill of `usages`, with each field at the highest value any of them has. That is
    the highest count and the latest time, so the merge loses no home's use."""
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
    """What `--check` says when it compares the skillUsage `usage` of the file at `path` with
    the pool. It returns two lists. The first holds the failures. A failure is a skill that the
    file lacks and that a thread last used more than `PERIOD` ago, so a sync since then should
    have added it. The second holds the skill use that the file lacks and the next sync will
    add."""
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
    """The mirror's `.claude.json` as it should be, and the shared keys whose values change.

    The new file has the main file's shared keys, and the function pools `usage` into its
    skillUsage. The function returns None when the file already matches, or when either file is not
    there, since a home with no `.claude.json` has no login to keep."""
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
    """Copy each file under `source` that `into` lacks. For each file that both hold with
    different bytes, return a conflict line that says the mirror's copy is under `kept`."""
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
    """Carry out one step, and say what it did."""
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
    """Write `made` to `target` in one move, by renaming a temporary file over it."""
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
    """What `--check` says when it compares one mirror with the skill `usage` pool. When `usage`
    is None, the function leaves the mirror's skillUsage out. It returns a line for each entry
    that differs, and the skill use that the mirror lacks, which is not drift. When either
    `.claude.json` is missing, `shared` pools nothing, so the function reads no skillUsage."""
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
    """What `--check` finds wrong with one mirror: a line for each entry that differs. The
    function compares the mirror with the pool of every home that providers.json declares,
    as `jroles mirror --check` reads it."""
    try:
        homes = [one.home for one in declared(main.config.parent) if one.home.is_dir()]
    except Refused:
        homes = []
    usage = pool_of(main, tuple(dict.fromkeys([*homes, mirror.home])))
    return review(main, mirror, usage, time.time())[0]


def run(main: Main, mirror: Mirror, usage: dict | None = None) -> list[str]:
    """Make one mirror match the main home, under its own lock and the main home's, and pool
    the skill `usage` into it. Say what changed, or say nothing when nothing did. Each run
    takes the main home's lock, so two runs on two mirrors cannot move the same new name into
    `~/.claude` at once. Each run reads and applies its plan while no other run writes there."""
    if not mirror.home.is_dir():
        raise Refused(f"jroles mirror: {mirror.instance}: {mirror.home} is missing")
    with (mirror.home / LOCK).open("a") as own, (main.home / LOCK).open("a") as shared_lock:
        fcntl.flock(own, fcntl.LOCK_EX)
        fcntl.flock(shared_lock, fcntl.LOCK_EX)
        steps = plan(main, mirror, usage)
        return [line for step in steps for line in apply(main, mirror, step)]


def pool_main(main: Main, usage: dict) -> list[str]:
    """Pool the skill `usage` into `~/.claude.json`, under the main home's lock, and leave
    every other key as it is. Say so, or say nothing when the file already has all of the pooled
    `usage`."""
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
    """`--check`: compare each chosen mirror with the pool. Compare `~/.claude.json` too,
    unless the user asked for one instance. A line that is only `pooling` is not drift. When
    there is no pool because a home's skillUsage is malformed, the function still checks every
    entry other than skillUsage."""
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
