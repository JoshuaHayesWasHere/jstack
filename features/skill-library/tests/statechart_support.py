"""What the statechart tests share: the port's package, loaded from the skill's `scripts/`
folder, the helpers that run its four commands as a user runs them, and the specs, charts and
mappings that more than one test reads. The tests are pstack's statechart tests, one for one, in
`test_statechart_charts.py`, `test_statechart_specs.py` and `test_statechart_runs.py`."""

import importlib
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from testing.paths import REPO

SCRIPTS = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"


PACKAGE = SCRIPTS / "statechart"
SRC = PACKAGE.parent


sys.path.insert(0, str(SRC))
lib = importlib.import_module("statechart.lib")
statechart_tools = importlib.import_module("statechart.tools")
ChartError = lib.ChartError
parse_dot = lib.parse_dot
parse_mermaid = lib.parse_mermaid
parse_traces = lib.parse_traces
parse_value = lib.parse_value
rule_sentences = lib.rule_sentences
state_key = lib.state_key
tlc_output_warning = lib.tlc_output_warning
uncited_conditions = lib.uncited_conditions


FIXTURES = Path(__file__).parent / "statechart"


MODULES = {
    "statechart": "statechart.cli",
    "chart-to-tla": "statechart.chart_to_tla",
    "tlc-to-chart": "statechart.tlc_to_chart",
    "compare-charts": "statechart.compare_charts",
}


TIMED = re.compile(r"^(  TLC ran \d+ times? in )\d+\.\d s\.$", re.M)


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def edges(region):
    return sorted(f"{t['from']} -> {t['to']} : {t['label']}" for t in region["transitions"])


def run_env(env=None):
    env = env or {}
    merged = {**os.environ, **env}
    merged["PYTHONPATH"] = os.pathsep.join(filter(None, [env.get("PYTHONPATH"), str(SRC)]))
    return merged


def node(script, args, cwd, env=None):
    """Runs one command as `node()` ran pstack's scripts: the time TLC took reads N s."""
    r = subprocess.run(
        [sys.executable, "-m", MODULES[script], *args],
        cwd=cwd,
        env=run_env(env),
        capture_output=True,
        text=True,
    )
    r.stdout = TIMED.sub(r"\1N s.", r.stdout)
    return r


def write(path, text, mode=None):
    Path(path).write_text(text, encoding="utf-8")
    if mode is not None:
        os.chmod(path, mode)


def read(path):
    return Path(path).read_text(encoding="utf-8")


DONE = "Model checking completed. No error has been found.\n"


EVALUATION_ERROR = """Error: Invariant NoLost is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
s = "Idle"

State 2: <Lose line 4, col 9 to line 4, col 33 of module F>
s = "Lost"

Error: TLC threw an unexpected exception.
This was probably caused by an error in the spec or model.

Error: The behavior up to this point is:
State 1: <Initial predicate>
s = "Idle"

State 2: <Save line 5, col 9 to line 5, col 35 of module F>
s = "Saving"

3 states generated, 3 distinct states found, 0 states left on queue.
"""


def tlc_threw(cls, message):
    return f"""Error: Evaluating invariant Small failed.
Index 123 out of bounds for length 4
Error: TLC threw an unexpected exception.
This was probably caused by an error in the spec or model.
See the User Output or TLC Console for clues to what happened.
The exception was a {cls}
: {message}
Error: The error occurred when TLC was evaluating the nested
expressions at the following positions:
    The error call stack is empty.
"""


SMALL_BROKEN = (
    "Error: Invariant Small is violated.\nError: The behavior up to this point is:\n"
    "State 1: <Initial predicate>\nx = 0\n\n"
)


STOPPED_EARLY = "9 states generated, 9 distinct states found, 4 states left on queue.\n"


DOOR = """stateDiagram-v2
  state Door {
    [*] --> Locked
    Locked --> Unlocked : tap unlock
    Unlocked --> Locked : tap lock
    --
    [*] --> Closed
    Closed --> Open : open the door
    Open --> Closed : close the door
  }
  [*] --> Door"""


