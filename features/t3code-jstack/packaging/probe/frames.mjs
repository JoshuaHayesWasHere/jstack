// Times a jbus work.json write to the websocket frame that carries it, under live jbus load.
//
//   node frames.mjs <T3 Code checkout> [writes=60] [port=38917]
//
// It runs the checkout's own JbusWork behind subscribeJbusWork's websocket protocol (harness.ts),
// on a copy of the jbus and home state it reads, in a temp folder. While it runs, every write
// jbus and the homes make in the live folders the base server watches is made again at the same
// moment in the copy: the same name in the same folder, so the copy carries the live load.
// Then it writes work.json the way jbus does (a temp file renamed over it) with one more row,
// `probe-<n>`, waits for the frame that shows it, and prints write-to-frame delays.
// It only reads the live state; it writes only in its temp folder and in <checkout>/apps/server/.jbus-frames.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const [checkout, writesArg = "60", portArg = "38917"] = process.argv.slice(2);
if (!checkout) throw new Error("usage: node frames.mjs <T3 Code checkout> [writes] [port]");
const WRITES = Number(writesArg);
const PORT = Number(portArg);
const REPO = "jstack";

const stateHome = process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local/state");
const live = { jbus: path.join(stateHome, "jbus"), home: path.join(stateHome, "home") };
const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "jbus-frames-"));
const copy = { jbus: path.join(sandbox, "jbus"), home: path.join(sandbox, "home") };
const serverDir = path.join(path.resolve(checkout), "apps/server");
const harnessDir = path.join(serverDir, ".jbus-frames");

const isDir = (p) => { try { return fs.statSync(p).isDirectory(); } catch { return false; } };
const isFile = (p) => { try { return fs.statSync(p).isFile(); } catch { return false; } };
const dirsIn = (d) => { try { return fs.readdirSync(d).map((n) => path.join(d, n)).filter(isDir); } catch { return []; } };
const inCopy = (p) => path.join(sandbox, path.relative(stateHome, p));
const copyFile = (from) => { try { fs.copyFileSync(from, inCopy(from)); } catch {} };

// The folders the base series' JbusWork watches: the roots, every folder in them, and every
// folder of a tracked repo's home.
const repos = fs.readdirSync(live.jbus).filter((n) => isFile(path.join(live.jbus, n, "work.json")) && isFile(path.join(live.home, n, "home-id")));
const watched = [live.jbus, live.home, ...dirsIn(live.jbus), ...dirsIn(live.home), ...repos.flatMap((r) => dirsIn(path.join(live.home, r)))];

// The copy: those folders, and the files a refresh reads in them.
for (const d of watched) fs.mkdirSync(inCopy(d), { recursive: true });
const BUS_FILES = ["work.json", "merged.json", "questions.json", "waiting-on-user.json", "held.json"];
for (const d of dirsIn(live.jbus)) for (const f of BUS_FILES) copyFile(path.join(d, f));
for (const d of dirsIn(live.home)) copyFile(path.join(d, "home-id"));
for (const r of repos) {
  for (const d of dirsIn(path.join(live.home, r))) for (const f of ["home-id", "prefix", "plan.md", "handoff.md"]) copyFile(path.join(d, f));
  let rows = [];
  try { rows = JSON.parse(fs.readFileSync(path.join(live.jbus, r, "work.json"), "utf8")).work ?? []; } catch {}
  for (const row of rows) for (const folder of ["tasks", "scouts"]) if (typeof row.slug === "string") copyFile(path.join(live.home, r, folder, `${row.slug}.md`));
}

