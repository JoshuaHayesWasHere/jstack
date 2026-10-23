"""Where the statechart command finds TLC, the Java that runs it, and Mermaid's renderer. Each is
pinned here, the one place its version is written."""

import hashlib
import os
import shutil
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
