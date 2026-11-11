## 1. A row red at two heads: not told, fails.json counts two heads, the row is held

Rule broken: "jbus drops no tell": between passes, an act still owed whose mark is written was taken, so a mark with no act never stands; one with no mark the next pass does. The home's stall the clock's home says went is in the log.
Why: the row is held, and the pass died before it paged the Chef.
There are 2 ways to get here in the model. This is the shortest.

0. Start: A row red at two heads: nothing owed yet
1. What calls for it comes to hold. Now: A row red at two heads: not told, fails.json counts two heads
2. A pass reaches it and reads its marks. Now: A row red at two heads: not told, fails.json counts two heads, a pass is in its step
3. The row is held. Now: A row red at two heads: not told, fails.json counts two heads, the row is held, a pass is in its step
4. The pass dies. Now: A row red at two heads: not told, fails.json counts two heads, the row is held

## 2. An ask owed after a limit: told twice, owed.json says owed, a pass is in its step

Rule broken: "jbus tells no one twice": the receiver takes each act once, a repeat after a pass that died being one it takes as the same, and no pass does an act again once its guard read the act's mark.
Why: failover's carry-on quoted the ask, and the pass died before it closed the ask.
There are 12 ways to get here in the model. This is the shortest.

0. Start: An ask owed after a limit: nothing owed yet
1. What calls for it comes to hold. Now: An ask owed after a limit: not told, owed.json says owed
2. Failover carries the thread on, the ask quoted. Now: An ask owed after a limit: told once, owed.json says owed, a pass is in its step
3. The pass dies. Now: An ask owed after a limit: told once, owed.json says owed
4. A pass reaches it and reads its marks. Now: An ask owed after a limit: told once, owed.json says owed, a pass is in its step
5. The receiver takes it. Now: An ask owed after a limit: told twice, owed.json says owed, a pass is in its step

## 3. The second target's body: told twice, the body waits in the outbox, a pass is in its step

Rule broken: "jbus tells no one twice": the receiver takes each act once, a repeat after a pass that died being one it takes as the same, and no pass does an act again once its guard read the act's mark.
Why: the body went, and the pass died before the outbox dropped it.
This is the only way to get here in the model.

0. Start: The second target's body: nothing owed yet
1. What calls for it comes to hold. Now: The second target's body: not told, the body waits in the outbox
2. A pass reaches it and reads its marks. Now: The second target's body: not told, the body waits in the outbox, a pass is in its step
3. The receiver takes it. Now: The second target's body: told once, the body waits in the outbox, a pass is in its step
4. The pass dies. Now: The second target's body: told once, the body waits in the outbox
5. A pass reaches it and reads its marks. Now: The second target's body: told once, the body waits in the outbox, a pass is in its step
6. The receiver takes it. Now: The second target's body: told twice, the body waits in the outbox, a pass is in its step

## 4. A merge that changed a skill: told twice, reload.json owes it, a pass is in its step

Rule broken: "jbus tells no one twice": the receiver takes each act once, a repeat after a pass that died being one it takes as the same, and no pass does an act again once its guard read the act's mark.
Why: the notice went, the pass died before it marked the merges, a new merge came.
There are 7 ways to get here in the model. This is the shortest.

0. Start: A merge that changed a skill: nothing owed yet
1. What calls for it comes to hold. Now: A merge that changed a skill: not told, reload.json owes it
2. A pass reaches it and reads its marks. Now: A merge that changed a skill: not told, reload.json owes it, a pass is in its step
3. The receiver takes it. Now: A merge that changed a skill: told once, reload.json owes it, a pass is in its step
4. The pass dies. Now: A merge that changed a skill: told once, reload.json owes it
5. A pass reaches it and reads its marks. Now: A merge that changed a skill: told once, reload.json owes it, a pass is in its step
6. The receiver takes it. Now: A merge that changed a skill: told twice, reload.json owes it, a pass is in its step

## 5. CI that starts no job: told twice, main's tip moved, a pass is in its step

Rule broken: "jbus tells no one twice": the receiver takes each act once, a repeat after a pass that died being one it takes as the same, and no pass does an act again once its guard read the act's mark.
Why: the question was parked, the pass died before account.json kept it, main moved.
This is the only way to get here in the model.

0. Start: CI that starts no job: nothing owed yet
1. What calls for it comes to hold. Now: CI that starts no job: not told
2. A pass reaches it and reads its marks. Now: CI that starts no job: not told, a pass is in its step
3. The receiver takes it. Now: CI that starts no job: told once, a pass is in its step
4. The pass dies. Now: CI that starts no job: told once
5. The key the next try names changes. Now: CI that starts no job: told once, main's tip moved
6. A pass reaches it and reads its marks. Now: CI that starts no job: told once, main's tip moved, a pass is in its step
7. The receiver takes it. Now: CI that starts no job: told twice, main's tip moved, a pass is in its step

## 6. The user's word: told twice, the home's thread changed, a pass is in its step

Rule broken: "jbus tells no one twice": the receiver takes each act once, a repeat after a pass that died being one it takes as the same, and no pass does an act again once its guard read the act's mark.
Why: the word went, the pass died before it wrote so, and the home's thread changed.
There are 9 ways to get here in the model. This is the shortest.

0. Start: The user's word: nothing owed yet
1. What calls for it comes to hold. Now: The user's word: not told
2. A pass reaches it and reads its marks. Now: The user's word: not told, a pass is in its step
3. The receiver takes it. Now: The user's word: told once, a pass is in its step
4. The pass dies. Now: The user's word: told once
5. The key the next try names changes. Now: The user's word: told once, the home's thread changed
6. A pass reaches it and reads its marks. Now: The user's word: told once, the home's thread changed, a pass is in its step
7. The receiver takes it. Now: The user's word: told twice, the home's thread changed, a pass is in its step

## 7. The wait clock: told once, the clock says its home was told, sent.json has its key, the stall's key is written, no stall in the log

Rule broken: "jbus drops no tell": between passes, an act still owed whose mark is written was taken, so a mark with no act never stands; one with no mark the next pass does. The home's stall the clock's home says went is in the log.
Why: the stall's key is written, and the pass died before its line went in the log.
There are 24 ways to get here in the model. This is the shortest.

0. Start: The wait clock: nothing owed yet
1. What calls for it comes to hold. Now: The wait clock: not told, the clock is counting
2. A pass counts on its clock. Now: The wait clock: not told, the clock is due
3. A pass reaches it and reads its marks. Now: The wait clock: not told, the clock is due, a pass is in its step
4. The receiver takes it. Now: The wait clock: told once, the clock is due, a pass is in its step
5. Its key goes in sent.json. Now: The wait clock: told once, the clock is due, sent.json has its key, a pass is in its step
6. Its own file says done. Now: The wait clock: told once, the clock says jbus acted, counting again, sent.json has its key
7. The pass writes the stall's key. Now: The wait clock: told once, the clock says jbus acted, counting again, sent.json has its key, the stall's key is written, no stall in the log, a pass is in its step
8. The pass dies. Now: The wait clock: told once, the clock says jbus acted, counting again, sent.json has its key, the stall's key is written, no stall in the log
9. The pass writes the stall's key. Now: The wait clock: told once, the clock says jbus acted, counting again, sent.json has its key, the stall's key is written, no stall in the log, a pass is in its step
10. The clock writes that its home was told. Now: The wait clock: told once, the clock says its home was told, sent.json has its key, the stall's key is written, no stall in the log