def flat_door(extra=()):
    return "\n".join(
        [
            "stateDiagram-v2",
            '  state "Locked | Closed" as L_C',
            '  state "Locked | Open" as L_O',
            '  state "Unlocked | Closed" as U_C',
            '  state "Unlocked | Open" as U_O',
            "  [*] --> L_C",
            "  L_C --> U_C : tap unlock",
            "  U_C --> L_C : tap lock",
            "  L_O --> U_O : tap unlock",
            "  L_C --> L_O : open the door",
            "  L_O --> L_C : close the door",
            "  U_C --> U_O : open the door",
            "  U_O --> U_C : close the door",
            *extra,
        ]
    )


LAMP = """stateDiagram-v2
  state "Lamp" as lamp {
    state "Power" as power {
      [*] --> Off
      Off --> On : flip the switch
      On --> Off : flip the switch
    }
    --
    state "Bulb" as bulb {
      [*] --> Dark
      Dark --> Lit : warm up [when the<br/>power is on]
      %% when On
      Lit --> Dark : cool down [when the power is off]
      %% when not On
    }
  }
  %% never LitWhileOff: Off & Lit -- The bulb is never lit while the power is off.
"""


SWITCH_LAMP = """stateDiagram-v2
  state "Lamp" as lamp {
    state "Power" as power {
      [*] --> Off
      Off --> On : flip the switch
      On --> Off : flip the switch
    }
    --
    state "Bulb" as bulb {
      [*] --> Dark
      Dark --> Lit : flip the switch [when the power is off]
      %% when Off
      Lit --> Dark : flip the switch
    }
  }
"""


FROM_SPEC_USAGE = (
    "statechart from-spec SPEC.tla [--config FILE] [--fixed FIXED.tla [--fixed-config FILE] |"
    " --against AGREED.tla [--against-config FILE]] [--label TEXT] [--map FILE] [--expect-broken"
    " RULE]... [--title TEXT] [--out DIR] [--png]"
)


FROM_CHART_USAGE = (
    "statechart from-chart CHART.mmd [--module NAME] [--expect-broken RULE]... [--title TEXT]"
    " [--out DIR] [--png]"
)


def no_tlc(tmp_path):
    """pstack's TLA2TOOLS="" and JAVA="": no TLC set, none in an empty cache, and no download."""
    cache = tmp_path / "empty-cache"
    cache.mkdir(exist_ok=True)
    env = {"TLA2TOOLS": "", "JAVA": "", "STATECHART_OFFLINE": "1", "XDG_CACHE_HOME": str(cache)}
    jar = cache / "jstack" / "tla2tools" / "1.7.4" / "tla2tools.jar"
    message = (
        f"Cannot find TLC: {jar} does not exist, and STATECHART_OFFLINE is set, so the command"
        " does not download it. Download tla2tools.jar from"
        " https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar, and set"
        " TLA2TOOLS to its path.\n"
    )
    return env, message


try:
    TOOLS = statechart_tools.find_tlc(download=False)
except statechart_tools.NoTlc:
    TOOLS = None


needs_tlc = pytest.mark.skipif(TOOLS is None, reason="cannot find TLC")


def tlc(directory, name):
    """TLC on NAME.tla with NAME.cfg in `directory`, with the graph dumped to NAME.dot and the
    output in NAME.out. Its metadir and java.io.tmpdir are its own, so parallel tests share
    nothing."""
    meta = Path(tempfile.mkdtemp(prefix="tlc-", dir=directory))
    r = subprocess.run(
        [
            TOOLS.java,
            f"-Djava.io.tmpdir={meta}",
            "-cp",
            TOOLS.jar,
            "tlc2.TLC",
            "-metadir",
            str(meta / "meta"),
            "-deadlock",
            "-continue",
            "-dump",
            "dot,actionlabels",
            f"{name}.dot",
            "-config",
            f"{name}.cfg",
            f"{name}.tla",
        ],
        cwd=directory,
        capture_output=True,
        text=True,
    )
    write(Path(directory) / f"{name}.out", r.stdout)
    return r


SYNC_STORY = """## 1. Offline | Synced

Rule broken: You never see "Synced" while you are offline.
This is the only way to get here in the model.

0. Start: Online | Synced
1. The network drops. Now: Offline | Waiting to sync
2. The server confirms. Now: Offline | Synced
"""


def pay(name, charge):
    return f"""---- MODULE {name} ----
EXTENDS Naturals
VARIABLES screen, charges
vars == <<screen, charges>>
Init == screen = "Cart" /\\ charges = 0
Pay == screen = "Cart" /\\ screen' = "Paying" /\\ UNCHANGED charges
Charge == {charge}
Refund == charges = 2 /\\ charges' = 1 /\\ screen' = "Refunded"
Next == Pay \\/ Charge \\/ Refund
Spec == Init /\\ [][Next]_vars
NoDoubleCharge == charges <= 1
====
"""


