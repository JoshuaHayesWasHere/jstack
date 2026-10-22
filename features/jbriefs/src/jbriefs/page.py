"""Render the homes as one HTML page.

The page is a single file. It fetches only DaisyUI and Tailwind from the CDN, and its one
script copies a thread's id. The renderer escapes every word that comes from a state file.
"""

from __future__ import annotations

import re
from collections import Counter
from html import escape
from pathlib import Path

from jbriefs.parse import (
    BLOCKED,
    DONE,
    NO_RESULT,
    NOT_DONE,
    PAUSED,
    UNCLEAR,
    Brief,
    Entry,
    Handoff,
    Repo,
    Result,
)

STATES = (NO_RESULT, DONE, NOT_DONE, BLOCKED, PAUSED, UNCLEAR)
BADGE = {
    NO_RESULT: "badge-info",
    DONE: "badge-success",
    NOT_DONE: "badge-warning",
    BLOCKED: "badge-error",
    PAUSED: "badge-accent",
    UNCLEAR: "badge-neutral",
}
EDGE = {
    DONE: "border-success",
    NOT_DONE: "border-warning",
    BLOCKED: "border-error",
    PAUSED: "border-accent",
    UNCLEAR: "border-neutral",
}

_URL = re.compile(r"https?://[^\s<>\"')\]`]+")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HEADING = re.compile(r"^#{1,6} +(.+)$")
_BULLET = re.compile(r"^\s*[-*] +(.*)$")
_LABEL = re.compile(r"^([A-Z][^:`]{0,30}):(?=\s|$)(.*)$")
_PULL_NUMBER = re.compile(r"/pull/(\d+)")
_NOT_ID = re.compile(r"[^A-Za-z0-9_-]+")

HEAD = """\
<!doctype html>
<html lang="en" data-theme="luxury">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live briefs</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/daisyui@5.5.19/daisyui.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/daisyui@5.5.19/themes.css">
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4.2.4/dist/index.global.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  html, body { background: var(--color-base-100); color: var(--color-base-content); }
  :where(.grid, .flex) > * { min-width: 0; }
  :where(p, h1, h2, h3, h4, li, summary, a, code) { overflow-wrap: anywhere; }
  .badge { white-space: nowrap; }
  code { font-size: 0.85em; background: var(--color-base-300); padding: 0.1em 0.35em;
    border-radius: 0.3em; }
  pre { overflow-x: auto; background: var(--color-base-300); padding: 0.75rem;
    border-radius: 0.5rem; font-size: 0.85em; }
  summary { cursor: pointer; }
  .md > * + * { margin-top: 0.45rem; }
  .md ul { list-style: disc; padding-left: 1.25rem; }
  .md li + li { margin-top: 0.25rem; }
  .eyebrow { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; opacity: 0.6; }
</style>
</head>
<body>
<main class="mx-auto max-w-6xl p-5 lg:p-10 space-y-12">
"""

FOOT = """\
</main>
<script>
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-copy]");
  if (!button) return;
  try {
    await navigator.clipboard.writeText(button.dataset.copy);
  } catch {
    const range = document.createRange();
    range.selectNodeContents(button.previousElementSibling);
    getSelection().removeAllRanges();
    getSelection().addRange(range);
    if (!document.execCommand("copy")) return;
  }
  button.textContent = "Copied";
  setTimeout(() => { button.textContent = "Copy id"; }, 1500);
});
</script>
</body>
</html>
"""


def _id(*parts: str) -> str:
    return _NOT_ID.sub("-", "-".join(parts)).strip("-")


def _plain(text: str) -> str:
    out, last = [], 0
    for found in _URL.finditer(text):
        url = found[0].rstrip(".,;:*")
        out.append(escape(text[last : found.start()]))
        out.append(f'<a class="link" href="{escape(url)}">{escape(url)}</a>')
        last = found.start() + len(url)
    out.append(escape(text[last:]))
    return _BOLD.sub(r"<strong>\1</strong>", "".join(out))


def inline(text: str) -> str:
    parts = text.split("`")
    if len(parts) % 2 == 0:
        parts[-2:] = ["`".join(parts[-2:])]
    return "".join(
        f"<code>{escape(part)}</code>" if index % 2 else _plain(part)
        for index, part in enumerate(parts)
    )


