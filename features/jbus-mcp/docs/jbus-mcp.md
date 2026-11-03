# jbus-mcp

`jbus-mcp` serves jbus to a claude.ai custom connector as a remote MCP server.
A Chef in claude.ai can then read the queue and the digest, queue a brief, and record the user's go or answer, all on the machine jbus runs on.
It runs nothing else: no merge, no `jmerge`, no `--rule`, no `--follows`, no `--as`, and no message to a T3 Code thread.

## The tools

| Tool | The jbus command it runs |
|---|---|
| `jbus_status` | `jbus status` |
| `jbus_digest` | `jbus digest --json [--since <time>]` |
| `jbus_feed` | `jbus --project <name> events [--slug <slug>] [--since <time>]` |
| `jbus_queue_show` | `jbus --project <name> queue show [--all]` |
| `jbus_queue_add` | `jbus --project <name> queue add <slug> --priority <n> [--depends <slugs>]`, with the brief on stdin |
| `jbus_queue_approve` | `jbus --project <name> queue approve <slug> --sha <sha12> --message <thread>/<message>` |
| `jbus_answer` | `jbus --project <name> answer <number> --message <thread>/<message> --default\|--differs` |

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
claude.ai -> Cloudflare (Access, then the tunnel) -> cloudflared -> 127.0.0.1:4391 jbus-mcp serve (user jbus-mcp)
  -> /run/jbus-mcp/run.sock -> jbus-mcp run (the user jbus runs as) -> jbus
```

The server runs as the system user `jbus-mcp`, which owns nothing of jbus's.
Its unit sandboxes it: no home directories, a read-only system, loopback only, and no new privileges.
It reaches jbus only through the runner's socket, which only the `jbus-mcp` group may open.
systemd starts one runner for each connection, as the user jbus runs as.

The runner trusts nothing the server sends but a tool's name and its arguments.
It rebuilds the command line from the same tool table (`jbus_mcp.tools`), checks the project against its own config, and checks the whole line again: every flag must be one of the table's, and every word plain ASCII with no space, shell character, line break or `..`.
It runs jbus with no shell.
Its code is a root-owned copy in `/opt/jbus-mcp`, so neither user can change it.

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

## Install on the machine

Run these as root, from a checkout of the merged branch.
Replace `josh` with the user jbus runs as, and `jbus-mcp.example.com` with the hostname.

1. Make the user and the code's copy:

   ```sh
   useradd --system --home-dir /var/lib/jbus-mcp --shell /usr/bin/nologin jbus-mcp
   install -d -o root -g root -m 0755 /opt/jbus-mcp /etc/jbus-mcp
   cp -r features/jbus-mcp/src /opt/jbus-mcp/src
   install -o root -g root -m 0755 features/jbus-mcp/deploy/jbus-mcp /opt/jbus-mcp/jbus-mcp
   chown -R root:root /opt/jbus-mcp && chmod -R go-w /opt/jbus-mcp
   ```

2. Write the config, with the hostname and the projects the connector may name:

   ```sh
   install -o root -g root -m 0644 features/jbus-mcp/deploy/jbus-mcp.env /etc/jbus-mcp/jbus-mcp.env
   sed 's/@JBUS_USER@/josh/g' features/jbus-mcp/deploy/runner.json > /etc/jbus-mcp/runner.json
   chmod 0644 /etc/jbus-mcp/runner.json
   ```

3. Install and start the units, from the feature's `deploy` folder:

   ```sh
   cd features/jbus-mcp/deploy
   install -m 0644 jbus-mcp.service jbus-mcp-run.socket /etc/systemd/system/
   sed 's/@JBUS_USER@/josh/g' 'jbus-mcp-run@.service' > '/etc/systemd/system/jbus-mcp-run@.service'
   cd -
   systemctl daemon-reload
   systemctl enable --now jbus-mcp-run.socket jbus-mcp.service
   curl -sS -H 'Host: 127.0.0.1:4391' http://127.0.0.1:4391/healthz
   ```

4. Make the tunnel and route the hostname to it, with `features/jbus-mcp/deploy/cloudflared.yml` as its config:

   ```sh
   cloudflared tunnel create jbus-mcp
   cloudflared tunnel route dns jbus-mcp jbus-mcp.example.com
   ```

5. Add the two Access applications above in Cloudflare Zero Trust.
6. Make the client, then add the connector in claude.ai with the URL `https://jbus-mcp.example.com/mcp`:

   ```sh
   sudo -u jbus-mcp /usr/bin/python3 -I /opt/jbus-mcp/jbus-mcp client
   ```

7. Before you press Connect, make a sign-in code, and type it on the sign-in page:

   ```sh
   sudo -u jbus-mcp /usr/bin/python3 -I /opt/jbus-mcp/jbus-mcp code
   ```

An upgrade is step 1's copy again, then `systemctl restart jbus-mcp.service`.

## Operate it

| Command, as `sudo -u jbus-mcp /usr/bin/python3 -I /opt/jbus-mcp/jbus-mcp ...` | What it does |
|---|---|
| `code` | Makes a sign-in code, good for ten minutes, once. |
| `revoke` | Signs every connector out. |
| `client` | Makes a new client and revokes the old one: the connector must be removed and added again. |
| `log --lines <n>` | Prints the last lines of the log. |

`client`, `code` and `revoke` are refused in an agent's session (`CLAUDE_CODE_SESSION_ID` set), since they are the user's to run.
`systemctl stop jbus-mcp.service jbus-mcp-run.socket` takes the connector off the machine at once.