PAY_MAP = """reader_actions = ["Pay"]


def state(v):
    return v["screen"] + ["", ", charged", ", charged twice"][v["charges"]]


def step(action):
    return {
        "Pay": "you pay",
        "Charge": "the bank charges you",
        "Refund": "the bank refunds you",
    }.get(action, "")


def cause():
    return "each charge request charges again"
"""


CHARGE_AGAIN = 'screen = "Paying" /\\ charges < 2 /\\ charges\' = charges + 1 /\\ UNCHANGED screen'


def status_of(chart):
    names = {
        m[2]: m[1].replace("<br/>", " ")
        for m in re.finditer(r'^ {2}state "([^"]+)" as (s\d+)$', chart, re.M)
    }
    return {names.get(m[1]): m[2] for m in re.finditer(r"^ {2}class (s\d+) (\w+)$", chart, re.M)}


def edit(name, fixed):
    return (
        f"""---- MODULE {name} ----
VARIABLES s, flashed
vars == <<s, flashed>>
Init == s = "Idle" /\\ flashed = FALSE
Tap == s = "Idle" /\\ s' = "Saving" /\\ UNCHANGED flashed
Lose == s = "Saving" /\\ s' = "Lost edit" /\\ UNCHANGED flashed
Flash == s = "Saving" /\\ s' = "Flash" /\\ flashed' = {"TRUE" if fixed else "FALSE"}
"""
        + 'Back == s \\in {"Lost edit", "Flash"} /\\ s\' = "Idle" /\\ flashed\' = FALSE\n'
        + f"""Next == Tap \\/ Flash \\/ Back{"" if fixed else " \\/ Lose"}
Spec == Init /\\ [][Next]_vars
NoLostEdit == s # "Lost edit" /\\ ~(s = "Flash" /\\ flashed)
====
"""
    )


def flat_edges(mmd):
    names = {}
    members = {}
    box = None

    def said(s):
        return s.replace("<br/>", " ")

    for line in mmd.split("\n"):
        opens = re.fullmatch(r' {2}state "([^"]+)" as (g\d+) \{', line)
        state = re.fullmatch(r' +state "([^"]+)" as (s\d+)', line)
        if opens:
            box = {"id": opens[2], "name": said(opens[1])}
            members[box["id"]] = []
        elif line == "  }":
            box = None
        elif state:
            names[state[2]] = f"{box['name']}: {said(state[1])}" if box else said(state[1])
            if box:
                members[box["id"]].append(state[2])
    return sorted(
        f"{names.get(f)} --> {names.get(m[2])} : {m[3]}"
        for m in re.finditer(r"^ {2}([gs]\d+) --> (s\d+) : (.*)$", mmd, re.M)
        for f in members.get(m[1], [m[1]])
    )


def save(name, code):
    retries = ", retries" if code else ""
    init_note = ", rev |-> 0] /\\ retries = 0" if code else "]"
    stored_note = ", rev |-> 1] /\\ UNCHANGED retries" if code else "]"
    reset = " /\\ retries' = 0" if code else ""
    steps = (
        """Retry == screen = "Saving" /\\ retries = 0 /\\ retries' = 1 /\\ UNCHANGED <<screen, \
note>>
TimeOut == screen = "Saving" /\\ retries = 1 /\\ screen' = "Saved" /\\ UNCHANGED <<note, retries>>
Next == Save \\/ Retry \\/ Confirm \\/ TimeOut \\/ Edit"""
        if code
        else "Next == Save \\/ Confirm \\/ Edit"
    )
    return (
        f"""---- MODULE {name} ----
VARIABLES screen, note{retries}
vars == <<screen, note{retries}>>
Init == screen = "Editing" /\\ note = [text |-> "draft"{init_note}
Save == screen = "Editing" /\\ screen' = "Saving" /\\ UNCHANGED <<note{retries}>>
Confirm == screen = "Saving" /\\ screen' = "Saved" /\\ note' = [text |-> "stored"{stored_note}
Edit == screen = "Saved" /\\ screen' = "Editing" /\\ note' = [note EXCEPT !.text = "draft"]{reset}
{steps}
Spec == Init /\\ [][Next]_vars
"""
        + 'TypeOK == screen \\in {"Editing", "Saving", "Saved"}\n'
        + """\\* You never see "Saved" while the note is still a draft.
NoFalseSaved == ~(screen = "Saved" /\\ note.text = "draft")
====
"""
    )


