# jbus-mcp serves jbus to a connector

`jbus-mcp serve` answers MCP over Streamable HTTP on 127.0.0.1, behind its own OAuth sign-in, and hands each tool call to `jbus-mcp run`, which rebuilds the jbus command line from the tool table and runs it as the user jbus runs as.

Paths:
- `features/jbus-mcp/src/jbus_mcp/`
- `features/jbus-mcp/docs/`
- `features/jbus-mcp/deploy/`
Tests: none

## Sub-features

- `mcp-sign-in` answers a call with no live token with a 401 that names the protected resource metadata, and lets the one client in only with a sign-in code made on the machine and PKCE.
- `mcp-tools` lists seven tools and runs each as its one jbus command line.
- `mcp-runner` refuses any request whose command line the tool table does not build.
- `mcp-off` stays off on every machine until its root renders the deploy files and installs them: jstack's install links nothing of it.

## How to get to it (user POV)

Not driven yet.

## Driving it with verify-jstack

Needs: `home`

Not driven yet: no recipe drives this feature. The `home` seed is the sandbox's HOME, which every drive has.

## Gotchas

Not driven yet.
