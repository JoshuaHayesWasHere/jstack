"""The shell jstack hands an agent or runs as a hook runs on macOS's BSD tools as well as on GNU.

The guard reads every `sh` block of the Markdown under `features/` and every shell script in the
tree, and fails on a GNU-only command or flag, with the form that works on both in its message.
`bsd_tools` builds a PATH that has the real tools with these taken away, the one the crew's and
the reviewer's tests start their checks on. Every `sh` block of every tracked .md that bash 5
parses also parses under bash 3.2, the bash macOS runs as /bin/sh, as written and with its
`<placeholder>`s filled in, with a plain word and, one at a time, with words that hold an
apostrophe.
A separator a block reads fields on with `IFS=` is one bash 3.2 splits on, which \\001 and \\177
are not.
"""

import os
import re
import shutil
import subprocess
import sys

import pytest

from testing.paths import REPO

READ_SET = ("*.md", "*.sh", "features/*/project-skill/scripts/")
PERL_TIMEOUT = "`perl -e 'alarm shift; exec @ARGV' <seconds> <command>`"

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
        r"(?<![\w.:])flock\s",
        "macOS has no flock: take the lock in perl, as step 2 of "
        "`features/crew/playbooks/visual-parity.md` does",
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
        r"\brealpath(\s+-q)*\s+-(?!q\b)",
        "BSD realpath takes only -q: `realpath -q <path> || echo <the path as it is>`",
    ),
    (
        r"^(?!.*(2>\s*/dev/null|\|\|)).*\brealpath\s[^|;&)]*(~|\$HOME|\$\{HOME\})"
        r"/\.claude/skills/[\w-]+/\.\./(?!\.\./(templates|playbooks|principles|hooks|source)\b"
        r"|\.\.(?![\w./-]))",
        "BSD realpath fails on a missing path where GNU prints it, and an install places only "
        "templates/, playbooks/, principles/, hooks/ and source beside skills/ "
        "(`features/jinstall/src/jinstall/layout.py`): "
        "`realpath <path> 2> /dev/null || echo missing`, and say what the block does then",
    ),
    (
        r"\bstat\s+(-\w*c|--format|--printf)\b",
        "BSD stat -c is not GNU's: `date -r <file>` for its time, `wc -c < <file>` for its size",
    ),
    (r"(^|[;&|(`]\s*|\$\(\s*|=\S*\s+)timeout\s", f"macOS has no timeout: {PERL_TIMEOUT}"),
    (r"\bsha256sum\b", "macOS has no sha256sum: `shasum -a 256`"),
    (
        r"\"[^\"]*\$\{\w+:?[-+=?][^}]*'",
        "bash 3.2, macOS's sh, opens a quote at an apostrophe in `${name:-words}` inside double "
        "quotes, when it runs and not under `bash -n`: set the words in a line of their own",
    ),
    (
        r"(?<!command -v )\bxdg-open\b",
        "macOS opens a file with `open`: `$(command -v xdg-open || echo open)`",
    ),
]