SAVE_CODE_MAP = """reader_actions = ["Save", "Edit"]


def state(v):
    return f'{v["screen"]}, {v["note"]["text"]}'


def step(a):
    return {
        "Save": "you press Save",
        "Retry": "the app tries again",
        "Confirm": "the server stores the note",
        "TimeOut": "the save times out",
        "Edit": "you edit the note",
    }.get(a, "")


def cause():
    return "the app stops after one retry and shows Saved anyway"
"""


DOOR_SPEC = """---- MODULE Door ----
VARIABLES where, reply
vars == <<where, reply>>
Init == where = "Open" /\\ reply = "none"
Ask == reply = "none" /\\ reply' = "pending" /\\ UNCHANGED where
Answer == where = "Open" /\\ reply = "pending" /\\ reply' = "shown" /\\ UNCHANGED where
Drop == where = "Closed" /\\ reply = "pending" /\\ reply' = "lost" /\\ UNCHANGED where
Close == where = "Open" /\\ where' = "Closed" /\\ UNCHANGED reply
Reopen == where = "Closed" /\\ where' = "Open" /\\ (reply' = reply \\/ (reply = "pending" /\\ \
reply' = "shown"))
Next == Ask \\/ Answer \\/ Drop \\/ Close \\/ Reopen
Spec == Init /\\ [][Next]_vars
NoLostReply == reply # "lost"
NoShownWhileClosed == ~(where = "Closed" /\\ reply = "shown")
====
"""


DOOR_MAP = """W = {"Open": "Window open", "Closed": "Window closed"}
R = {
    "none": "no question",
    "pending": "reply on its way",
    "shown": "reply shown",
    "lost": "reply lost",
}
region_names = ["Where you are", "Your reply"]


def state(v):
    return f"{W[v['where']]}: {R[v['reply']]}"


def step(a):
    return {
        "Ask": "you ask",
        "Answer": "the reply arrives",
        "Drop": "the app drops the reply",
        "Close": "you close the window",
        "Reopen": "you open the window",
    }[a]
"""


def run_door(directory, mapping):
    write(directory / "Door.tla", DOOR_SPEC)
    write(directory / "Door.map.py", mapping)
    out = directory / "Door-statechart"

    def shown(f):
        return read(out / f).replace("<br/>", " ")

    def run(rule):
        write(directory / "Door.cfg", f"SPECIFICATION Spec\nINVARIANT {rule}\n")
        r = node("statechart", ["from-spec", "Door.tla", "--expect-broken", rule], directory)
        assert r.returncode == 0, r.stdout + r.stderr
        every = out / "tlc" / "regions-all.mmd"
        return {
            "stdout": r.stdout,
            "chart": shown("chart.mmd"),
            "every": shown("tlc/regions-all.mmd") if every.exists() else None,
            "bug": shown("bug-1.mmd"),
            "out": out,
        }

    return run


GROUP_MAP = f"""{DOOR_MAP}

def group(v):
    return {{
        "none": "Nothing to show",
        "pending": "Waiting",
        "shown": "Reply shown",
        "lost": "Reply shown",
    }}[v["reply"]]


group_colors = {{"Reply shown": "#d1f2eb", "Waiting": None, "Never drawn": "#ffffff"}}
"""


def order(name, note, charge):
    return f"""---- MODULE {name} ----
EXTENDS Naturals
VARIABLES screen, charges, note
vars == <<screen, charges, note>>
Init == screen = "Cart" /\\ charges = 0 /\\ note = 0
Pay == screen = "Cart" /\\ screen' = "Paying" /\\ note' = {note} /\\ UNCHANGED charges
Charge == screen = "Paying" /\\ charges < 2 /\\ {charge}
Next == Pay \\/ Charge
Spec == Init /\\ [][Next]_vars
NoDoubleCharge == charges <= 1
====
"""


CHARGE_AGAIN_NOTED = "charges' = charges + 1 /\\ UNCHANGED <<screen, note>>"


