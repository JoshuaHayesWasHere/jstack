"""Verification scaffolding: a local stand-in for T3 Code's MCP endpoint.

`launch.sh` starts it and `cleanup.sh` stops it. It listens on a free port of 127.0.0.1 and
keeps everything it is told under the directory it is given:

    port          the port it listens on, written once it is ready
    threads.json  the threads it has, which a drive may edit between passes
    messages.json the items a drive gives a thread, by thread id, which `t3_thread_read` returns:
                  one by its item id, as `jbus word --message` asks, or all of them, as a pass
                  asks when it looks for a usage limit in a failed thread's last run
    calls.jsonl   one line for each tool call jbus made, with its arguments
    wake.jsonl    one line for each wake jbus sent a home thread, with the lines it carried

It answers the tools `jbus.t3.TOOLS` names, and only to the sandbox's token. Any other tool
is the JSON-RPC error T3 Code gives, `t3_thread_configuration` included, which T3 Code folded
into `t3_thread_configure`. That one reads a thread's selection with `threadId` alone and sets
it with `modelSelection`, and a thread keeps its selection under that key in threads.json. A
wake is a `t3_thread_send` whose request id starts `wakes|`, the one list's message
(`jbus.wakes`), and its lines are the items the message names.
"""

from __future__ import annotations

import argparse
import http.server
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jbus.bind import NoLookup
from jbus.t3 import PROTOCOL, TOOLS

SELECTION = {"provider": "claudeAgent", "model": "claude-sandbox"}


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Unknown(Exception):
    """A tool the stand-in does not answer: one jbus does not name, or a new one."""


class Gone(Exception):
    """A thread the stand-in does not have, which T3 Code answers with a failure."""


class Fake:
    def __init__(self, directory: Path, token: str) -> None:
        self.directory, self.token = directory, token
        self.lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("[]\n")

    @property
    def path(self) -> Path:
        return self.directory / "threads.json"

    def threads(self) -> list[dict[str, Any]]:
        return json.loads(self.path.read_text())

    def messages(self) -> dict[str, list[dict[str, Any]]]:
        path = self.directory / "messages.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def keep(self, threads: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(threads, indent=2) + "\n")

    def log(self, name: str, value: Any) -> None:
        with (self.directory / name).open("a") as log:
            log.write(json.dumps({"at": now(), **value}) + "\n")

    def tool(self, name: str, given: dict[str, Any]) -> dict[str, Any]:
        self.log("calls.jsonl", {"tool": name, "arguments": given})
        if name not in TOOLS:
            raise Unknown(name)
        threads = self.threads()
        by_id = {thread["threadId"]: thread for thread in threads}
        if name == "t3_thread_list":
            found = [t for t in threads if given.get("titleContains", "") in t["title"]]
            if given.get("settled") is not None:
                found = [t for t in found if t["settled"] == given["settled"]]
            hidden = ("branch", "modelSelection")
            listed = [{k: v for k, v in t.items() if k not in hidden} for t in found]
            return {"projectId": given.get("projectId"), "threads": listed, "nextCursor": None}
        if name == "t3_thread_read":
            thread = given["threadId"]
            said = self.messages().get(thread, [])
            if "itemId" in given:
                items = [one for one in said if one["itemId"] == given["itemId"]]
                found = by_id.get(thread, {"threadId": thread, "title": "home: demo"})
                return {"thread": found, "recentRuns": [], "items": items}
            return {"thread": by_id[thread], "recentRuns": [], "items": said}
        if name == "t3_thread_configure":
            if given["threadId"] not in by_id:
                raise Gone(given["threadId"])
            thread = by_id[given["threadId"]]
            if "modelSelection" in given:
                thread["modelSelection"] = given["modelSelection"]
                self.keep(threads)
            return {
                "threadId": thread["threadId"],
                "modelSelection": thread.get("modelSelection") or SELECTION,
                "runtimeMode": "full-access",
                "interactionMode": "default",
            }
        if name == "t3_thread_send":
            if given["clientRequestId"].startswith("wakes|"):
                listed = given["message"].split("\n\n")[1].splitlines()
                lines = [line.removeprefix("- ") for line in listed]
                self.log("wake.jsonl", {"thread": given["threadId"], "lines": lines})
            return {"threadId": given["threadId"], "status": "queued"}
        if name == "link_pull_request":
            return {"url": given["url"], "alreadyLinked": False}
        if name == "t3_thread_organize":
            by_id[given["threadId"]]["settled"] = given["action"] == "settle"
            self.keep(threads)
            return {}
        if name != "t3_thread_launch":
            raise Unknown(name)
        made = {
            "threadId": f"mcp:sandbox-thread-{len(threads) + 1}",
            "title": given["title"],
            "status": "running",
            "settled": False,
            "branch": given["workspaceStrategy"].get("branch"),
            "modelSelection": given.get("modelSelection"),
            "createdAt": now(),
            "updatedAt": now(),
        }
        self.keep([*threads, made])
        return {"threadId": made["threadId"]}

    def rpc(self, asked: dict[str, Any]) -> dict[str, Any]:
        if asked["method"] == "initialize":
            return {"protocolVersion": PROTOCOL, "capabilities": {}, "serverInfo": {}}
        if asked["method"] == "tools/list":
            return {"tools": [{"name": name, "inputSchema": {}} for name in TOOLS]}
        try:
            made = self.tool(asked["params"]["name"], asked["params"]["arguments"])
        except Gone as thread:
            failure = {"_tag": "OrchestratorMcpFailure", "code": "thread_not_found"}
            failure["message"] = f"Thread {thread} is no longer available."
            return {"isError": True, "content": [{"type": "text", "text": json.dumps(failure)}]}
        return {"content": [{"type": "text", "text": json.dumps(made)}], "structuredContent": made}


def handler(fake: Fake) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def reply(self, body: Any, status: int = 200) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("mcp-session-id", "sandbox-session")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path == "/health":
                return self.reply({"fake": "verify-jstack", "directory": str(fake.directory)})
            self.reply({}, 404)

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            with fake.lock:
                if self.path != "/mcp":
                    return self.reply({}, 404)
                if self.headers.get("authorization") != f"Bearer {fake.token}":
                    return self.reply({"error": "invalid_mcp_credential"}, 401)
                asked = json.loads(body)
                if "id" not in asked:
                    return self.reply({}, 202)
                try:
                    said = {"result": fake.rpc(asked)}
                except Unknown as tool:
                    said = {"error": {"code": -32602, "message": f"Tool '{tool}' not found"}}
                self.reply({"jsonrpc": "2.0", "id": asked["id"], **said})

        def log_message(self, *_: Any) -> None:
            pass

    return Handler


class Server(NoLookup, http.server.ThreadingHTTPServer):
    """A `ThreadingHTTPServer` that binds without asking DNS for a name of its address
    (`jbus.bind`): on GitHub's macOS runner that reverse lookup of 127.0.0.1 waits in mDNS."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--token", required=True, help="the sandbox's made-up token")
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    server = Server(("127.0.0.1", 0), handler(Fake(args.directory, args.token)))
    (args.directory / "port").write_text(f"{server.server_address[1]}\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
