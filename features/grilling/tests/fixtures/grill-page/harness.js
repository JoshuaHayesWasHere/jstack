// Node has no page: build the template's markup into a small tree, run its script against
// it as a browser would, answer the round as stdin says and press the button.
const fs = require('fs');
const vm = require('vm');
const spec = JSON.parse(fs.readFileSync(0, 'utf8'));
let html = fs.readFileSync(process.argv[2], 'utf8');
const block = /(<script type="application\/json" id="round-data">)[\s\S]*?(<\/script>)/;
if (spec.raw !== undefined) html = html.replace(block, (_, open, close) => open + spec.raw + close);
else if (spec.round) html = html.replace(block, (_, open, close) => open + JSON.stringify(spec.round) + close);
if (spec.script) html = html.replace(spec.script[0], spec.script[1]);

const VOID = ['meta', 'input', 'br', 'hr', 'img', 'link'];
class Node {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.attrs = {}; this.listeners = {};
    this.parent = null; this.own = ''; this.hidden = false; this.checked = false;
    this.held = ''; this.className = '';
  }
  // A browser keeps an input's value as text, whatever was assigned.
  get value() { return this.held; }
  set value(value) { this.held = String(value); }
  appendChild(child) { child.parent = this; this.children.push(child); return child; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  addEventListener(type, heard) { (this.listeners[type] = this.listeners[type] || []).push(heard); }
  fire(type) { (this.listeners[type] || []).forEach((heard) => heard({ preventDefault() {} })); }
  get textContent() { return this.own + this.children.map((child) => child.textContent).join(''); }
  set textContent(text) { this.children = []; this.own = String(text); }
  walk(seen = []) { seen.push(this); this.children.forEach((child) => child.walk(seen)); return seen; }
  up(test) { for (let n = this.parent; n; n = n.parent) if (test(n)) return n; return null; }
}

const root = new Node('#document');
let at = root;
const token = /<!--[\s\S]*?-->|<(script|style)\b([^>]*)>([\s\S]*?)<\/\1>|<(\/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*)>|([^<]+)/g;
function open(tag, text) {
  const node = new Node(tag.toLowerCase());
  for (const [, name, value] of text.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) node.attrs[name] = value || '';
  node.className = node.attrs.class || '';
  node.hidden = 'hidden' in node.attrs;
  return at.appendChild(node);
}
for (const found of html.matchAll(token)) {
  const [, raw, rawAttrs, rawText, closing, tag, attrs, text] = found;
  if (raw) open(raw, rawAttrs).own = rawText;
  else if (closing) at = at.parent;
  else if (tag) { const node = open(tag, attrs); if (!VOID.includes(node.tagName)) at = node; }
  else if (text && at !== root) { const node = new Node('#text'); node.own = text; at.appendChild(node); }
}

const heard = new Node('#listeners');
const document = {
  title: '',
  getElementById: (id) => root.walk().find((node) => node.attrs.id === id) || null,
  createElement: (tag) => new Node(tag),
  createTextNode: (text) => { const node = new Node('#text'); node.own = String(text); return node; },
  addEventListener: (type, listener) => heard.addEventListener(type, listener),
};
const calls = [];
const window = { addEventListener() {} };
if (spec.lavish) {
  window.lavish = {
    queuePrompt: (prompt, options) => calls.push(['queuePrompt', prompt, options]),
    sendQueuedPrompts: () => calls.push(['sendQueuedPrompts']),
  };
}
const sandbox = vm.createContext({ document, window, setTimeout() {} });
const scripts = root.walk().filter((node) => node.tagName === 'script' && !node.attrs.type);
// A name declared at the top of a script stays in the context after the run, `const` and `let`
// included, and in a browser it shares a scope with the window's own names. Ask the context
// for each name the script declares anywhere, and for the window's.
const names = new Set(['top', 'name', 'status', 'parent', 'self', 'length', 'origin']);
scripts.forEach((script) => {
  for (const [, name] of script.own.matchAll(/\b(?:var|let|const|function|class)\s+([A-Za-z_$][\w$]*)/g)) names.add(name);
});
const known = (name) => vm.runInContext(`(function () { try { return typeof ${name}; } catch (err) { return 'declared'; } })()`, sandbox) !== 'undefined';
const before = [...names].filter(known);
scripts.forEach((script) => vm.runInContext(script.own, sandbox));

const forms = () => root.walk().filter((node) => 'data-lavish-question' in node.attrs);
// After a reload Lavish puts back each pick under the name of the form the user made it in.
for (const [name, option] of Object.entries(spec.restored || {})) {
  const form = forms().find((node) => node.attrs['data-lavish-question'] === name);
  if (form) form.walk().filter((node) => node.type === 'radio').forEach((input) => { input.checked = input.value === option; });
}

const controls = () => root.walk().filter((node) => ['input', 'textarea', 'select'].includes(node.tagName));
const question = (node) => node.up((n) => 'data-lavish-question' in n.attrs);
const checked = {};
for (const input of controls().filter((node) => node.type === 'radio')) {
  const id = question(input).attrs['data-lavish-question'];
  checked[id] = (checked[id] || []).concat(input.checked ? [input.value] : []);
}
const report = {
  checked,
  controls: controls().map((node) => ({
    tag: node.tagName,
    question: question(node) ? question(node).attrs['data-lavish-question'] : null,
    details: !!node.up((n) => n.tagName === 'details'),
  })),
  cards: root.walk().filter((node) => 'data-lavish-question' in node.attrs).map((node) => node.textContent),
  settled: document.getElementById('settled').children.map((row) => row.children.map((cell) => cell.textContent)),
  settled_hidden: document.getElementById('settled-sec').hidden,
  settled_above: root.walk().indexOf(document.getElementById('settled-sec')) < root.walk().indexOf(document.getElementById('questions')),
  title: document.title,
  loads: root.walk().filter((node) => 'src' in node.attrs || 'href' in node.attrs).map((node) => node.tagName)
    .concat(root.walk().filter((node) => node.tagName === 'style').flatMap((node) => node.own.match(/url\(|@import/g) || [])),
  scripts: scripts.length,
  leaked: [...names].filter((name) => known(name) && !before.includes(name)),
  problems: document.getElementById('problem-list').children.map((item) => item.textContent),
  problems_hidden: document.getElementById('problems').hidden,
  send_disabled: !!document.getElementById('send').disabled,
};
if (report.problems.length) { process.stdout.write(JSON.stringify(report)); process.exit(0); }

for (const pick of spec.picks || []) {
  const form = root.walk().find((node) => (node.attrs['data-lavish-question'] || '').endsWith(':' + pick.id));
  if (pick.option) {
    form.walk().filter((node) => node.type === 'radio').forEach((input) => { input.checked = input.value === pick.option; });
    heard.fire('change');
  }
  if (pick.note !== undefined) {
    form.walk().find((node) => node.tagName === 'textarea').value = pick.note;
    heard.fire('input');
  }
}
report.count = document.getElementById('count').textContent;
document.getElementById('send').fire('click');
report.calls = calls;
report.state = document.getElementById('state').textContent;
report.copy = document.getElementById('copy').textContent;
report.copy_hidden = document.getElementById('copy').hidden;
process.stdout.write(JSON.stringify(report));