EXEMPT = {
    "scripts/fresh-host.sh": "its shell runs in an Arch Linux container",
    "features/jgauge/src/jgauge/room.sh": "its GNU forms are in its Linux branch",
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


def on_bsd(tools, *argv):
    env = {**os.environ, "PATH": str(tools)}
    return subprocess.run(argv, env=env, capture_output=True, text=True)


def test_a_date_d_planted_in_a_skill_block_is_found_and_its_portable_form_runs(tmp_path):
    """The planted line fails on macOS's tools, the guard names its line, and the form its
    message gives prints the date a week ago on those same tools."""
    planted = "since=$(date -d '7 days ago' +%F) && echo \"$since\""
    skill = tmp_path / "features" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(f"# demo\n\n```sh\necho one\n{planted}\n```\n")
    tools = bsd_tools(tmp_path / "bsd")
    assert on_bsd(tools, "sh", "-c", planted).returncode == 64
    (found,) = gnu_only(tmp_path)
    where, why = found.split(": ", 1)
    assert where == "features/demo/SKILL.md:5"
    portable = on_bsd(tools, "sh", "-c", re.findall(r"`([^`]+)`", why)[-1])
    assert (portable.returncode, len(portable.stdout.split("-"))) == (0, 3)


def test_a_script_is_read_by_its_shebang_and_its_comments_are_not(tmp_path):
    """A hook with no `.sh` is read by its first line: the guard names the GNU-only line and
    not the comment above it, and the hook fails on macOS's tools until it is rewritten."""
    hook = tmp_path / "features" / "demo" / "hooks" / "stamp"
    hook.parent.mkdir(parents=True)
    hook.write_text('#!/bin/sh\n# readlink -f here\nreadlink -f "$0"\n')
    tools = bsd_tools(tmp_path / "bsd")
    assert on_bsd(tools, "sh", str(hook)).returncode == 64
    assert [line.split(": ")[0] for line in gnu_only(tmp_path)] == ["features/demo/hooks/stamp:3"]
    hook.write_text('#!/bin/sh\n# readlink -f here\nrealpath "$0"\n')
    assert gnu_only(tmp_path) == []
    assert on_bsd(tools, "sh", str(hook)).stdout == f"{hook.resolve()}\n"


def test_a_realpath_of_a_path_an_install_may_not_have_is_found_until_it_is_handled(tmp_path):
    """BSD realpath fails on a missing path where GNU prints it. An install places `templates/`
    beside `skills/` (`jinstall.layout`), so the skills' `T=` line resolves on both, and a planted
    line that reaches past the skill for anything else fails on macOS's tools and is named."""
    planted = 'T=$(realpath ~/.claude/skills/demo/../../nope) && echo "$T"'
    skill = tmp_path / "features" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(f"# demo\n\n```sh\n{planted}\n```\n")
    user = tmp_path / "user"
    (user / "layout" / "skills" / "demo").mkdir(parents=True)
    (user / "layout" / "templates").mkdir()
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / "demo").symlink_to(user / "layout" / "skills" / "demo")
    tools = bsd_tools(tmp_path / "bsd")

    def on_mac(line):
        env = {**os.environ, "PATH": str(tools), "HOME": str(user)}
        return subprocess.run(["sh", "-c", line], env=env, capture_output=True, text=True)

    assert on_mac(planted).returncode == 1
    (found,) = gnu_only(tmp_path)
    assert found.split(": ", 1)[0] == "features/demo/SKILL.md:4"
    handled = planted.replace(")", " 2> /dev/null || echo missing)", 1)
    install = planted.replace("nope", "templates")
    skill.write_text(f"# demo\n\n```sh\n{handled}\n{install}\n```\n")
    assert gnu_only(tmp_path) == []
    assert on_mac(handled).stdout == "missing\n"
    assert on_mac(install).stdout == f"{(user / 'layout' / 'templates').resolve()}\n"


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
        (
            'echo "${boot:-the home\'s line}"',
            'first=${boot:-}\nif [ -z "$first" ]; then first="the home\'s line"; fi',
        ),
        ("R=$(realpath -m ~/x/../y)", "R=$(realpath -q ~/x/../y || echo ~/y)"),
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

BSD_REALPATH = """#!/bin/sh
quiet=
for one in "$@"; do
    case $one in
    -q) quiet=1 ;;
    -*) echo "bsd realpath: no $one" >&2; exit 64 ;;
    esac
done
status=0
for one in "$@"; do
    if [ "$one" = -q ]; then continue; fi
    if [ -e "$one" ]; then
        REAL "$one"
    else
        status=1
        if [ -z "$quiet" ]; then echo "realpath: $one: No such file or directory" >&2; fi
    fi
done
exit "$status"
"""
"""macOS's realpath: it takes only -q, and fails on a path that does not exist where GNU prints
it."""


def bsd_tools(where):
    """A directory of every tool on PATH with macOS's gaps in it: the GNU-only tools are not
    there, the tools whose flags differ refuse the GNU-only flags, exit 64, and say which, and
    realpath fails on a missing path. Put it on PATH in place of the real directories."""
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
            if name == "realpath":
                link.write_text(BSD_REALPATH.replace("REAL", real))
                link.chmod(0o755)
            elif name in REFUSED:
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