CHARGE_ONCE = (
    "IF charges = 0 THEN charges' = 1 /\\ UNCHANGED <<screen, note>> ELSE screen' = \"Paid\" /\\"
    " UNCHANGED <<charges, note>>"
)


CHARGE_FIRST_ONLY = "charges = 0 /\\ charges' = 1 /\\ UNCHANGED <<screen, note>>"


def notify(name, muted_arrive):
    return (
        f"""---- MODULE {name} ----
EXTENDS Naturals
VARIABLES screen, muted, banner, badge, missed, msgs, syncs
vars == <<screen, muted, banner, badge, missed, msgs, syncs>>
Init == screen = "Inbox" /\\ muted = FALSE /\\ banner = FALSE /\\ badge = FALSE
        /\\ missed = FALSE /\\ msgs = 0 /\\ syncs = 0
OpenThread == screen = "Inbox" /\\ screen' = "Thread" /\\ UNCHANGED <<muted, banner, badge, \
missed, msgs, syncs>>
"""
        + 'OpenSettings == screen \\in {"Inbox", "Thread"} /\\ screen\' = "Settings" /\\ UNCHANGED'
        " <<muted, banner, badge, missed, msgs, syncs>>\n"
        + 'TapBack == screen \\in {"Thread", "Settings"} /\\ screen\' = "Inbox" /\\ UNCHANGED'
        " <<muted, banner, badge, missed, msgs, syncs>>\n"
        + f"""Mute == screen = "Settings" /\\ ~muted /\\ muted' = TRUE /\\ UNCHANGED <<screen, \
banner, badge, missed, msgs, syncs>>
Refresh == syncs < 2 /\\ syncs' = syncs + 1 /\\ UNCHANGED <<screen, muted, banner, badge, missed, \
msgs>>
Arrive == msgs < syncs /\\ msgs' = msgs + 1
          /\\ (IF muted THEN {muted_arrive} ELSE banner' = TRUE /\\ UNCHANGED <<badge, missed>>)
          /\\ UNCHANGED <<screen, muted, syncs>>
Next == OpenThread \\/ OpenSettings \\/ TapBack \\/ Mute \\/ Refresh \\/ Arrive
Spec == Init /\\ [][Next]_vars
NeverMissed == ~missed
NoBannerOnThread == ~(banner /\\ screen = "Thread")
====
"""
    )


def write_lamp(directory, label="you flip the switch"):
    write(
        directory / "Lamp.tla",
        "---- MODULE Lamp ----\nVARIABLE on\nInit == on = FALSE\nOn == on' = TRUE\n"
        "Off == on' = FALSE\nSpec == Init /\\ [][On \\/ Off]_on\n====\n",
    )
    write(directory / "Lamp.cfg", "SPECIFICATION Spec\n")
    write(
        directory / "Lamp.map.py",
        f'def state(v):\n    return "On" if v["on"] else "Off"\n\n\n'
        f'def step():\n    return "{label}"\n',
    )
    return directory / "Lamp-statechart"


def write_slow_pay(directory, ticks, paid="Paid"):
    write(
        directory / "Pay.tla",
        f"""---- MODULE Pay ----
EXTENDS Naturals
VARIABLES screen, charges, ticks
vars == <<screen, charges, ticks>>
Init == screen = "Cart" /\\ charges = 0 /\\ ticks = 0
TapPay == screen = "Cart" /\\ screen' = "Paying" /\\ UNCHANGED <<charges, ticks>>
Charge == screen = "Paying" /\\ charges < 2 /\\ charges' = charges + 1 /\\ UNCHANGED <<screen, \
ticks>>
Done == screen = "Paying" /\\ charges > 0 /\\ screen' = "{paid}" /\\ UNCHANGED <<charges, ticks>>
Tick == ticks < {ticks} /\\ ticks' = ticks + 1 /\\ UNCHANGED <<screen, charges>>
Spec == Init /\\ [][TapPay \\/ Charge \\/ Done \\/ Tick]_vars
ChargedAtMostTwice == charges <= 2
====
""",
    )
    write(directory / "Pay.cfg", "SPECIFICATION Spec\nINVARIANT ChargedAtMostTwice\n")
    write(
        directory / "Pay.map.py",
        """def state(v):
    return v["screen"]


def step(a):
    return {
        "TapPay": "you tap Pay",
        "Charge": "the charge goes through",
        "Done": "the receipt shows",
    }.get(a, "")
""",
    )
    return directory / "Pay-statechart"


