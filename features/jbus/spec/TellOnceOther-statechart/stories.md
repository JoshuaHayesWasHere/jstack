## 1. A row red at two heads: not told, fails.json counts two heads, the row is held

Rule broken: "jbus drops no tell": between passes, an act still owed whose mark is written was taken, so a mark with no act never stands; one with no mark the next pass does. The home's stall the clock's home says went is in the log.
Why: the row is held, and the pass died before it paged the Chef.
There are 2 ways to get here in the model. This is the shortest.

0. Start: A row red at two heads: nothing owed yet
1. What calls for it comes to hold. Now: A row red at two heads: not told, fails.json counts two heads
2. A pass reaches it and reads its marks. Now: A row red at two heads: not told, fails.json counts two heads, a pass is in its step
3. The row is held. Now: A row red at two heads: not told, fails.json counts two heads, the row is held, a pass is in its step
4. The pass dies. Now: A row red at two heads: not told, fails.json counts two heads, the row is held

## 2. The second target's body: told twice, the body waits in the outbox, a pass is in its step

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

## 3. CI that starts no job: told twice, main's tip moved, a pass is in its step

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
