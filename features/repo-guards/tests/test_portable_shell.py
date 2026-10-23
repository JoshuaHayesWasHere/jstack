"""The shell jstack hands an agent or runs as a hook runs on macOS's BSD tools as well as on GNU.

The guard reads every `sh` block of the Markdown under `features/` and every shell script in the
tree, and fails on a GNU-only command or flag, with the form that works on both in its message.
`bsd_tools` builds a PATH that has the real tools with these taken away, the one the crew's and
the reviewer's tests start their checks on.
"""

import os
import re
import subprocess

import pytest

from testing.paths import REPO

PERL_TIMEOUT = "the perl alarm the merge gate of `features/pr-review/SKILL.md` runs"

GNU_ONLY = [
    (
        r"(?<![\w:])setsid\b(?!\()",
        "macOS has no setsid: start it with "
        "`perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV or die' <command>`",
    ),
    (
        r"\bdate\b[^|;&)]*\s(-d|--date)\b",
        "BSD date has no -d: count the time in perl, "
        "`perl -MPOSIX -e 'print strftime(\"%F\", localtime(time - 7 * 86400))'`",
    ),
    (
        r"\bdate\b[^|;&)]*%N",
        "BSD date has no %N: `perl -MTime::HiRes=time -e 'printf \"%.6f\\n\", time'`",
    ),
    (
        r"\bfind\b[^|;&)]*\s-printf\b",
        "BSD find has no -printf: newest first is `find ... -exec ls -t {} +`",
    ),
    (r"\bnproc\b", "macOS has no nproc: `getconf _NPROCESSORS_ONLN`"),
    (
        r"(?<![\w.:])flock\s+(-\w+\s+)*(?!\$\w+,)\S",
        'macOS has no flock: `perl -MFcntl=:flock -e \'$^F = 255; open my $l, ">>", shift '
        "or die; flock $l, LOCK_EX or die; exec @ARGV or die' <lock file> <command>`",
    ),
    (
        r"\bxargs(\s+-\w+)*\s+(-\w*r\w*|--no-run-if-empty)\b",
        "BSD xargs has no -r and runs nothing on empty input anyway: drop the r",
    ),
    (
        r"\bsed(\s+-\w+)*\s+-\w*i(?=\s|$)",
        "BSD sed -i takes the suffix as its next word: `sed -i.bak ... && rm <file>.bak`, "
        "or write a new file and move it",
    ),
    (r"\bsed(\s+-\w+)*\s+-\w*r\b", "BSD sed has no -r: `sed -E`"),
    (r"\bgrep(\s+-\w+)*\s+-\w*P", "BSD grep has no -P: `grep -E`"),
    (r"\breadlink\s+-\w*f", "use `realpath`, the form the rest of jstack uses"),
    (
        r"\bstat\s+(-\w*c|--format|--printf)\b",
        "BSD stat -c is not GNU's: `date -r <file>` for its time, `wc -c < <file>` for its size",
    ),
    (r"(^|[;&|(`]\s*|\$\(\s*|=\S*\s+)timeout\s", f"macOS has no timeout: {PERL_TIMEOUT}"),
    (r"\bsha256sum\b", "macOS has no sha256sum: `shasum -a 256`"),
    (
        r"(?<!command -v )\bxdg-open\b",
        "macOS opens a file with `open`: `$(command -v xdg-open || echo open)`",
    ),
]

EXEMPT = {
    "scripts/fresh-host.sh": "its shell runs in an Arch Linux container",
    "features/jgauge/src/jgauge/room.sh": "it reads /proc, and its darwin form is jgauge's own",
}

BLOCK = re.compile(r"^([ \t]*)```(?:sh|bash|shell|zsh)[ \t]*\n(.*?)^\1```[ \t]*$", re.M | re.S)
SHEBANG = re.compile(r"#!\s*(/bin/|/usr/bin/env\s+)(sh|bash|zsh|dash)\b")


def markdown(root):
    for path in sorted(root.glob("features/**/*.md")):
        if not {"tests", "evals"} & set(path.relative_to(root).parts):
            yield path


def scripts(root):
    found = {root / "install.sh", *root.glob("scripts/*.sh")}
    for path in root.glob("features/**/*"):
        if {"tests", "evals"} & set(path.relative_to(root).parts) or not path.is_file():
            continue
        with path.open("rb") as file:
            if SHEBANG.match(file.read(64).decode("utf-8", "replace")):
                found.add(path)
    return sorted(path for path in found if path.is_file())


def shell(root):
    """Each line of shell in the tree, as `(path, line number, text)`."""
    for path in markdown(root):
        text = path.read_text()
        for found in BLOCK.finditer(text):
            first = text.count("\n", 0, found.start(2)) + 1
            for at, line in enumerate(found.group(2).splitlines()):
                yield path, first + at, line
    for path in scripts(root):
        if str(path.relative_to(root)) in EXEMPT:
            continue
        for at, line in enumerate(path.read_text().splitlines(), 1):
            if not line.lstrip().startswith("#"):
                yield path, at, line