class Run:
    """One statechart run in the background, in its own process group, as pstack's startRun:
    its stderr is read as it comes, and done() waits for its exit."""

    def __init__(self, cwd, args=("from-spec", "Pay.tla"), wrap=(), env=None):
        self.child = subprocess.Popen(
            [*wrap, sys.executable, "-m", "statechart.cli", *args],
            cwd=cwd,
            env=run_env(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self.stderr = ""
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        self.stderr = self.child.stderr.read()
        self.child.wait()

    def done(self):
        self.reader.join()
        return self.child.returncode, self.stderr

    def kill_group(self):
        try:
            os.killpg(self.child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def until(ready, seconds=90):
    deadline = time.monotonic() + seconds
    while not ready():
        assert time.monotonic() < deadline, "waited too long"
        time.sleep(0.02)


def own_tmp(directory, name):
    tmp = directory / name
    tmp.mkdir()
    return tmp


def tlc_started(tmp):
    return any(f.startswith("tlc-") for f in os.listdir(tmp))


def staged(directory):
    return [f for f in os.listdir(directory) if f.startswith(".")]


def changed_mid_run(directory, wrap=(), env=None):
    env = env or {}
    out = write_slow_pay(directory, 20000)
    tmp = own_tmp(directory, "tmp-a")
    first = Run(directory, wrap=wrap, env={**env, "TMPDIR": str(tmp)})
    second = None
    try:
        until(lambda: tlc_started(tmp))
        time.sleep(0.5)
        write_slow_pay(directory, 20000, "Receipt")
        second = Run(directory, wrap=wrap, env={**env, "TMPDIR": str(own_tmp(directory, "tmp-b"))})
        paid_status, paid_stderr = first.done()
        receipt_status, receipt_stderr = second.done()
    finally:
        first.kill_group()
        if second:
            second.kill_group()
    assert receipt_status == 0, receipt_stderr
    assert paid_status == 2, paid_stderr
    m = re.fullmatch(
        r"Pay\.tla changed while this run read it, so the run left Pay-statechart as it was\. Run"
        r" the command again\. The files that this run wrote are in (tmp-a\/statechart-\w+)\.\n",
        paid_stderr,
    )
    assert m, paid_stderr
    assert re.search(r"Paid", read(directory / m[1] / "chart.mmd"))
    chart = read(out / "chart.mmd")
    assert re.search(r"Receipt", chart)
    assert not re.search(r"Paid", chart)
    assert staged(directory) == []


UNSHARE = ["unshare", "--user", "--map-root-user", "--pid", "--fork", "--mount-proc"]


HIDE_PID_NAMESPACE = """#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>
ssize_t readlink(const char *path, char *buf, size_t size) {
  static ssize_t (*real)(const char *, char *, size_t);
  if (!real) real = dlsym(RTLD_NEXT, "readlink");
  if (path && strcmp(path, "/proc/self/ns/pid") == 0) { errno = EIO; return -1; }
  return real(path, buf, size);
}
"""


def compiled(folder, source, name):
    """A shared library built from `source` in `folder`, or None when the machine cannot build
    it."""
    if not shutil.which("cc"):
        return None
    write(folder / f"{name}.c", source)
    so = folder / f"{name}.so"
    cc = subprocess.run(
        ["cc", "-shared", "-fPIC", "-o", str(so), str(folder / f"{name}.c"), "-ldl"],
        capture_output=True,
    )
    return str(so) if cc.returncode == 0 else None


FAIL_RENAMES = """#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static size_t hits;
int rename(const char *from, const char *to) {
  static int (*real)(const char *, const char *);
  if (!real) real = dlsym(RTLD_NEXT, "rename");
  const char *base = strrchr(to, '/'), *fails = getenv("RENAME_FAILS");
  const char *cannot = getenv("RENAME_CANNOT");
  base = base ? base + 1 : to;
  if (cannot && strstr(base, "shared")) {
    errno = strcmp(cannot, "EXDEV") == 0 ? EXDEV : access(to, F_OK) == 0 ? EISDIR : ENOSYS;
    return -1;
  }
  if (fails && strcmp(base, "shared") == 0 && hits < strlen(fails)) {
    errno = fails[hits++] == 'N' ? ENOTEMPTY : EIO;
    return -1;
  }
  return real(from, to);
}
"""
