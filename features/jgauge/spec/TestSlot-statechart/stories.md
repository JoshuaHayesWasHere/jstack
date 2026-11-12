## 1. Full lane: the slot held by a desk's run, the crew is woken, its claim holds, the woken crew found its slot taken

Rule broken: WokenGetsSlot: a woken waiter gets the slot or its claim lapses at HOLDS. A crew jbus woke, that runs its command again while the wake's claim holds, finds its slot free.
Why: jbus counted the free slot outside the waiters' lock and recorded the wake after its message went, and a call with no thread took the slot in between.
There are 300 ways to get here in the model. This is the shortest.

0. Start: Full lane: the slot free
1. A call to test-slot starts. Now: Full lane: the slot free
2. A call to test-slot starts. Now: Full lane: the slot free
3. The call counts the slots to spare. Now: Full lane: the slot held by a desk's run
4. The slot is let go. Now: Full lane: the slot free
5. A call to test-slot starts. Now: Full lane: the slot free
6. The crew registers as a waiter and ends its turn. Now: Full lane: the slot free, the crew waits, not woken
7. A call to test-slot starts. Now: Full lane: the slot free, the crew waits, not woken
8. The jbus pass counts the slots to spare, with no lock. Now: Full lane: the slot free, the crew waits, not woken, jbus sends a wake for a slot it counted free
9. The call counts the slots to spare. Now: Full lane: the slot held by a desk's run, the crew waits, not woken, jbus sends a wake for a slot it counted free
10. The jbus pass records the wake. Now: Full lane: the slot held by a desk's run, the crew is woken, its claim holds
11. The call counts the slots to spare. Now: Full lane: the slot held by a desk's run, the crew is woken, its claim holds, the woken crew found its slot taken
