"""A stack's mock API held to the real one, run as a new repo of a Go API and a node client.

`contract_repo` makes a repo from the skeleton as `features/repo-standard/docs/skeleton.md` says
for a repo of several stacks: a go stack `api` over `api/`, whose `pets.Register` adds its routes
to a `net/http` ServeMux as `mux.HandleFunc("GET /pets/{id}", ...)`, with `cmd/serve` serving
them and `cmd/routes` printing them; and a node-vite stack `client` over `client/`, whose browser
tests run on the mock `client/e2e/mock-api.ts`, a TypeScript route list that
`client/e2e/mock-routes.ts` prints. The client's `e2e:` declares the mock, its contract, the
standard's `repo-standard routes` over the two printers, and `api` as its producer.

The cases run the contract alone and `make lint`, which runs it, on the repo as made and on the
repo with one Go route renamed. The module skips where go does not run, or where node cannot run
a TypeScript file.
"""

import os
import shutil
import subprocess

import pytest

from test_go_adapter import needs_go
from test_node_adapter import npm_runs
from test_skeleton_python import INHERITED, SKELETON, STANDARD, git, make, upstream, write


def node_strips_types():
    try:
        done = subprocess.run(
            ["node", "-p", "process.features.typescript"], capture_output=True, text=True
        )
    except OSError:
        return False
    return done.returncode == 0 and done.stdout.strip() in ("strip", "transform")


pytestmark = [
    needs_go,
    pytest.mark.skipif(not npm_runs(), reason="npm is not installed, or does not run"),
    pytest.mark.skipif(not node_strips_types(), reason="node here cannot run a TypeScript file"),
]
upstream = upstream
ADAPTERS = STANDARD / "adapters"
CONTRACT = (
    'python3 -m repo_standard routes --producer "cd api && go run ./cmd/routes"'
    ' --mock "node client/e2e/mock-routes.ts"'
)
STACKS = f"""stacks:
  api:
    adapter: go
    roots: [api]
  client:
    adapter: node-vite
    roots: [client]
    e2e:
      root: client
      script: test:e2e
      mock:
        path: client/e2e/mock-api.ts
        contract: {CONTRACT}
        producer: [api]
"""
PETS = "api/pets/pets.go"
PLANTED = {
    "api/go.mod": "module example.com/api\n\ngo 1.24\n",
    PETS: (
        'package pets\n\nimport "net/http"\n\n'
        "type Mux interface {\n"
        "\tHandleFunc(pattern string, handler func(http.ResponseWriter, *http.Request))\n}\n\n"
        "func Register(mux Mux) {\n"
        '\tmux.HandleFunc("GET /pets", list)\n'
        '\tmux.HandleFunc("GET /pets/{id}", show)\n'
        '\tmux.HandleFunc("POST /pets/{id}/walks", walk)\n}\n\n'
        'func list(w http.ResponseWriter, r *http.Request) { w.Write([]byte("[]")) }\n\n'
        "func show(w http.ResponseWriter, r *http.Request) {"
        ' w.Write([]byte(r.PathValue("id"))) }\n\n'
        "func walk(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusCreated) }\n"
    ),
    "api/cmd/serve/main.go": (
        'package main\n\nimport (\n\t"net/http"\n\n\t"example.com/api/pets"\n)\n\n'
        "func main() {\n\tmux := http.NewServeMux()\n\tpets.Register(mux)\n"
        '\thttp.ListenAndServe(":8080", mux)\n}\n'
    ),
    "api/cmd/routes/main.go": (
        'package main\n\nimport (\n\t"encoding/json"\n\t"net/http"\n\t"os"\n\t"strings"\n\n'
        '\t"example.com/api/pets"\n)\n\n'
        "type route struct {\n"
        '\tMethod string `json:"method"`\n'
        '\tPath   string `json:"path"`\n}\n\n'
        "type recorder []route\n\n"
        "func (r *recorder) HandleFunc("
        "pattern string, _ func(http.ResponseWriter, *http.Request)) {\n"
        '\tmethod, path, _ := strings.Cut(pattern, " ")\n'
        "\t*r = append(*r, route{method, path})\n}\n\n"
        "func main() {\n\tvar found recorder\n\tpets.Register(&found)\n"
        "\tjson.NewEncoder(os.Stdout).Encode(found)\n}\n"
    ),
    "client/package.json": (
        '{"name": "client", "private": true, "engines": {"node": ">=22.18"}, "scripts": '
        '{"check": "node -e \\"\\"", "test": "node -e \\"\\"", "test:e2e": "playwright test"}}\n'
    ),
    "client/e2e/mock-api.ts": (
        "export interface Route {\n  method: string;\n  path: string;\n}\n\n"
        "export const routes: Route[] = [\n"
        "  { method: 'GET', path: '/pets' },\n"
        "  { method: 'GET', path: '/pets/{petId}' },\n"
        "  { method: 'POST', path: '/pets/{petId}/walks' },\n];\n"
    ),
    "client/e2e/mock-routes.ts": (
        "import { routes } from './mock-api.ts';\n\nconsole.log(JSON.stringify(routes));\n"
    ),
}
HELD = "routes: the producer serves each of the mock's 3 routes"
LACKS = "GET /pets/{petId}: the mock answers it, and the producer has no such route"


@pytest.fixture
def contract_repo(tmp_path, upstream):
    """The repo of a Go API and a node client with a mock, and the env its make runs in."""
    root = tmp_path / "repo"
    shutil.copytree(SKELETON, root, ignore=shutil.ignore_patterns("__pycache__", ".cache"))
    for adapter in ("go", "node-vite"):
        shutil.copytree(ADAPTERS / adapter / "scripts", root / "scripts", dirs_exist_ok=True)
    write(root, PLANTED)
    config = (root / ".repo-standard.yml").read_text()
    config = config.replace("layout: [", "layout: [api/, client/, ")
    config = config.replace(
        "  STACK: [pyproject.toml, uv.lock, conftest.py]",
        '  STACK: []\n  API: ["api/**"]\n  CLIENT: ["client/**"]',
    )
    config = config.replace("[scripts/stack.mk]", "[scripts/go.py, scripts/node.py]")
    (root / ".repo-standard.yml").write_text(config + STACKS)
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["REPO_STANDARD_UPSTREAM"] = str(upstream)
    make(root, env, "generate")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start from the skeleton, with an API and a client")
    return root, env


def rename_a_go_route(root):
    text = (root / PETS).read_text()
    assert '"GET /pets/{id}"' in text
    (root / PETS).write_text(text.replace('"GET /pets/{id}"', '"GET /animals/{id}"'))


def contract(root, env):
    """The contract alone, run from the repo's root as `make lint` runs it."""
    done = subprocess.run(
        ["sh", "-c", CONTRACT],
        cwd=root,
        env={**env, "PYTHONPATH": str(STANDARD / "src")},
        capture_output=True,
        text=True,
        timeout=300,
    )
    return done.returncode, done.stdout + done.stderr


def test_the_contract_holds_the_mock_to_the_go_router_and_names_a_route_it_lost(contract_repo):
    root, env = contract_repo
    assert contract(root, env) == (0, f"{HELD}\n")
    rename_a_go_route(root)
    assert contract(root, env) == (1, f"{LACKS}\n")


def test_make_lint_runs_the_contract_and_fails_when_it_fails(contract_repo):
    root, env = contract_repo
    out = make(root, env, "lint")
    assert HELD in out
    assert "errors 0" in out
    rename_a_go_route(root)
    out = make(root, env, "lint", ok=False)
    assert LACKS in out
