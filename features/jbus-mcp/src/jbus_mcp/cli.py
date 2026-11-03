"""The one entry point: `jbus-mcp serve`, `jbus-mcp run`, `jbus-mcp client`, `jbus-mcp code`,
`jbus-mcp revoke` and `jbus-mcp log`.

`serve` runs the server (`jbus_mcp.server`), as its own system user. `run` is the runner
(`jbus_mcp.run`), which only systemd starts, on a connection to its socket, as the user jbus
runs as. `client`, `code`
and `revoke` are typed at a shell of the machine as the server's user: `client` makes the one
OAuth client and prints its ID and secret once, `code` makes a sign-in code good for ten minutes
and prints it once, and `revoke` signs every connector out. `log` prints the last lines of the
server's log.
"""

from __future__ import annotations

import argparse
import json
import os

from jbus_mcp import Refused, limits, oauth, run, server, state_dir

AGENT = "CLAUDE_CODE_SESSION_ID"


def _store() -> oauth.Store:
    origin = os.environ.get("JBUS_MCP_ORIGIN", "").rstrip("/") or "https://unset.invalid"
    return oauth.Store(state_dir() / oauth.FILE, origin)


def _yours(verb: str) -> None:
    if os.environ.get(AGENT):
        raise Refused(
            f"refused: jbus-mcp {verb} runs in an agent's session: it is the user's to run"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jbus-mcp", description=__doc__, allow_abbrev=False)
    verbs = parser.add_subparsers(dest="verb", required=True)
    verbs.add_parser("serve", help="serve MCP and the sign-in on 127.0.0.1")
    verbs.add_parser("run", help="the runner: one request on stdin, as the user jbus runs as")
    verbs.add_parser("client", help="make the one OAuth client, and print its ID and secret once")
    verbs.add_parser("code", help="make a sign-in code good for ten minutes, and print it once")
    verbs.add_parser("revoke", help="sign every connector out")
    shown = verbs.add_parser("log", help="print the last lines of the server's log")
    shown.add_argument("--lines", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        if args.verb == "serve":
            return server.serve()
        if args.verb == "run":
            return run.main()
        if args.verb == "log":
            for one in limits.Log(state_dir() / limits.FILE).lines()[-max(args.lines, 1) :]:
                print(json.dumps(one, sort_keys=True))
            return 0
        _yours(args.verb)
        store = _store()
        if args.verb == "client":
            client_id, secret = store.make_client()
            print(f"client ID: {client_id}")
            print(f"client secret, shown this once: {secret}")
            print("Enter both in the custom connector's settings, under Use your own OAuth client.")
            return 0
        if args.verb == "code":
            print(
                f"sign-in code, good for {oauth.CODE_TTL // 60} minutes, once: {store.make_code()}"
            )
            return 0
        print(f"revoked {store.revoke()} tokens: every connector signs in again")
        return 0
    except Refused as error:
        print(error)
        return 1