def gnu_only(root):
    return [
        f"{path.relative_to(root)}:{at}: {why}"
        for path, at, line in shell(root)
        for pattern, why in GNU_ONLY
        if re.search(pattern, line)
    ]


def test_every_line_of_shell_in_the_tree_runs_on_bsd_tools_as_well():
    assert gnu_only(REPO) == []


def test_a_date_d_planted_in_a_skill_block_is_found_with_its_portable_form(tmp_path):
    skill = tmp_path / "features" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# demo\n\n```sh\necho one\nsince=$(date -d '7 days ago' +%F)\n```\n")
    (found,) = gnu_only(tmp_path)
    assert found.startswith("features/demo/SKILL.md:5: BSD date has no -d")
    assert "strftime" in found


def test_a_script_is_read_by_its_shebang_and_its_comments_are_not(tmp_path):
    hook = tmp_path / "features" / "demo" / "hooks" / "stamp"
    hook.parent.mkdir(parents=True)
    hook.write_text('#!/bin/sh\n# GNU\'s readlink -f is not used here\nhere=$(readlink -f "$0")\n')
    assert gnu_only(tmp_path) == [
        "features/demo/hooks/stamp:3: use `realpath`, the form the rest of jstack uses"
    ]


@pytest.mark.parametrize(
    ("gnu", "portable"),
    [
        ("setsid sh -c 'x' &", "perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV or die' sh -c 'x' &"),
        ("now=$(date +%s.%N)", "now=$(perl -MTime::HiRes=time -e 'printf \"%.6f\\n\", time')"),
        ("find . -printf '%T@ %p\\n'", "find . -exec ls -t {} +"),
        ("flock ~/x.lock make", "perl -MFcntl=:flock -e '...' ~/x.lock make"),
        ("ls | xargs -0r git add", "ls | xargs -0 git add"),
        ("sed -i 's/a/b/' f", "sed -i.bak 's/a/b/' f && rm f.bak"),
        ("out=$(timeout 9 sh -c x)", "out=$(perl -e 'alarm shift; exec @ARGV' 9 sh -c x)"),
        ("sha256sum f | cut -c1-12", "shasum -a 256 f | cut -c1-12"),
        ("cores=$(nproc)", "cores=$(getconf _NPROCESSORS_ONLN)"),
    ],
)
def test_each_gnu_form_is_found_and_its_portable_form_is_not(gnu, portable):
    def found(line):
        return [why for pattern, why in GNU_ONLY if re.search(pattern, line)]

    assert found(gnu) and not found(portable)


ABSENT = ("setsid", "nproc", "flock", "timeout", "sha256sum", "xdg-open", "tac")
REFUSED = {
    "date": "-d|--date|--date=*|*%N*",
    "find": "-printf|-fprintf",
    "sed": "-i|-r|--in-place|--in-place=*|--regexp-extended",
    "xargs": "-r|-*r|--no-run-if-empty",
    "readlink": "-f|-*f",
    "stat": "-c|--format=*|--printf=*",
    "grep": "-P|-*P*",
}


def bsd_tools(where):
    """A directory of every tool on PATH with macOS's gaps in it: the GNU-only tools are not
    there, and the tools whose flags differ refuse the GNU-only flags, exit 64, and say which.
    Put it on PATH in place of the real directories."""
    where.mkdir(parents=True, exist_ok=True)
    for folder in os.environ["PATH"].split(os.pathsep):
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            real = os.path.join(folder, name)
            link = where / name
            if name in ABSENT or link.exists() or os.path.isdir(real):
                continue
            if not os.access(real, os.X_OK):
                continue
            if name in REFUSED:
                refuse = f'echo "bsd {name}: no $one" >&2; exit 64'
                link.write_text(
                    "#!/bin/sh\n"
                    f'for one in "$@"; do case $one in {REFUSED[name]}) {refuse} ;; esac; done\n'
                    f'exec {real} "$@"\n'
                )
                link.chmod(0o755)
            else:
                link.symlink_to(real)
    return where


def test_the_bsd_tools_refuse_the_gnu_forms_and_pass_the_rest(tmp_path):
    tools = bsd_tools(tmp_path / "bsd")
    env = {**os.environ, "PATH": str(tools)}

    def runs(command):
        return subprocess.run(["sh", "-c", command], env=env, capture_output=True, text=True)

    assert runs("date -d '7 days ago' +%F").returncode == 64
    assert runs("setsid true").returncode == 127
    assert runs("date +%F").returncode == 0
    assert runs("perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV or die' true").returncode == 0
