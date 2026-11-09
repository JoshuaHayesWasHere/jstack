"""`build(root, files) -> Graph`: the import graph of one npm root, read in python3 alone.

The node-vite adapter's selection reads it, and so may any script that asks which files reach a
changed one, such as a browser job's selection: `Graph.reach` gives each file that imports a set of
files, directly or through others, and `Graph.closure` each file a set of files imports.

A path is a path from the repo's root, as git prints it. `files` is every file of the repo, and the
graph reads the source files under `root`: `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`,
`.cjs`, `.svelte` and `.css`, outside `node_modules`. In each it finds, by pattern and not by a
parser:

- `import ... from 'x'`, `import 'x'`, `export ... from 'x'`, a literal `import('x')`,
  `require('x')` and a CSS `@import 'x'`, in a stylesheet or a `.svelte` file's style.
- `vi.mock('x')`, `vi.doMock`, `vi.importActual` and `vi.importMock`, whose module a test
  depends on.
- A template `import(`./x/${name}.ts`)`, read as the glob `./x/*.ts`, and `import.meta.glob`, given
  one pattern or a list of them, each a glob over the root's files. A `!` pattern is left out.
- In a test, any other string that names a file or a folder of the repo, from the test's folder,
  from the root or from the repo's root, such as a page a test opens with `fs`, which may be
  another stack's. A folder reaches each file under it.

A specifier resolves the way Vite and TypeScript resolve it:

- `./` and `../` from the importing file's folder, and `/` from the root, as Vite reads it.
- `$lib` and `$lib/...` from `src/lib`, SvelteKit's alias, and each alias of `compilerOptions.paths`
  in a `tsconfig*.json` at the root, from its `baseUrl` or the root. A `tsconfig` that `extends` a
  file the setup writes, such as `.svelte-kit/tsconfig.json`, adds nothing, since it is not there.
- A query such as `?raw` or `?url` is cut first.
- The path as written, when it is a file; then with each extension added, which also finds the
  module `x.svelte.ts` of the specifier `x.svelte`; then a `.js` written for its `.ts`; then
  `index` with each extension in the folder.

A bare specifier, a package from `node_modules`, and a name the bundler makes up, such as
SvelteKit's `$app/...`, resolve to nothing: a change to a package changes the lockfile, which
selects the whole stack. An import whose specifier is built at run time in another way is not seen.
"""

from __future__ import annotations

import fnmatch
import json
import posixpath
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

SOURCE = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".svelte", ".css")
EXTENSIONS = (*SOURCE, ".json")
SWAPS = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
SPECIFIER = re.compile(
    r"""(?:\bfrom|\bimport|\bimport\s*\(|\brequire\s*\("""
    r"""|\bvi\.(?:mock|doMock|unmock|doUnmock|importActual|importMock)\s*(?:<[^>]*>)?\s*\()"""
    r"""\s*(['"])([^'"\n]+)\1"""
)
TEMPLATE = re.compile(r"\bimport\s*\(\s*`([^`\n]+)`")
GLOB = re.compile(r"\bimport\.meta\.glob\s*(?:<[^>]*>)?\s*\(\s*(\[[^\]]*\]|'[^'\n]*'|\"[^\"\n]*\")")
STRING = re.compile(r"""(['"`])((?:\.{1,2}/|/)?[\w@$.-]+(?:/[\w@$.\[\]-]*)*)\1""")
PATHLIKE = re.compile(r"\w/\w|\w\.\w+$")
QUOTED = re.compile(r"""(['"])([^'"\n]*)\1""")
LIB = "$lib"


def within(path: str, root: str) -> bool:
    return root == "." or path == root or path.startswith(f"{root}/")


def join(root: str, inner: str) -> str:
    return (
        posixpath.normpath(posixpath.join(root, inner))
        if root != "."
        else posixpath.normpath(inner)
    )


def braces(pattern: str) -> list[str]:
    """The patterns a glob's `{a,b}` stands for, each brace opened in turn."""
    found = re.search(r"\{([^{}]*)\}", pattern)
    if not found:
        return [pattern]
    head, tail = pattern[: found.start()], pattern[found.end() :]
    return [one for part in found[1].split(",") for one in braces(f"{head}{part}{tail}")]