def block(text: str) -> str:
    out: list[str] = []
    items: list[str] = []
    fence: list[str] | None = None

    def close_list() -> None:
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(item)}</li>" for item in items) + "</ul>")
            items.clear()

    for line in text.splitlines():
        if line.strip().startswith("```"):
            if fence is None:
                close_list()
                fence = []
            else:
                out.append(f"<pre>{escape(chr(10).join(fence))}</pre>")
                fence = None
        elif fence is not None:
            fence.append(line)
        elif not line.strip():
            close_list()
        elif found := _BULLET.match(line):
            items.append(found[1])
        elif items and line[:1].isspace():
            items[-1] += " " + line.strip()
        else:
            close_list()
            if found := _HEADING.match(line):
                out.append(f'<p class="font-semibold">{inline(found[1])}</p>')
            elif found := _LABEL.match(line):
                label = f'<span class="font-semibold">{escape(found[1])}:</span>'
                out.append(f"<p>{label}{inline(found[2])}</p>")
            else:
                out.append(f"<p>{inline(line)}</p>")
    if fence is not None:
        out.append(f"<pre>{escape(chr(10).join(fence))}</pre>")
    close_list()
    return f'<div class="md">{"".join(out)}</div>'


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _state_badge(state: str) -> str:
    return f'<span class="badge badge-soft {BADGE[state]}">{escape(state)}</span>'


def _entry_badge(status: str) -> str:
    lower = status.lower()
    if lower.startswith("with crewmate"):
        return '<span class="badge badge-soft badge-info">with crewmate</span>'
    if re.match(r"pr\b", lower):
        return '<span class="badge badge-soft badge-primary">pull request</span>'
    if lower.startswith("planned"):
        return '<span class="badge badge-outline">planned</span>'
    return '<span class="badge badge-outline">open</span>'


def _result(result: Result) -> str:
    return (
        f'<div class="border-l-4 {EDGE[result.state]} pl-3 space-y-2">'
        f'<p class="eyebrow">{escape(result.heading)}</p>{block(result.text)}</div>'
    )


def _brief(brief: Brief, *, anchor: str | None = None, opened: bool = True) -> str:
    head = ['<span class="eyebrow">Brief</span>']
    if anchor:
        head.append(f"<span><code>{escape(brief.slug)}</code> {inline(brief.title)}</span>")
    head.append(_state_badge(brief.state))
    if brief.thread:
        thread = escape(brief.thread)
        head.append(
            '<span class="inline-flex flex-wrap items-center gap-1" data-part="thread">'
            f"<span>{escape(brief.thread_title or '')}</span><code>{thread}</code>"
            f'<button type="button" class="btn btn-xs btn-outline" data-copy="{thread}">'
            "Copy id</button></span>"
        )
    pull = brief.pull_request
    if pull and pull.url:
        number = _PULL_NUMBER.search(pull.url)
        label = f"PR #{number[1]}" if number else "Pull request"
        head.append(f'<a class="btn btn-xs btn-outline" href="{escape(pull.url)}">{label}</a>')
    elif pull:
        head.append(f'<span class="text-sm opacity-80">Pull request: {inline(pull.text)}</span>')
    return (
        f'<div class="rounded-box border border-base-content/15 bg-base-100 p-4 space-y-3 text-sm"'
        f"{f' id="{anchor}"' if anchor else ''}>"
        f'<div class="flex flex-wrap items-center gap-2">{"".join(head)}</div>'
        f"{''.join(_result(result) for result in brief.results)}"
        f'<details{" open" if opened else ""}><summary class="eyebrow">Brief text</summary>'
        f'<div class="pt-2">{block(brief.body)}</div></details>'
        "</div>"
    )


def _entry(repo: Repo, entry: Entry, brief: Brief | None) -> str:
    keyword = re.sub(r"<[^>]+>", "", _entry_badge(entry.status))
    more = entry.status and entry.status.lower() != keyword
    status = f'<p class="text-sm opacity-80">Status: {inline(entry.status)}</p>' if more else ""
    checks = "".join(f"<li>{inline(item)}</li>" for item in entry.done_when)
    done_when = (
        f'<div class="md"><p class="eyebrow">Done when</p><ul>{checks}</ul></div>'
        if checks
        else '<p class="text-sm opacity-60">No "Done when" list.</p>'
    )
    return (
        f'<article class="card card-border bg-base-200" id="{_id(repo.name, entry.slug)}">'
        '<div class="card-body gap-3">'
        '<div class="flex flex-wrap items-center gap-2">'
        f'<h4 class="text-base font-semibold"><code>{escape(entry.slug)}</code> '
        f"{inline(entry.title)}</h4>{_entry_badge(entry.status)}</div>"
        f"{status}{done_when}"
        f"{_brief(brief) if brief else '<p class="text-sm opacity-60">No brief yet.</p>'}"
        "</div></article>"
    )


