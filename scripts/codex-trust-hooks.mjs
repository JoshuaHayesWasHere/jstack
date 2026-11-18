#!/usr/bin/env node
// Codex silently skips any hook without a trusted_hash under hooks.state in
// ~/.codex/config.toml. This mirrors what Codex's /hooks screen does through
// `codex app-server` (hooks/list, config/batchWrite).
import { spawn } from "node:child_process";
import { homedir } from "node:os";

const [pattern, flag] = process.argv.slice(2);
if (!pattern) {
    console.error("usage: codex-trust-hooks.mjs <command regex> [--dry-run]");
    process.exit(2);
}
const ours = new RegExp(pattern);
const dryRun = flag === "--dry-run";

const server = spawn(process.env.CODEX_BIN || "codex", ["app-server"], {
    stdio: ["pipe", "pipe", "ignore"],
});
server.on("error", (e) => {
    console.error(`codex app-server did not start: ${e.message}`);
    process.exit(1);
});
setTimeout(() => {
    console.error("codex app-server did not answer in 30s");
    server.kill();
    process.exit(1);
}, 30_000).unref();

let buffer = "";
let nextId = 0;
const pending = new Map();
server.stdout.on("data", (chunk) => {
    buffer += chunk;
    for (let i; (i = buffer.indexOf("\n")) >= 0; ) {
        const line = buffer.slice(0, i);
        buffer = buffer.slice(i + 1);
        let message;
        try {
            message = JSON.parse(line);
        } catch {
            continue;
        }
        const settle = pending.get(message.id);
        if (!settle) continue;
        pending.delete(message.id);
        settle(message);
    }
});
const write = (message) => server.stdin.write(JSON.stringify({ jsonrpc: "2.0", ...message }) + "\n");
const call = (method, params) =>
    new Promise((resolve, reject) => {
        const id = ++nextId;
        pending.set(id, (m) => (m.error ? reject(new Error(`${method}: ${m.error.message}`)) : resolve(m.result)));
        write({ id, method, params });
    });
const ourHooks = async () =>
    (await call("hooks/list", { cwds: [homedir()] })).data
        .flatMap((entry) => entry.hooks)
        .filter((hook) => hook.source === "user" && ours.test(hook.command ?? ""));

let failed = false;
try {
    await call("initialize", { clientInfo: { name: "jstack-install", version: "1" } });
    write({ method: "initialized" });

    const untrusted = (await ourHooks()).filter((h) => h.trustStatus !== "trusted" && h.trustStatus !== "managed");
    for (const h of untrusted) console.log(`${dryRun ? "would trust" : "trusted"} ${h.key}`);

    if (untrusted.length && !dryRun) {
        await call("config/batchWrite", {
            edits: [
                {
                    keyPath: "hooks.state",
                    mergeStrategy: "upsert",
                    value: Object.fromEntries(untrusted.map((h) => [h.key, { trusted_hash: h.currentHash }])),
                },
            ],
            reloadUserConfig: true,
        });
        for (const h of await ourHooks()) {
            if (h.trustStatus !== "trusted") {
                console.error(`still ${h.trustStatus}: ${h.key}`);
                failed = true;
            }
        }
    }
} catch (e) {
    console.error(e.message);
    failed = true;
}
server.kill();
process.exit(failed ? 1 : 0);