def matcher(patterns: Iterable[str]) -> re.Pattern[str]:
    """One expression for globs in which `**/` matches no folder or any number of them."""
    parts = []
    for pattern in patterns:
        for one in braces(pattern):
            text = fnmatch.translate(one.replace("**/", "\0"))
            parts.append(text.replace("\0", "(?:.*/)?"))
    return re.compile("|".join(parts) or "(?!)")


def jsonc(text: str) -> object:
    """The value of JSON with comments and trailing commas, as a `tsconfig.json` may be written."""
    out, at, quote = [], 0, False
    while at < len(text):
        char = text[at]
        if quote:
            out.append(char)
            if char == "\\":
                out.append(text[at + 1 : at + 2])
                at += 1
            elif char == '"':
                quote = False
        elif char == '"':
            quote = True
            out.append(char)
        elif text.startswith("//", at):
            at = text.find("\n", at)
            at = len(text) if at < 0 else at
            continue
        elif text.startswith("/*", at):
            end = text.find("*/", at + 2)
            at = len(text) if end < 0 else end + 2
            continue
        else:
            out.append(char)
        at += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))


@dataclass(frozen=True)
class Alias:
    """One alias: a pattern that ends in `*` matches a prefix, and its targets take the rest."""

    pattern: str
    targets: tuple[str, ...]

    def bases(self, specifier: str) -> list[str]:
        if self.pattern.endswith("*"):
            head = self.pattern[:-1]
            if not specifier.startswith(head):
                return []
            rest = specifier[len(head) :]
            return [target.replace("*", rest, 1) for target in self.targets]
        return list(self.targets) if specifier == self.pattern else []


def aliases(root: str, read) -> list[Alias]:
    """`$lib`, and the `compilerOptions.paths` of each `tsconfig*.json` at the root, the longest
    first."""
    found = [Alias(LIB, (join(root, "src/lib"),)), Alias(f"{LIB}/*", (join(root, "src/lib/*"),))]
    for name in sorted(read.names(root)):
        if not fnmatch.fnmatch(name, "tsconfig*.json"):
            continue
        try:
            options = jsonc(read.text(join(root, name))).get("compilerOptions") or {}
        except (ValueError, AttributeError):
            continue
        base = join(root, options.get("baseUrl") or ".")
        for pattern, targets in (options.get("paths") or {}).items():
            if isinstance(targets, list):
                found.append(Alias(pattern, tuple(join(base, one) for one in targets)))
    return sorted(found, key=lambda one: -len(one.pattern.rstrip("*")))


@dataclass
class Graph:
    """The files each source file of a root reaches by an import, and the reverse."""

    resolver: Resolver
    imports: dict[str, set[str]] = field(default_factory=dict)
    importers: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add(self, source: str, targets: set[str]) -> None:
        self.imports[source] = targets
        for target in targets:
            self.importers[target].add(source)

    def holds(self, path: str) -> bool:
        """Whether the graph places the path: a source file of the root, or a file one reaches."""
        return path in self.imports or path in self.importers

    def reach(self, paths: Iterable[str]) -> set[str]:
        """The paths, and each file that imports one of them, directly or through others."""
        return _walk(paths, self.importers)

    def closure(self, paths: Iterable[str]) -> set[str]:
        """The paths, and each file they import, directly or through others."""
        return _walk(paths, self.imports)


def _walk(paths: Iterable[str], edges: dict[str, set[str]]) -> set[str]:
    seen = set(paths)
    todo = list(seen)
    while todo:
        for one in edges.get(todo.pop(), ()):
            if one not in seen:
                seen.add(one)
                todo.append(one)
    return seen