BASH3_IMAGE = "bash:3.2"


def bash_version(bash):
    """The major version of a bash, or 0 where it does not run."""
    try:
        said = subprocess.run(
            [bash, "-c", "echo ${BASH_VERSINFO[0]}"], capture_output=True, text=True
        )
    except OSError:
        return 0
    return int(said.stdout.strip() or 0) if said.returncode == 0 else 0


def bash5():
    """A bash of version 4 or later: the one the blocks are first read with."""
    for bash in (shutil.which("bash"), "/opt/homebrew/bin/bash", "/usr/local/bin/bash"):
        if bash and bash_version(bash) >= 4:
            return [bash]
    return None


def bash3(folder):
    """A bash 3.2, the one macOS runs as /bin/sh, with `folder` where it reads it, or None:
    macOS's own /bin/bash, else the `bash:3.2` image where docker already has it."""
    if bash_version("/bin/bash") == 3:
        return ["/bin/bash"], str(folder)
    docker = shutil.which("docker")
    if (
        docker
        and subprocess.run(
            [docker, "image", "inspect", BASH3_IMAGE], capture_output=True
        ).returncode
        == 0
    ):
        return [docker, "run", "--rm", "-v", f"{folder}:/blocks:ro", BASH3_IMAGE, "bash"], "/blocks"
    return None


PLACEHOLDER = re.compile(r"<[a-z][^<>\n]*>")


def filled(block):
    """The block as written, then as an agent fills it in: each placeholder a plain word, then
    one placeholder at a time a user's words or a proof command that hold an apostrophe."""
    yield block
    names = list(dict.fromkeys(PLACEHOLDER.findall(block)))
    for words in [None, *names]:
        yield PLACEHOLDER.sub(
            lambda one, words=words: "a user's words" if one[0] == words else "x", block
        )


def tracked_blocks(root):
    """Each `sh` block of each tracked .md, as `(path:line, text)`, out of the indent of its fence
    as an agent runs it, once for each way it is `filled`."""
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "*.md"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for name in sorted(filter(None, listed.split("\0"))):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text()
        for found in BLOCK.finditer(text):
            at = f"{name}:{text.count(chr(10), 0, found.start(2)) + 1}"
            fence = found.group(1)
            lines = found.group(2).splitlines(keepends=True)
            unfenced = "".join(line.removeprefix(fence) for line in lines)
            for block in filled(unfenced):
                yield at, block


def unparsed(bash, folder):
    """The names of the files in `folder` that `bash -n` refuses, read by one bash."""
    command, inside = bash
    loop = 'for f in "$1"/*; do "$BASH" -n "$f" 2> /dev/null || echo "${f##*/}"; done'
    said = subprocess.run([*command, "-c", loop, "sh", inside], capture_output=True, text=True)
    assert said.returncode == 0, said.stderr
    return set(said.stdout.split())


def unparsed_by_bash3(root, where):
    """Each block bash 5 parses that bash 3.2 does not, as `path:line`."""
    five, three = bash5(), bash3(where)
    if five is None or three is None:
        why = "needs a bash 4 or later and a bash 3.2 (macOS's /bin/bash, or docker's bash:3.2)"
        if os.environ.get("CI") and sys.platform == "darwin":
            pytest.fail(f"{why}: the macOS job is where this guard always runs")
        pytest.skip(why)
    where.mkdir(parents=True, exist_ok=True)
    names = {}
    for at, (name, text) in enumerate(tracked_blocks(root)):
        names[f"{at:05}"] = name
        (where / f"{at:05}").write_text(text)
    refused = unparsed(three, where) - unparsed((five, str(where)), where)
    return sorted({names[file] for file in refused})


def test_every_block_bash_5_parses_parses_under_bash_3_2(tmp_path):
    assert unparsed_by_bash3(REPO, tmp_path / "blocks") == []


MOVED = "line() {\n    cat << 'EOF'\nTEXT\nEOF\n}\nsaid=$(line)\necho \"$said\"\n"


SAID = "said=$(cat << 'EOF'\nTEXT\nEOF\n)\necho \"$said\"\n"


