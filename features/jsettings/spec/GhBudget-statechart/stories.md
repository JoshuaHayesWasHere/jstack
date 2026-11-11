## 1. The API budget at the floor: a call starts at the floor, the call log past its size, no old log

Rule broken: No call starts while the kept budget is under the floor: each call that runs began with `logged` reading more than FLOOR left, or reading nothing. At the floor counts as under it, as `held` counts it.
Why: a pass reads the budget once, as it starts, and goes on calling while its own calls and another pass's take the budget to the floor.
There are 2520 ways to get here in the model. This is the shortest.

0. Start: The API budget above the floor: no call, no call log, no old log
1. A pass starts a gh call in a free slot. Now: The API budget above the floor: a call under way, no call log, no old log
2. The call's line goes in the log. Now: The API budget above the floor: a call under way, the call log has room, no old log
3. The API answers the call and counts it. Now: The API budget at the floor: a call under way, the call log has room, no old log
4. The call's line goes in the log. Now: The API budget at the floor: a call under way, the call log past its size, no old log
5. A pass starts a gh call in a free slot. Now: The API budget at the floor: a call starts at the floor, the call log past its size, no old log

## 2. The API budget spent: a call under way, no call log, a full log lost

Rule broken: A rotation never drops lines another rotation kept: gh-calls.old.jsonl holds the whole log that a rename found past KEPT, and never a log a second rename moved over it before that log grew past KEPT.
Why: two processes found the log past its size at once: the first renamed it to the old log, a call started a new log, and the second renamed that one over the old log, so the whole log the first kept is gone.
There are 3316 ways to get here in the model. This is the shortest.

0. Start: The API budget above the floor: no call, no call log, no old log
1. A pass starts a gh call in a free slot. Now: The API budget above the floor: a call under way, no call log, no old log
2. The call's line goes in the log. Now: The API budget above the floor: a call under way, the call log has room, no old log
3. The call's line goes in the log. Now: The API budget above the floor: a call under way, the call log past its size, no old log
4. The API answers the call and counts it. Now: The API budget at the floor: a call under way, the call log past its size, no old log
5. The API answers the call and counts it. Now: The API budget spent: a call under way, the call log past its size, no old log
6. The process renames the log to the old log. Now: The API budget spent: a call under way, no call log, the old log keeps the last full log
7. The call's line goes in the log. Now: The API budget spent: a call under way, the call log has room, the old log keeps the last full log
8. The process renames the log to the old log. Now: The API budget spent: a call under way, no call log, a full log lost