class Tree:
    """The repo's files, and what one of them holds, read once."""

    def __init__(self, files: Iterable[str], text) -> None:
        self.files = set(files)
        self.folders: set[str] = set()
        for path in self.files:
            while "/" in path:
                path = posixpath.dirname(path)
                self.folders.add(path)
        self._text = text

    def text(self, path: str) -> str:
        return self._text(path)

    def names(self, folder: str) -> list[str]:
        return [
            posixpath.basename(path)
            for path in self.files
            if (posixpath.dirname(path) or ".") == folder
        ]

    def under(self, folder: str) -> set[str]:
        return {path for path in self.files if path.startswith(f"{folder}/")}


class Resolver:
    """Where a specifier of a file under a root points, as a set of the repo's files."""

    def __init__(self, root: str, tree: Tree) -> None:
        self.root, self.tree = root, tree
        self.aliases = aliases(root, tree)
        self.root_files = sorted(path for path in tree.files if within(path, root))

    def bases(self, specifier: str, source: str) -> list[str]:
        specifier = specifier.split("?")[0]
        if specifier.startswith(("./", "../")) or specifier in (".", ".."):
            return [posixpath.normpath(posixpath.join(posixpath.dirname(source), specifier))]
        if specifier.startswith("/"):
            return [join(self.root, specifier.lstrip("/"))]
        for alias in self.aliases:
            found = alias.bases(specifier)
            if found:
                return found
        return []

    def file(self, base: str) -> str | None:
        if base.startswith("../") or base == "..":
            return None
        files = self.tree.files
        if base in files:
            return base
        for extension in EXTENSIONS:
            if f"{base}{extension}" in files:
                return f"{base}{extension}"
        stem, extension = posixpath.splitext(base)
        for swap in SWAPS.get(extension, ()):
            if f"{stem}{swap}" in files:
                return f"{stem}{swap}"
        for extension in EXTENSIONS:
            if f"{base}/index{extension}" in files:
                return f"{base}/index{extension}"
        return None

    def resolve(self, specifier: str, source: str) -> set[str]:
        found = (self.file(base) for base in self.bases(specifier, source))
        return {one for one in found if one}

    def glob(self, pattern: str, source: str) -> set[str]:
        if pattern.startswith("!"):
            return set()
        bases = self.bases(pattern, source)
        if not bases:
            return set()
        expression = matcher(bases)
        return {path for path in self.root_files if expression.fullmatch(path)}

    def literal(self, text: str, source: str) -> set[str]:
        """The files a string in a test names, from the test's folder, the root, or the repo's
        root."""
        if not PATHLIKE.search(text):
            return set()
        found = set()
        for base in (
            posixpath.normpath(posixpath.join(posixpath.dirname(source), text)),
            join(self.root, text.lstrip("/")),
            posixpath.normpath(text.lstrip("/")),
        ):
            if base.startswith("../") or base in ("..", "."):
                continue
            if base in self.tree.files:
                found.add(base)
            elif base in self.tree.folders:
                found |= self.tree.under(base)
        return found


def imports(text: str, source: str, resolver: Resolver, test: bool) -> set[str]:
    """The files a source file reaches, read from its text."""
    found: set[str] = set()
    for matched in SPECIFIER.finditer(text):
        found |= resolver.resolve(matched[2], source)
    for matched in TEMPLATE.finditer(text):
        found |= resolver.glob(re.sub(r"\$\{[^}]*\}", "*", matched[1]), source)
    for matched in GLOB.finditer(text):
        for pattern in QUOTED.finditer(matched[1]):
            found |= resolver.glob(pattern[2], source)
    if test:
        for matched in STRING.finditer(text):
            found |= resolver.literal(matched[2], source)
    found.discard(source)
    return found


def is_source(path: str) -> bool:
    return path.endswith(SOURCE) and "node_modules" not in path.split("/")


def build(root: str, files: Iterable[str], text, tests=lambda path: False) -> Graph:
    """The graph of the source files under `root`, given every file of the repo and a reader of
    a file's text. `tests` says which files are tests, whose other strings count as paths too."""
    tree = Tree(files, text)
    resolver = Resolver(root, tree)
    graph = Graph(resolver)
    for path in resolver.root_files:
        if is_source(path):
            graph.add(path, imports(tree.text(path), path, resolver, tests(path)))
    return graph