def _handoff(handoff: Handoff | None) -> str:
    if handoff is None:
        return '<p class="opacity-60">No handoff yet.</p>'
    cards = []
    for heading in ("Next", "Open decisions"):
        text = handoff.section(heading)
        body = block(text) if text else '<p class="opacity-60">Nothing written.</p>'
        cards.append(
            '<div class="card card-border bg-base-200"><div class="card-body gap-2">'
            f'<h3 class="eyebrow">{heading}</h3>{body}</div></div>'
        )
    return f'<div class="grid gap-4 md:grid-cols-2">{"".join(cards)}</div>'


def _repo(repo: Repo) -> str:
    live, cleared = repo.live, repo.cleared
    title = repo.handoff.title if repo.handoff else ""
    entries = "".join(_entry(repo, entry, brief) for entry, brief in live)
    if not entries:
        entries = '<p class="opacity-60">No open plan entries.</p>'
    apart = ""
    if cleared:
        briefs = "".join(
            _brief(brief, anchor=_id(repo.name, brief.slug), opened=False) for brief in cleared
        )
        apart = (
            '<details data-part="cleared" class="rounded-box border border-base-content/15 p-4">'
            f"<summary>{_count(len(cleared), 'brief')} with no open plan entry</summary>"
            f'<div class="space-y-4 pt-4">{briefs}</div></details>'
        )
    return (
        f'<section class="space-y-5" id="{_id("repo", repo.name)}">'
        '<div class="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b '
        'border-base-content/20 pb-2">'
        f'<h2 class="text-2xl font-bold">{escape(repo.name)}</h2>'
        f'<span class="text-sm opacity-60">{inline(title)}</span></div>'
        f"{_handoff(repo.handoff)}"
        f'<h3 class="text-lg font-semibold">Open plan entries ({len(live)})</h3>'
        f'<div class="space-y-4">{entries}</div>{apart}'
        "</section>"
    )


def _header(repos: list[Repo], state: Path, generated: str) -> str:
    live = [brief for repo in repos for _, brief in repo.live if brief]
    entries = sum(len(repo.live) for repo in repos)
    states = Counter(brief.state for brief in live)
    badges = "".join(
        f'<span class="badge badge-soft {BADGE[name]}">{states[name]} {escape(name)}</span>'
        for name in STATES
        if states[name]
    )
    nav = ""
    if len(repos) > 1:
        links = "".join(
            f'<a class="btn btn-sm btn-outline" href="#{_id("repo", repo.name)}">'
            f"{escape(repo.name)} · {len(repo.live)}</a>"
            for repo in repos
        )
        nav = f'<nav class="flex flex-wrap gap-2">{links}</nav>'
    return (
        '<header class="space-y-4">'
        f'<p class="eyebrow">Written {escape(generated)} · <code>{escape(str(state))}</code></p>'
        '<h1 class="text-4xl lg:text-5xl font-bold leading-tight">Live briefs</h1>'
        f'<p class="text-lg opacity-80">{_count(len(repos), "repo")} with a home, '
        f"{_count(entries, 'open plan entry').replace('entrys', 'entries')}, "
        f"{_count(len(live), 'live brief')}.</p>"
        f'<div class="flex flex-wrap gap-2">{badges}</div>{nav}'
        "</header>"
    )


def render(repos: list[Repo], *, state: Path, generated: str) -> str:
    body = "".join(_repo(repo) for repo in repos)
    if not repos:
        body = (
            '<div class="card card-border bg-base-200"><div class="card-body">'
            "<p>No repo has a home yet. A home appears here once a thread runs <code>/home</code> "
            "in a repo and writes its plan.</p></div></div>"
        )
    return HEAD + _header(repos, state, generated) + body + FOOT