// The probe's own work.json: the live one with one row more, written as jbus writes it.
const workPath = path.join(copy.jbus, REPO, "work.json");
const kept = JSON.parse(fs.readFileSync(path.join(live.jbus, REPO, "work.json"), "utf8"));
const template = kept.work.find((row) => row.kind === "row" && row.lane !== "merged" && row.value !== "merged");
if (!template) throw new Error(`no open row in ${REPO}'s work.json to copy`);
let current = "";
const writeWork = (n) => {
  if (n !== null) current = JSON.stringify({ ...kept, work: [...kept.work, { ...template, key: `probe-${n}`, slug: `probe-${n}` }] }, null, 2);
  const temporary = `${workPath}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, current);
  fs.renameSync(temporary, workPath);
};
writeWork(0);

// The live load, made again in the copy.
let replayed = 0;
const replayers = [];
const WORK = path.join(live.jbus, REPO, "work.json");
for (const d of watched) {
  try {
    replayers.push(fs.watch(d, (_type, name) => {
      if (name === null) return;
      replayed++;
      const real = path.join(d, String(name));
      if (real === WORK) return writeWork(null);
      const target = inCopy(real);
      try {
        if (isDir(real)) fs.mkdirSync(target, { recursive: true });
        else if (!fs.existsSync(real)) fs.rmSync(target, { force: true });
        else if (BUS_FILES.includes(String(name)) || /\.md$|home-id$|prefix$/.test(String(name))) fs.copyFileSync(real, target);
        else fs.writeFileSync(target, String(replayed));
      } catch {}
    }));
  } catch {}
}

// The server half.
fs.mkdirSync(harnessDir, { recursive: true });
fs.copyFileSync(new URL("./harness.ts", import.meta.url), path.join(harnessDir, "harness.ts"));
const server = spawn(process.execPath, [path.join(harnessDir, "harness.ts"), String(PORT), copy.jbus, copy.home], { cwd: serverDir, stdio: ["ignore", "inherit", "inherit"] });
const cleanUp = () => {
  for (const w of replayers) w.close();
  server.kill();
  fs.rmSync(harnessDir, { recursive: true, force: true });
  fs.rmSync(sandbox, { recursive: true, force: true });
};
process.on("exit", cleanUp);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const connect = async () => {
  for (let tries = 0; tries < 100; tries++) {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
    const opened = await new Promise((r) => { ws.onopen = () => r(true); ws.onerror = () => r(false); });
    if (opened) return ws;
    await sleep(200);
  }
  throw new Error("the harness never listened");
};

const ws = await connect();
const seen = new Map();
let waiter = null;
ws.onmessage = (event) => {
  const at = performance.now();
  const parsed = JSON.parse(String(event.data));
  for (const message of Array.isArray(parsed) ? parsed : [parsed]) {
    if (message._tag === "Ping") ws.send(JSON.stringify({ _tag: "Pong" }));
    if (message._tag !== "Chunk") continue;
    ws.send(JSON.stringify({ _tag: "Ack", requestId: message.requestId }));
    for (const value of message.values) {
      for (const task of value.tasks ?? []) {
        const n = /^probe-(\d+)$/.exec(task.slug)?.[1];
        if (n !== undefined && !seen.has(Number(n))) {
          seen.set(Number(n), at);
          if (waiter?.n === Number(n)) waiter.resolve();
        }
      }
    }
  }
};
ws.send(JSON.stringify({ _tag: "Request", id: "1", tag: "subscribeJbusWork", payload: {}, headers: [] }));
while (!seen.has(0)) await sleep(50);

const replayedAtStart = replayed;
const startedAt = performance.now();
const delays = [];
let timeouts = 0;
for (let n = 1; n <= WRITES; n++) {
  // A gap that does not line up with the coalesce: 100-400 ms, the same for every run.
  await sleep(100 + ((n * 7919) % 300));
  const framed = new Promise((resolve) => { waiter = { n, resolve }; });
  writeWork(n);
  const wroteAt = performance.now();
  const timedOut = await Promise.race([framed.then(() => false), sleep(15000).then(() => true)]);
  if (timedOut) timeouts++;
  else delays.push(seen.get(n) - wroteAt);
}
const seconds = (performance.now() - startedAt) / 1000;
delays.sort((a, b) => a - b);
const at = (q) => delays[Math.min(delays.length - 1, Math.ceil(q * delays.length) - 1)];
const ms = (v) => (v === undefined ? "-" : `${v.toFixed(1)}ms`);
console.log(
  `writes ${WRITES} framed ${delays.length} timeouts ${timeouts} | p50 ${ms(at(0.5))} p90 ${ms(at(0.9))} p99 ${ms(at(0.99))} max ${ms(delays.at(-1))} min ${ms(delays[0])} | live load ${((replayed - replayedAtStart) / seconds).toFixed(1)} events/s over ${seconds.toFixed(0)}s`,
);
console.log(`delays ${delays.map((d) => d.toFixed(0)).join(" ")}`);
ws.close();
process.exit(0);
