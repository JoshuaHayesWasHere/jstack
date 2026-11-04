# jbus-mcp

`jbus-mcp` serves jbus to a claude.ai custom connector as a remote MCP server.
A Chef in claude.ai can then read the queue and the digest, queue a brief, and record the user's go or answer, all on the machine jbus runs on.
It runs nothing else: no merge, no `jmerge`, no `--rule`, no `--follows`, no `--as`, and no message to a T3 Code thread.

## Off by default

jstack's install leaves the connector off, on every machine.
The feature has no command, no hook and no `units/` folder, so `install.sh` and `jinstall` link nothing of it, and `--check` names nothing of it.
Nothing makes the `jbus-mcp` user, the runner's socket, a unit, the tunnel or an Access application, and nothing listens, until a machine's root runs [Turn it on](#turn-it-on).
Even a server started by hand refuses to serve without `JBUS_MCP_ORIGIN`, and the runner refuses every request without its config in `/etc/jbus-mcp/runner.json`.
The files in `deploy/` are templates: each value a machine sets is a placeholder, and `jbus-mcp render` fills them in.

To turn it off again, stop and disable the units, `systemctl disable --now jbus-mcp.service jbus-mcp-run.socket`, and delete the tunnel's DNS route.

It needs Linux with systemd, root, Python 3.12 or later for the user `jbus-mcp`, and a claude.ai plan that can add custom connectors.
The tunnel and Access need a Cloudflare account with a zone for the hostname.
Any other way to put an `https` hostname in front of `127.0.0.1:<port>` works too, but loses the Access gate below.

## The tools

| Tool | The jbus command it runs |
|---|---|
| `jbus_status` | `jbus status` |
| `jbus_digest` | `jbus digest --json [--since <time>]` |
| `jbus_feed` | `jbus --project <name> events [--slug <slug>] [--since <time>]` |
| `jbus_queue_show` | `jbus --project <name> queue show [--all]` |
| `jbus_queue_add` | `jbus --project <name> queue add <slug> --priority <n> [--depends <slugs>]`, with the brief on stdin |
| `jbus_queue_approve` | `jbus --project <name> queue approve <slug> --sha <sha12> --message <thread>/<message>` |
| `jbus_answer` | `jbus --project <name> answer <number> --message <thread>/<message>`, with `--default` or `--differs` |

The four reads are the Chef's reads of [What the Chef may run](../../jbus/docs/jbus/what-the-chef-may-run.md).
The feed is `jbus events`, so the server never calls `jbus view` and never holds the bot's key.
A go and an answer rest only on the user's own message in T3 Code, which jbus reads itself.
Both run as the default party, `home`, so a brief or a gate that holds for a door parks a gate for the user instead of opening it ([Doors](../../jbus/docs/jbus/the-queue.md#doors)).
No call over the connector opens a door.

`jbus_queue_add` is the main exposure.
Whoever holds a live token, a prompt injection in a chat that has the connector included, can queue a brief.
The row still waits for the user's go, and a crew runs it only after that go, read from the user's own T3 Code message.

## How it reaches jbus

```
claude.ai -> Cloudflare (Access, then the tunnel) -> cloudflared -> 127.0.0.1:<port> jbus-mcp serve (user jbus-mcp)
  -> /run/jbus-mcp/run.sock -> jbus-mcp run (the user jbus runs as) -> jbus
```

The server runs as the system user `jbus-mcp`, which owns nothing of jbus's.
Its unit sandboxes it: no home directories, a read-only system, loopback only, and no new privileges.
It reaches jbus only through the runner's socket, which only the `jbus-mcp` group may open.
systemd starts one runner for each connection, as the user jbus runs as.

The runner trusts nothing the server sends but a tool's name and its arguments.
It rebuilds the command line from the same tool table (`jbus_mcp.tools`), checks the project against its own config, and checks the whole line again: every flag must be one of the table's, and every word plain ASCII with no space, shell character, line break or `..`.
It runs jbus with no shell.
Its code is a root-owned copy, in `/opt/jbus-mcp` by default, so neither user can change it.

Every call is one line of `/var/lib/jbus-mcp/log.jsonl`, with a brief kept only as its sha256 and length.
Reads are limited to 60 a minute, writes to 10, and the sign-in endpoints to 20.

## Sign-in

claude.ai's custom connectors sign in with OAuth: Claude's published client metadata (CIMD), dynamic client registration, or an OAuth client the user enters ([Authentication for connectors](https://claude.com/docs/connectors/building/authentication), [Add a connector that isn't in the directory](https://claude.com/docs/connectors/custom/add-unlisted)).
A fixed bearer token in a request header is in beta for a limited set of organizations, so the server does not rest on it.
Claude needs a 401 whose `WWW-Authenticate` names the protected resource metadata, PKCE with S256, the callback `https://claude.ai/api/mcp/auth_callback`, form-encoded token requests, and rotated refresh tokens.

The server is its own authorization server, for one client and one user:

- `jbus-mcp client` makes the one client and prints its ID and secret once.
  You enter both in the connector's settings under "Use your own OAuth client".
  The server takes no registration over the network.
- The sign-in page asks for a sign-in code that `jbus-mcp code` makes on the machine.
  The code is eight letters, good for ten minutes and for one sign-in, and five wrong tries burn it.
- An access token lives an hour and a refresh token 30 days.
  Each refresh spends the old refresh token, and a spent one used again revokes its whole family.
- Every secret is kept only as its sha256, in `/var/lib/jbus-mcp/oauth.json`, mode 0600.

## Cloudflare Access in front

Access is a second gate before OAuth, on the tunnel's hostname, with two applications ([Application paths](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/)):

| Application | Path | Policies |
|---|---|---|
| jbus-mcp sign-in | `<host>/authorize` | Allow: your email. |
| jbus-mcp | `<host>` | Bypass: IP ranges `160.79.104.0/21`. Allow: your email. |

The more specific path wins, so the sign-in page asks for your Cloudflare sign-in and then for the sign-in code.
claude.ai's servers call the MCP endpoint, the token endpoint and the metadata themselves, from Anthropic's published egress range, `160.79.104.0/21`, and carry no Access cookie.
An Access login in their way would break the connector, so the Bypass lets that range through to OAuth, and the Allow lets your own browser in.
Every other address gets the Access login page and never reaches the server.
An Access service token is no way out: Claude would have to send its two headers, and custom header names need Anthropic's approval.
If Anthropic's range changes, the connector fails closed until the policy is updated.

## Turn it on

Run these as root, from a checkout of jstack.
Set the four values first, and every step uses them:

```sh
JBUS_USER=<the user jbus runs as>
HOST=<the public hostname, such as jbus-mcp.example.com>
PREFIX=/opt/jbus-mcp
OUT=$(mktemp -d)/deploy
```

1. Write this machine's deploy files from the templates, with each project the connector may name.
   `render` checks each value and writes only to the new folder `$OUT`.
   `--home` names the jbus user's home when it is not that user's own, `--port` the loopback port (4391 by default), and `--python` a Python 3.12 or later when `/usr/bin/python3` is older:

   ```sh
   PYTHONPATH=features/jbus-mcp/src python3 -m jbus_mcp render --user "$JBUS_USER" --host "$HOST" --project jstack --prefix "$PREFIX" --out "$OUT"
   ```

2. Make the user and the code's root-owned copy:

   ```sh
   useradd --system --home-dir /var/lib/jbus-mcp --shell "$(command -v nologin)" jbus-mcp
   install -d -o root -g root -m 0755 "$PREFIX" /etc/jbus-mcp
   cp -r features/jbus-mcp/src "$PREFIX/src"
   install -o root -g root -m 0755 "$OUT/jbus-mcp" "$PREFIX/jbus-mcp"
   chown -R root:root "$PREFIX" && chmod -R go-w "$PREFIX"
   ```

3. Put the config in place:

   ```sh
   install -o root -g root -m 0644 "$OUT/jbus-mcp.env" "$OUT/runner.json" /etc/jbus-mcp/
   ```

4. Install and start the units:

   ```sh
   install -o root -g root -m 0644 "$OUT"/*.service "$OUT"/*.socket /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now jbus-mcp-run.socket jbus-mcp.service
   ```

5. Make the tunnel, route the hostname to it, and run it with `$OUT/cloudflared.yml` as its config.
   Copy the credentials file that `tunnel create` names to `/etc/cloudflared/jbus-mcp.json` before `service install`:

   ```sh
   cloudflared tunnel create jbus-mcp
   cloudflared tunnel route dns jbus-mcp "$HOST"
   install -o root -g root -m 0644 "$OUT/cloudflared.yml" /etc/cloudflared/config.yml
   cloudflared service install
   ```

6. Add the two Access applications above in Cloudflare Zero Trust, with your own email.
7. Make the client, then add the connector in claude.ai with the URL `https://<host>/mcp` and the client's ID and secret:

   ```sh
   sudo -u jbus-mcp "$PREFIX/jbus-mcp" client
   ```

8. Before you press Connect, make a sign-in code, and type it on the sign-in page:

   ```sh
   sudo -u jbus-mcp "$PREFIX/jbus-mcp" code
   ```

An upgrade is step 2's `cp` again, then `systemctl restart jbus-mcp.service`.

## Operate it

| Command, as `sudo -u jbus-mcp <prefix>/jbus-mcp ...` | What it does |
|---|---|
| `code` | Makes a sign-in code, good for ten minutes, once. |
| `revoke` | Signs every connector out. |
| `client` | Makes a new client and revokes the old one: the connector must be removed and added again. |
| `log --lines <n>` | Prints the last lines of the log. |

`client`, `code` and `revoke` are refused in an agent's session (`CLAUDE_CODE_SESSION_ID` set), since they are the user's to run.
`systemctl stop jbus-mcp.service jbus-mcp-run.socket` takes the connector off the machine at once.
