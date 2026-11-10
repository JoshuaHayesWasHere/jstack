# The corrections count

`corrections.py` counts the messages in which the user corrects a home's reply, by the cause of the correction, over a window.
It reruns the hand count of the scout po-home-replies-scout (2026-11-10), whose classes it keeps: the audit's own classifier scripts are not on disk.

```sh
uv run --script features/evals/corrections/corrections.py --since 2026-11-02 --until 2026-11-09
```

It prints one line for the whole window, then one row per class: the count, the key and the class.
`--list` prints each correction too, as its place among the window's messages, when, its class, its thread, and the first words of the message and of the reply it answers.
`--store` reads another store than T3 Code's own, `~/.t3/userdata/statev2.sqlite`.
The store is opened read only (`mode=ro`) and nothing is written.

## The window

`--since` and `--until` each take a day, `YYYY-MM-DD`, or an ISO time.
A day starts at the user's local midnight, the machine's `TZ`, and the day `--until` names is counted whole.
An ISO time with no zone is local too.

## What is counted

The messages are the user's own: role `user` and `createdBy` `user`, so an agent's `t3_thread_send` is not one.
They are those of the threads whose title starts `home: `, the home of a repo and each scoped home, the archived ones too.
A message's words are its text with each `[Assistant quote](...)` cut down to the comment the user wrote on the quote, and each pasted picture cut out.
The quoted text is the home's, not the user's, so it decides nothing.

A message is a correction when its thread has a reply before it and a cue of a class matches its words.
The classes are tried in this order, and the first whose cue matches is the message's class:

| Key | Class | Its cues, in short |
|---|---|---|
| `unchecked` | a fact not checked before it was said | "is that accurate", "are you guessing", "no guessing", "want accurate", "wasn't it", "but we did", "going in circles", "already done", "turned that off", "turned back off", "I thought we", "we are supposed to" |
| `visual` | a visual that missed the ask | "not what I asked", "wrong report" (or chart, diagram, picture, image, page), "no lines should cross", "top down", "open this in my browser", "more screenshots", "this confuses me" |
| `missing` | a rule that is missing | "what are these", "what report", "where did that rule come from", "in the future" |
| `broken` | a skill rule the reply broke | "$unslop the", "needs me explicit" |

The cues themselves are the `CLASSES` table at the top of `corrections.py`, each a regular expression matched without regard to case.
Over 2026-11-02 to 2026-11-09 it counts 10, 7, 4 and 2, the scout's own counts, and the same 23 messages the scout quoted.

## What it misses

The cues were read off that one week's 23 corrections, so they are the words the user used then, not a model of a correction.
Read a count from another week as a floor that holds for the same words, and run `--list` to read what it took.

- A correction in other words is not counted: "that's wrong" or "no, check again" match no cue, and the count says nothing of them.
- A message is put in one class by the order of the table, by its words alone: it does not read the reply, so a complaint about a chart that says "is that accurate" is `unchecked`, and a message that corrects two things is counted once.
- A cue can match a message that corrects nothing, a request that happens to say "top down" or "in the future"; the reply before it is required, so a thread's first message is never one.
- A quote whose comment is `go` or `approved` matches no cue, as the scout ruled: it is an approval.
- The scout's other exclusions (the exact-words complaints, the sidebar and routing corrections, a turned-down design) are not cues, and they are not counted only because no cue matches them.
- A home thread is one by its title: a home whose thread was renamed, or a thread named `home: ` that is no home, is read by the title it has now.