@pytest.mark.parametrize(
    ("planted", "text", "fence"),
    [
        (SAID, "the home's line", ""),
        ("gh pr diff <url> > /dev/null\n" + SAID, "the home's line", ""),
        (SAID, "<what the scope owns>", ""),
        (SAID, "<the answer>", "   "),
    ],
    ids=["apostrophe", "apostrophe-beside-a-placeholder", "placeholder", "placeholder-in-a-list"],
)
def test_a_heredoc_with_an_apostrophe_inside_a_command_substitution_is_found(
    tmp_path, planted, text, fence
):
    """bash 3.2 ends a quote at an apostrophe in the heredoc's body, where bash 5 reads the
    body as text. The apostrophe is in the block, or comes with the words an agent puts in
    place of its placeholder, and neither a placeholder elsewhere that bash 5 does not parse as
    written nor the indent of a block in a list hides it. The guard names that block and no
    other, and the same text with the heredoc moved out of `$( )`, into a function the
    substitution calls, passes."""
    repo = tmp_path / "repo"
    skill = repo / "features" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    planted = planted.replace("TEXT", text)
    moved = planted[: planted.index("said=")] + MOVED.replace("TEXT", text)

    def page(block):
        block = "".join(fence + line for line in f"```sh\n{block}```\n".splitlines(True))
        return f"# demo\n\n```sh\necho one\n```\n\n-  a step\n\n{block}"

    skill.write_text(page(planted))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    assert unparsed_by_bash3(repo, tmp_path / "planted") == ["features/demo/SKILL.md:10"]
    skill.write_text(page(moved))
    assert unparsed_by_bash3(repo, tmp_path / "moved") == []


SEPARATOR = re.compile(r"\b(\w+)=\$\(printf '(\\[0-7]{1,3})'\)")
SPLIT = 'printf "1${SEP}alpha${SEP}tea\\n" | while IFS=$SEP read -r n s a; do echo "[$n][$s]"; done'


def unsplit_by_bash3(root, where):
    """Each separator a block sets with `printf` and a block reads fields on, `IFS=$<name>`,
    that bash 3.2 does not split on, as `path:line`. bash 3.2 keeps \\001 and \\177 as its own
    quoting bytes, and its `read` takes a line with them as one field."""
    lines = list(shell(root))
    found = [
        (f"{path.relative_to(root)}:{at}", setting.group(2))
        for path, at, line in lines
        for setting in SEPARATOR.finditer(line)
        if any(re.search(rf'IFS="?\${setting.group(1)}\b', text) for _, _, text in lines)
    ]
    if not found:
        return []
    three = bash3(where)
    if three is None:
        why = "needs a bash 3.2 (macOS's /bin/bash, or docker's bash:3.2)"
        if os.environ.get("CI") and sys.platform == "darwin":
            pytest.fail(f"{why}: the macOS job is where this guard always runs")
        pytest.skip(why)
    command, inside = three
    where.mkdir(parents=True, exist_ok=True)
    unsplit = []
    for name, byte in found:
        (where / "split").write_text(f"SEP=$(printf '{byte}')\n{SPLIT}\n")
        said = subprocess.run(
            [*command, f"{inside}/split"], capture_output=True, text=True, check=True
        )
        if said.stdout != "[1][alpha]\n":
            unsplit.append(name)
    return unsplit


def test_every_separator_a_block_reads_fields_on_splits_under_bash_3_2(tmp_path):
    assert unsplit_by_bash3(REPO, tmp_path / "split") == []


def test_a_read_on_a_separator_bash_3_2_keeps_whole_is_found(tmp_path):
    """A block that reads fields on \\001 gets one run-on field under bash 3.2, where bash 5
    splits it. The guard names the line that sets it, and passes the same block on \\037."""
    skill = tmp_path / "features" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)

    def page(byte):
        return f"# demo\n\n```sh\nSEP=$(printf '{byte}')\n{SPLIT}\n```\n"

    skill.write_text(page("\\001"))
    assert unsplit_by_bash3(tmp_path, tmp_path / "planted") == ["features/demo/SKILL.md:4"]
    skill.write_text(page("\\037"))
    assert unsplit_by_bash3(tmp_path, tmp_path / "moved") == []
