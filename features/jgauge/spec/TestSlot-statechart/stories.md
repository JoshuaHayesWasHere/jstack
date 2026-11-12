## 1. Usage ledger: the ledger keeps the records of jbus, the status line wrote and its record is gone, the last capped read is older than the ledger

Rule broken: LedgerNoLostUpdate: no ledger write drops another's. Each record a writer merged in is still in the ledger, so a cap one writer recorded is never undone by another's older copy.
Why: two writers read the ledger at once, and the second write put back the copy it read, without the first one's record.
There are 776 ways to get here in the model. This is the shortest.

0. Start: Usage ledger: the ledger keeps the records of no one
1. A writer reads the ledger. Now: Usage ledger: the ledger keeps the records of no one, the status line merges into the copy it read, of no one
2. A writer reads the ledger. Now: Usage ledger: the ledger keeps the records of no one, the status line merges into the copy it read, of no one, jbus merges into the copy it read, of no one
3. A writer writes the ledger. Now: Usage ledger: the ledger keeps the records of the status line, jbus merges into the copy it read, of no one, the last capped read is older than the ledger
4. A writer writes the ledger. Now: Usage ledger: the ledger keeps the records of jbus, the status line wrote and its record is gone, the last capped read is older than the ledger

## 2. Full lane: the slot held by a desk's run, the crew is woken, its claim holds, the woken crew found its slot taken

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
