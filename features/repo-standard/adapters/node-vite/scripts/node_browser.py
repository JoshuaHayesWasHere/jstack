"""`Suite`: a node stack's Playwright tests and the files that reach each, read in python3 alone.

`scripts/node.py select --e2e <json>` asks it which browser tests a change reaches, and the
standard's conformance asks it which test no path reaches. The JSON is the stack's `e2e:` part of
`.repo-standard.yml`: the npm `root` whose `script` runs Playwright, and `every`, `routes` and
`table`, each path from the repo's root.

A spec is a `*.spec.<ext>` file under Playwright's `testDir`, as the config the `script` runs sets
it (`-c <file>`, or else `playwright.config.*` in the root). A test's id is Playwright's test-list
form with the spec's path from the repo's root: `<spec>` runs the whole spec, and
`<spec> > <title>` one test of it. Playwright still runs a setup project the tests depend on.

What reaches a test:

- A URL the spec opens: each literal of a `goto(...)`, where a `${...}` stands for one segment, and
  each URL `routes` declares for the spec. A URL maps to its route's files. In SvelteKit, those are
  the `src/routes/**` folder with a `+page.*`, its `+page*` files, and each `+layout*` from the
  routes folder down to it, where a `(group)` folder adds no segment, and `[x]`, `[[x]]` and
  `[...x]` take one segment, none or one, and any number. In React, the `path:` row of a router
  table (a file that calls `createBrowserRouter`, `createHashRouter`, `createMemoryRouter` or
  `useRoutes`), with the components that row and each row around it name, as `<Name`,
  `Component: Name` or a lazy `import('...')`. Of the routes a URL matches, the most literal wins,
  as the routers pick one.
- Each file those route files import, directly or through others (`node_graph`), where an import
  of names from a barrel, an `index.*` that only re-exports, follows only those names.
- The spec's own local imports, the same way.
- A table spec (`table`) runs one test a row of the array `export`: each `{...}` row of the
  array's literal and of each `<export>.push({...})`. A row's `name:` literal fills the `{name}` of
  `title`, and its `path:` literal is the URL it opens, which alone reaches its test. A change to
  the file that holds the array selects by its lines: a line of a row selects that row, a line of
  another top-level declaration selects the rows that name it, directly or through other
  declarations, a line between rows or of a comment selects nothing, and any other line selects
  the whole spec. A row whose `name:` is not a literal runs only with the whole spec.
- A spec in `every`, such as one that reads every page's built CSS, is reached by any change of the
  app: a path under the stack's roots that is not under `testDir`, not Markdown and no unit test.
- The service worker, `src/service-worker.*` or a `sw.*` or `service-worker.*` file, and each file
  it imports, reach each spec that runs with it: one whose text sets `serviceWorkers: 'allow'`, or
  that sets nothing while no Playwright config of the root sets `serviceWorkers: 'block'`.

A change that every browser test rests on forces the whole stack: the e2e root's `package.json`
and lockfile, a Playwright config (`playwright*.config.*`, or a `*.config.*` that imports
`@playwright/test`) and each file it imports, a file its `webServer` command or the `script`
names, a `mock*` file and the shared fixture (`test.*`, `fixture.*`, `fixtures.*` or `support.*`)
under `testDir`; and, in each root of the stack, `index.html`, `src/app.html`, `src/hooks.*`,
React's `src/main.*` and each router file, `static/**` and `public/**`, and the Vite, Svelte,
Tailwind and PostCSS configs. Global CSS needs no entry: the root layout or `main.*` imports it,
and the graph follows each `@import`, so it reaches every test.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import node_graph
from node_graph import Graph, join, matcher, within
from node_table import Hunks, Row, Table, blank, read_table, spans, table_change

SPEC = re.compile(r"\.spec\.[cm]?[jt]sx?$")
UNIT = re.compile(r"\.test\.[cm]?[jt]sx?$")
APP_FORCING = matcher(
    [
        "index.html",
        "src/app.html",
        "src/hooks.*",
        "src/main.*",
        "static/**",
        "public/**",
        "vite.config.*",
        "svelte.config.*",
        "tailwind.config.*",
        "postcss.config.*",
    ]
)
ROOT_FORCING = matcher(["package.json", "package-lock.json", "npm-shrinkwrap.json"])
PLAYWRIGHT_CONFIG = matcher(["playwright*.config.*"])
ANY_CONFIG = matcher(["*.config.*"])
FIXTURE = matcher(["**/mock*", "**/mock*/**", "**/{test,fixture,fixtures,support}.*"])
WORKER = matcher(
    ["src/service-worker.*", "src/service-worker/**", "**/sw.*", "**/service-worker.*"]
)
ROUTER = re.compile(r"\b(?:createBrowserRouter|createHashRouter|createMemoryRouter|useRoutes)\s*\(")
GOTO = re.compile(r"\bgoto\s*\(\s*(['\"`])([^'\"`\n]*)\1")
CONFIG_FLAG = re.compile(r"(?:^|\s)(?:-c|--config)(?:\s+|=)(['\"]?)([^\s'\"]+)\1")
TEST_DIR = re.compile(r"\btestDir\s*:\s*(['\"`])([^'\"`\n]+)\1")
WEB_SERVER = re.compile(r"\bwebServer\s*:")
COMMAND = re.compile(r"\bcommand\s*:\s*(['\"`])([^'\"`]+)\1")
TOKEN = re.compile(r"[\w./@-]+\.(?:[cm]?[jt]sx?|sh|py)\b")
WORKERS = re.compile(r"\bserviceWorkers\s*:\s*['\"](allow|block)['\"]")
NAMED = re.compile(
    r"\b(?:import|export)\s+(?:type\s+)?(?:[\w$]+\s*,\s*)?\{([^}]*)\}\s*from\s*(['\"])([^'\"\n]+)\2"
)
REEXPORT = re.compile(r"\bexport\s+(?:type\s+)?\{([^}]*)\}\s*from\s*(['\"])([^'\"\n]+)\2")
STAR = re.compile(r"\bexport\s+\*\s+(?:as\s+[\w$]+\s+)?from\s*(['\"])([^'\"\n]+)\1")
BARREL_LINE = re.compile(
    r"^\s*(?:export\s+(?:type\s+)?(?:\{\}|\*(?:\s+as\s+[\w$]+)?)\s+from\s*(['\"])[^'\"\n]+\1;?\s*"
    r"|//.*|/?\*.*|)$"
)
WHOLE_IMPORT = re.compile(
    r"\bimport\s+(?:type\s+)?(?:[\w$]+|\*\s+as\s+[\w$]+)\s*(?:,\s*\{[^}]*\})?\s*from\s*$"
    r"|\bimport\s*\(?\s*$|\bexport\s+\*\s+(?:as\s+[\w$]+\s+)?from\s*$|\b(?:require|mock)\s*\(\s*$"
)
IMPORTED = re.compile(
    r"\bimport\s+(?:type\s+)?([\w$]+)?\s*,?\s*(?:\{([^}]*)\})?\s*from\s*(['\"])([^'\"\n]+)\3"
)
JSX = re.compile(r"<([A-Z][\w$]*)|\bComponent\s*:\s*([A-Z][\w$]*)")
LAZY = re.compile(r"\bimport\s*\(\s*(['\"])([^'\"\n]+)\1")
QUOTED = re.compile(r"""(['"])([^'"\n]+)\1""")
PATH = re.compile(r"\bpath\s*:\s*(['\"`])([^'\"`\n]*)\1")

Reader = Callable[[str], str]


def local_names(listed: str, last: bool = False) -> list[str]:
    """The names of an `{ a, b as c, type d }` list: as the module exports them, or with `last`,
    as the list gives them on."""
    found = []
    for one in listed.split(","):
        one = re.sub(r"^\s*type\s+", "", one).strip()
        if one:
            found.append(one.split(" as ")[-1 if last else 0].strip())
    return found


@dataclass(frozen=True)
class Segment:
    """One segment of a route: `literal`, `param` (one segment), `optional` (none or one) or
    `rest` (any number), with the literal's text."""

    kind: str
    text: str = ""


RANK = {"literal": 3, "param": 2, "optional": 1, "rest": 0}


def svelte_segment(name: str) -> Segment | None:
    if name.startswith("(") and name.endswith(")"):
        return None
    if name.startswith("[[") and name.endswith("]]"):
        return Segment("optional")
    if name.startswith("[...") and name.endswith("]"):
        return Segment("rest")
    if "[" in name:
        return Segment("param")
    return Segment("literal", name)


def react_segment(name: str) -> Segment:
    if name == "*":
        return Segment("rest")
    if name.startswith(":"):
        return Segment("optional" if name.endswith("?") else "param")
    return Segment("literal", name)


def matches(pattern: tuple[Segment, ...], parts: list[str]) -> bool:
    if not pattern:
        return not parts
    head, rest = pattern[0], pattern[1:]
    if head.kind == "rest":
        return any(matches(rest, parts[at:]) for at in range(len(parts) + 1))
    if head.kind == "optional" and matches(rest, parts):
        return True
    if not parts or (head.kind == "literal" and head.text != parts[0]):
        return False
    return matches(rest, parts[1:])


def url_parts(url: str) -> list[str]:
    return [one for one in re.split(r"[?#]", url)[0].split("/") if one]


@dataclass(frozen=True)
class Route:
    """A route of the app: the segments it matches and every file its page rests on."""

    pattern: tuple[Segment, ...]
    files: frozenset[str]

    def rank(self) -> tuple[int, ...]:
        return tuple(RANK[one.kind] for one in self.pattern)


@dataclass
class Test:
    """One browser test: its id, its spec, the URLs it opens, and each file whose change
    reaches it."""

    id: str
    spec: str
    urls: list[str] = field(default_factory=list)
    reach: set[str] = field(default_factory=set)
    row: Row | None = None


class Deps:
    """The import graph of the stack's roots, where an import of names from a barrel goes on to
    the files that export those names and not to the rest of the barrel."""

    def __init__(self, roots: Iterable[str], files: set[str], read: Reader) -> None:
        self.read = read
        self.graphs: list[Graph] = [node_graph.build(root, files, read) for root in roots]
        imports: dict[str, set[str]] = {}
        for graph in self.graphs:
            imports.update(graph.imports)
        self.sources = set(imports)
        self.barrels = {
            path: found for path in imports for found in [self.barrel(path)] if found is not None
        }
        self.edges = {path: self.refine(path, targets) for path, targets in imports.items()}

    def resolve(self, specifier: str, source: str) -> set[str]:
        for graph in self.graphs:
            if within(source, graph.resolver.root):
                return graph.resolver.resolve(specifier, source)
        return set()

    def barrel(self, path: str) -> dict[str, set[str]] | None:
        """Each name a barrel exports and the files it comes from, with `*` for the files of its
        `export * from`, or None when the file is not a barrel."""
        if not re.search(r"(?:^|/)index\.[cm]?[jt]sx?$", path):
            return None
        text = self.read(path)
        if not all(
            BARREL_LINE.match(line) for line in re.sub(r"\{[^}]*\}", "{}", text).split("\n")
        ):
            return None
        found: dict[str, set[str]] = {}
        for matched in REEXPORT.finditer(text):
            for name in local_names(matched[1], last=True):
                found.setdefault(name, set()).update(self.resolve(matched[3], path))
        for matched in STAR.finditer(text):
            found.setdefault("*", set()).update(self.resolve(matched[2], path))
        return found or None

    def refine(self, path: str, targets: set[str]) -> set[str]:
        """The files a file reaches, with each barrel it takes names from replaced by the files of
        those names, unless it also takes the barrel whole."""
        barrels = targets & self.barrels.keys()
        if not barrels:
            return targets
        text = self.read(path)
        named: dict[str, set[str]] = {}
        for matched in NAMED.finditer(text):
            for barrel in self.resolve(matched[3], path) & barrels:
                named.setdefault(barrel, set()).update(local_names(matched[1]))
        whole = {
            barrel
            for found in QUOTED.finditer(text)
            if WHOLE_IMPORT.search(text[max(0, found.start() - 200) : found.start()])
            for barrel in self.resolve(found[2], path) & barrels
        }
        kept = (targets - barrels) | whole | (barrels - named.keys())
        for barrel, wanted in named.items():
            exports = self.barrels[barrel]
            for name in wanted:
                kept |= exports.get(name) or exports.get("*") or {barrel}
        return kept

    def closure(self, paths: Iterable[str]) -> set[str]:
        """The paths, and each file they import, directly or through others."""
        seen = set(paths)
        todo = list(seen)
        while todo:
            for one in self.edges.get(todo.pop(), ()):
                if one not in seen:
                    seen.add(one)
                    todo.append(one)
        return seen


class Runner:
    """How the e2e root runs Playwright: its `script`, the config that script runs, and the
    `testDir` that config sets, from whose folder Playwright reads a test list's paths."""

    def __init__(self, root: str, script: str, files: set[str], read: Reader) -> None:
        self.root, self.script, self.files, self.read = root, script, files, read
        self.configs = self.playwright_configs()
        self.config = self.script_config()
        self.test_dir = self.find_test_dir()

    def scripts(self) -> dict:
        try:
            found = json.loads(self.read(join(self.root, "package.json"))).get("scripts")
        except (ValueError, AttributeError):
            return {}
        return found if isinstance(found, dict) else {}

    def playwright_configs(self) -> list[str]:
        folder = "" if self.root == "." else self.root
        return sorted(
            path
            for path in self.files
            if posixpath.dirname(path) == folder
            and (
                PLAYWRIGHT_CONFIG.fullmatch(posixpath.basename(path))
                or (
                    ANY_CONFIG.fullmatch(posixpath.basename(path))
                    and "@playwright/test" in self.read(path)
                )
            )
        )

    def script_config(self) -> str | None:
        """The Playwright config the `script` runs: the one its `-c` names, or else
        `playwright.config.*` in the root."""
        text = self.scripts().get(self.script)
        flag = CONFIG_FLAG.search(text) if isinstance(text, str) else None
        if flag:
            return join(self.root, flag[2])
        return next(
            (
                one
                for one in self.configs
                if posixpath.basename(one).startswith("playwright.config.")
            ),
            None,
        )

    def find_test_dir(self) -> str:
        if self.config is None or self.config not in self.files:
            return self.root
        folder = posixpath.dirname(self.config) or "."
        found = TEST_DIR.search(self.read(self.config))
        return join(folder, found[2]) if found else folder

    def listed(self, ids: Iterable[str]) -> list[str]:
        """The ids, each a spec's path from the repo's root, as a test list gives them: from
        `testDir`."""
        found = []
        for one in ids:
            spec, *titles = one.split(" > ")
            found.append(" > ".join([posixpath.relpath(spec, self.test_dir), *titles]))
        return found


class Suite:
    """The browser tests of one node stack, what reaches each, and what forces them all."""

    def __init__(self, roots: Iterable[str], e2e: dict, files: Iterable[str], read: Reader):
        self.roots = [posixpath.normpath(one) for one in roots]
        self.root = posixpath.normpath(e2e["root"])
        self.script = e2e["script"]
        self.every = {posixpath.normpath(one) for one in e2e.get("every", ())}
        self.declared = {
            posixpath.normpath(spec): list(urls) for spec, urls in e2e.get("routes", {}).items()
        }
        self.table_rows = {posixpath.normpath(one["file"]): one for one in e2e.get("table", ())}
        self.files = set(files)
        self.read = read
        self.deps = Deps(self.roots, self.files, read)
        self.runner = Runner(self.root, self.script, self.files, read)
        self.configs, self.test_dir = self.runner.configs, self.runner.test_dir
        self.routes: list[Route] = []
        self.routers: set[str] = set()
        self.find_routes()
        self.forcing = self.find_forcing() | self.routers
        self.worker = self.deps.closure(
            path for path in self.app() if WORKER.fullmatch(self.inner(path))
        )
        self.blocked = any(
            found[1] == "block" for one in self.configs for found in WORKERS.finditer(read(one))
        )
        self.specs = sorted(
            path
            for path in self.files
            if within(path, self.test_dir)
            and SPEC.search(path)
            and "node_modules" not in path.split("/")
        )
        self.tables: dict[str, Table] = {}
        self.tests: list[Test] = []
        self.faults: list[str] = []
        for spec in self.specs:
            self.add(spec)
        for named in sorted(self.every | self.declared.keys() | self.table_rows.keys()):
            if named not in self.specs:
                self.faults.append(
                    f"{named}: e2e names it, and it is no spec under {self.test_dir}"
                )

    def inner(self, path: str) -> str:
        root = next((one for one in self.roots if within(path, one)), ".")
        return path if root == "." else path[len(root) + 1 :]

    def app(self) -> list[str]:
        """The files of the app: under the stack's roots, outside `testDir`, and no test."""
        return sorted(path for path in self.files if self.is_app(path))

    def is_app(self, path: str) -> bool:
        return (
            any(within(path, root) for root in self.roots)
            and not within(path, self.test_dir)
            and "node_modules" not in path.split("/")
            and not UNIT.search(path)
            and not SPEC.search(path)
            and not path.endswith(".md")
        )

    def named_files(self, text: str, folder: str) -> set[str]:
        """The files of the repo a command line names, from the folder it runs in."""
        return {
            path
            for token in TOKEN.findall(text)
            for path in [join(folder, token)]
            if path in self.files
        }

    def find_forcing(self) -> set[str]:
        imported = self.deps.closure(self.configs)
        forcing = set(self.configs) | {path for path in imported if not self.is_app(path)}
        for path in self.files:
            if within(path, self.root) and ROOT_FORCING.fullmatch(
                posixpath.relpath(path, self.root)
            ):
                forcing.add(path)
            if within(path, self.test_dir) and not SPEC.search(path):
                inner = posixpath.relpath(path, self.test_dir)
                if FIXTURE.fullmatch(inner):
                    forcing.add(path)
            if any(within(path, root) for root in self.roots) and APP_FORCING.fullmatch(
                self.inner(path)
            ):
                forcing.add(path)
        script = self.runner.scripts().get(self.script)
        forcing |= self.named_files(script if isinstance(script, str) else "", self.root)
        for config in self.configs:
            text = self.read(config)
            server = WEB_SERVER.search(text)
            for command in COMMAND.finditer(text, server.end() if server else len(text)):
                forcing |= self.named_files(command[2], posixpath.dirname(config) or ".")
        return forcing

    def find_routes(self) -> None:
        for root in self.roots:
            self.svelte_routes(join(root, "src/routes"))
        for path in sorted(self.deps.sources):
            text = self.read(path)
            if ROUTER.search(text):
                self.routers.add(path)
                self.react_routes(path, text)

    def svelte_routes(self, folder: str) -> None:
        pages = {
            posixpath.dirname(path)
            for path in self.files
            if within(path, folder) and posixpath.basename(path).startswith("+page")
        }
        for page in sorted(pages):
            names = [] if page == folder else posixpath.relpath(page, folder).split("/")
            pattern = tuple(found for name in names for found in [svelte_segment(name)] if found)
            chain = [folder, *(join(folder, "/".join(names[: at + 1])) for at in range(len(names)))]
            entry = {
                path
                for path in self.files
                if posixpath.dirname(path) in chain
                and (
                    posixpath.basename(path).startswith("+layout")
                    or (
                        posixpath.dirname(path) == page
                        and posixpath.basename(path).startswith("+page")
                    )
                )
            }
            self.routes.append(Route(pattern, frozenset(self.deps.closure(entry))))

    def react_routes(self, path: str, text: str) -> None:
        imported: dict[str, set[str]] = {}
        for found in IMPORTED.finditer(text):
            targets = self.deps.resolve(found[4], path)
            barrel = next(
                (self.deps.barrels[one] for one in targets if one in self.deps.barrels), None
            )
            if found[1]:
                imported[found[1]] = targets
            listed = found[2] or ""
            pairs = zip(local_names(listed), local_names(listed, last=True), strict=True)
            for name, local in pairs:
                exports = barrel or {}
                imported[local] = exports.get(name) or exports.get("*") or targets
        objects = spans(text)
        rows: dict[tuple[int, int], str] = {}
        for found in PATH.finditer(text):
            inside = [one for one in objects if one[0] < found.start() < one[1]]
            if inside:
                rows.setdefault(max(inside), found[2])
        for row in rows:
            entry, full = set(), ""
            for around in sorted(one for one in objects if one[0] <= row[0] and row[1] <= one[1]):
                nested = [
                    one
                    for one in rows
                    if one != around and around[0] < one[0] and one[1] <= around[1]
                ]
                body = blank(text[around[0] : around[1]], around[0], nested)
                for ref in JSX.finditer(body):
                    entry |= imported.get(ref[1] or ref[2], set())
                for lazy in LAZY.finditer(body):
                    entry |= self.deps.resolve(lazy[2], path)
                if around in rows:
                    mine = rows[around]
                    full = mine if mine.startswith("/") else f"{full.rstrip('/')}/{mine}"
            pattern = tuple(react_segment(name) for name in url_parts(full))
            self.routes.append(Route(pattern, frozenset(self.deps.closure(entry))))

    def match(self, url: str) -> list[Route]:
        parts = url_parts(url)
        hits = [route for route in self.routes if matches(route.pattern, parts)]
        best = max((route.rank() for route in hits), default=None)
        return [route for route in hits if route.rank() == best]

    def opened(self, spec: str, text: str) -> list[str]:
        found = []
        for literal in GOTO.finditer(text):
            url = re.sub(r"\$\{[^}]*\}", "x", literal[2])
            if not re.match(r"^[a-z][a-z0-9+.-]*:", url):
                found.append(url if url.startswith("/") else f"/{url}")
        return found + self.declared.get(spec, [])

    def reached(self, test: Test) -> None:
        for url in test.urls:
            routes = self.match(url)
            if not routes and test.spec not in self.every:
                self.faults.append(f"{test.id}: opens {url}, which matches no route of the app")
            for route in routes:
                test.reach |= route.files

    def add(self, spec: str) -> None:
        local = self.deps.closure([spec])
        table = None
        if spec in self.table_rows:
            table = self.table(spec, self.table_rows[spec], local)
            if table is None:
                export = self.table_rows[spec]["export"]
                self.faults.append(f"{spec}: e2e.table names {export}, an array it never declares")
        whole = Test(spec, spec, self.opened(spec, self.read(spec)))
        whole.reach = local - ({table.file} if table and table.file != spec else set())
        self.reached(whole)
        self.tests.append(whole)
        rows = []
        if table is not None:
            self.tables[table.file] = table
            for row in table.rows:
                name = table.id(row)
                if name is None:
                    continue
                test = Test(name, spec, [row.url] if row.url else [], row=row)
                self.reached(test)
                self.tests.append(test)
                rows.append(test)
        if spec in self.every:
            return
        for test in rows:
            if not test.urls:
                self.faults.append(f"{test.id}: its row names no path, so no change reaches it")
        own = whole.reach - {spec} - self.forcing - set(self.specs)
        if table is not None:
            own -= {table.file}
        if not own and not rows and not whole.urls:
            self.faults.append(
                f"{spec}: no path reaches it: it opens no route, imports no local file outside"
                " the forcing set, and e2e.every does not name it"
            )

    def table(self, spec: str, row: dict, local: set[str]) -> Table | None:
        export = row["export"]
        declared = re.compile(
            rf"^(?:export\s+)?(?:const|let|var)\s+{re.escape(export)}\b[^=\n]*=\s*\[", re.M
        )
        for path in [spec, *sorted(local - {spec})]:
            text = self.read(path)
            found = declared.search(text)
            if found:
                spec_text = "" if path == spec else self.read(spec)
                return read_table(
                    spec, path, text, found.end() - 1, export, row["title"], spec_text
                )
        return None

    def allows_worker(self, spec: str) -> bool:
        found = WORKERS.search(self.read(spec))
        return found[1] == "allow" if found else not self.blocked

    def select(
        self, changed: Iterable[str], hunks: Callable[[str], Hunks | None]
    ) -> set[str] | None:
        """The ids of the tests the change reaches, or None when it forces every test."""
        selected: set[str] = set()
        for path in changed:
            if path in self.forcing:
                return None
            if path.endswith(".md"):
                continue
            if path in self.worker:
                selected |= {spec for spec in self.specs if self.allows_worker(spec)}
            if self.is_app(path):
                selected |= self.every & set(self.specs)
            table = self.tables.get(path)
            if table is not None:
                lines = hunks(path)
                selected |= {table.spec} if lines is None else table_change(table, lines)
            selected |= {
                test.id
                for test in self.tests
                if path in test.reach and (table is None or test.spec != table.spec)
            }
        whole = {one for one in selected if " > " not in one}
        return {
            one
            for one in selected
            if one.split(" > ")[0] in self.specs
            and (" > " not in one or one.split(" > ")[0] not in whole)
        }
