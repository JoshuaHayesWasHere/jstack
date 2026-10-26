"""Where the statechart command finds TLC, the Java that runs it, and Mermaid's renderer. Each is
pinned here, the one place its version is written."""

import functools
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

TLA2TOOLS_VERSION = "1.7.4"
TLA2TOOLS_URL = (
    f"https://github.com/tlaplus/tlaplus/releases/download/v{TLA2TOOLS_VERSION}/tla2tools.jar"
)
TLA2TOOLS_SHA256 = "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"

# TLC's workers for a run that checks a rule, unless TLC_WORKERS names another count. Never
# `auto`, which starts one for each core: several such runs at once loaded a 24-core machine to 126.
WORKERS = 2

# The renderer --png runs through npx, at this version and never at npx's latest.
MERMAID_CLI = "@mermaid-js/mermaid-cli@12.0.0"


class NoTlc(Exception):
    pass


@dataclass(frozen=True)
class Tlc:
    jar: str
    java: str


def cached_jar():
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.join(Path.home(), ".cache")
    return Path(cache) / "jstack" / "tla2tools" / TLA2TOOLS_VERSION / "tla2tools.jar"


def tlc_cache():
    """Where `kept` keeps each TLC run's output, one file named by the sha256 of its inputs."""
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.join(Path.home(), ".cache")
    return Path(cache) / "jstack" / "tlc"


def kept(output_of, inputs, done):
    """`output_of()`, kept under the sha256 of `inputs`, each a str or bytes: a later call with
    the same inputs returns the kept output and calls nothing. An output is kept only when
    `done(output)` says the run finished, so a run that failed or was cut short runs again."""
    key = hashlib.sha256()
    for one in inputs:
        key.update(hashlib.sha256(one.encode() if isinstance(one, str) else one).digest())
    path = tlc_cache() / key.hexdigest()
    try:
        return path.read_text()
    except FileNotFoundError:
        pass
    out = output_of()
    if done(out):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, part = tempfile.mkstemp(dir=path.parent, prefix=".tlc-")
        with os.fdopen(fd, "w") as handle:
            handle.write(out)
        os.replace(part, path)
    return out


_jars = {}


def tlc_inputs(found):
    """What a TLC run reads besides its spec and its config: this file, the pinned jar's version
    and sha256, the bytes of the jar it runs, and the first line `java -version` says of the Java
    that runs it."""
    jar = Path(found.jar)
    stat = jar.stat()
    seen = (str(jar), stat.st_mtime_ns, stat.st_size)
    if seen not in _jars:
        _jars[seen] = hashlib.sha256(jar.read_bytes()).hexdigest()
    return [
        Path(__file__).read_bytes(),
        TLA2TOOLS_VERSION,
        TLA2TOOLS_SHA256,
        _jars[seen],
        java_version(found.java),
    ]


@functools.cache
def java_version(java):
    """The first line `java -version` says, past the one a set JAVA_TOOL_OPTIONS adds."""
    said = subprocess.run([java, "-version"], capture_output=True, text=True)
    lines = (said.stderr + said.stdout).splitlines()
    return next((line for line in lines if not line.startswith("Picked up ")), "")


def find_java():
    """JAVA when it is set, else the Java runtime of the jdk4py wheel that `uv run` installs with
    this project, else a java on PATH."""
    if os.environ.get("JAVA"):
        return os.environ["JAVA"]
    try:
        import jdk4py

        return str(jdk4py.JAVA)
    except ImportError:
        return shutil.which("java")


def download_jar(target):
    print(f"Downloading tla2tools.jar {TLA2TOOLS_VERSION} to {target}.", file=sys.stderr)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, part = tempfile.mkstemp(dir=target.parent, prefix=".tla2tools-")
    try:
        with os.fdopen(fd, "wb") as handle, urllib.request.urlopen(TLA2TOOLS_URL, timeout=120) as r:
            shutil.copyfileobj(r, handle)
        with open(part, "rb") as handle:
            got = hashlib.sha256(handle.read()).hexdigest()
        if got != TLA2TOOLS_SHA256:
            raise NoTlc(
                f"{TLA2TOOLS_URL} has sha256 {got}, not the pinned {TLA2TOOLS_SHA256}, so the"
                " command does not use it."
            )
        os.chmod(part, 0o644)
        os.replace(part, target)
    except OSError as e:
        raise NoTlc(
            f"Cannot download tla2tools.jar from {TLA2TOOLS_URL}: {e}. Download it, and set"
            " TLA2TOOLS to its path."
        ) from e
    finally:
        if os.path.exists(part):
            os.remove(part)


def find_tlc(download=True):
    """TLC: TLA2TOOLS when it is set, else tla2tools.jar of the pinned version in the cache,
    downloaded and checked against its sha256 the first time, unless STATECHART_OFFLINE is set."""
    if os.environ.get("TLA2TOOLS"):
        jar = Path(os.environ["TLA2TOOLS"])
        if not jar.exists():
            raise NoTlc(f"TLA2TOOLS is {jar}, which does not exist.")
    else:
        jar = cached_jar()
        if not jar.exists():
            if not download or os.environ.get("STATECHART_OFFLINE"):
                raise NoTlc(
                    f"Cannot find TLC: {jar} does not exist, and STATECHART_OFFLINE is set, so the"
                    f" command does not download it. Download tla2tools.jar from {TLA2TOOLS_URL},"
                    " and set TLA2TOOLS to its path."
                )
            download_jar(jar)
    java = find_java()
    if not java:
        raise NoTlc(
            "Cannot find Java to run TLC. Run the command with uv run --project <the skill's"
            " scripts folder>, which brings Java through jdk4py, or set JAVA to a java binary"
            " (Java 11 or later)."
        )
    return Tlc(jar=str(jar), java=java)


def workers():
    """The count of TLC workers a run that checks a rule takes: TLC_WORKERS, else `WORKERS`."""
    asked = os.environ.get("TLC_WORKERS") or str(WORKERS)
    if not asked.isdigit() or int(asked) < 1:
        raise NoTlc(f"TLC_WORKERS is {asked}, and it must be a count of 1 or more.")
    return asked


def in_test_slot(command):
    """`command` under one of jgauge's machine-wide test slots, so only so many TLC runs go at
    once. A run in a slot already held, a suite's under `jgauge test-slot`, which sets
    JGAUGE_TEST_SLOT, takes no second one, and cannot wait on its own. Where there is no jgauge,
    as where the skill is installed alone, the command runs as it is."""
    jgauge = None if os.environ.get("JGAUGE_TEST_SLOT") else shutil.which("jgauge")
    return [jgauge, "test-slot", "--", *command] if jgauge else command


def rerun_in_test_slot():
    """Run this whole command again under one test slot, in place of this process, so a script
    of many TLC runs waits for a slot once and not once for each run. In a slot held already, or
    with no jgauge, it does nothing and the command goes on."""
    command = [sys.executable, *sys.orig_argv[1:]]
    held = in_test_slot(command)
    if held is not command:
        sys.stdout.flush()
        os.execv(held[0], held)
