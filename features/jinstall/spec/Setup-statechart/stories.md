## 1. Installing, uninstall leaves ~/.local/state/jstack behind: No expert yet

Rule broken: Every path jstack made is recorded or not made: an uninstall leaves nothing behind.
Why: the install makes jstack's state folder before a record names it.
There are 1866 ways to get here in the model. This is the shortest.

0. Start: Nothing of jstack's on disk: No expert yet
1. You run install.sh: the install makes a folder. Now: Installing, uninstall removes it all: No expert yet
2. It makes ~/.local/state/jstack. Now: Installing, uninstall leaves ~/.local/state/jstack behind: No expert yet

## 2. Nothing of jstack's on disk: Expert in thread 2 starting, two webhooks live

Rule broken: An expert has at most one live webhook, and once a start has ended, its record names it and the thread it posts into.
Why: the new thread keeps no record of the webhook the last one made and never kept.
There are 1218 ways to get here in the model. This is the shortest.

0. Start: Nothing of jstack's on disk: No expert yet
1. You start the expert in thread 1. Now: Nothing of jstack's on disk: Expert in thread 1 starting, no webhook
2. T3 Code makes a webhook into this thread. Now: Nothing of jstack's on disk: Expert in thread 1 starting, a webhook no record names
3. The turn stops. Now: Nothing of jstack's on disk: Expert in thread 1, a webhook no record names, its turn stopped
4. You start the expert in thread 2. Now: Nothing of jstack's on disk: Expert in thread 2 starting, a webhook no record names
5. T3 Code makes a webhook into this thread. Now: Nothing of jstack's on disk: Expert in thread 2 starting, two webhooks live

## 3. Nothing of jstack's on disk: Expert in thread 1, its webhook kept, posting into thread 1, its address lost

Rule broken: Once a start has ended, the address kept is the kept webhook's.
Why: the turn stopped before it kept the address, and nothing writes it again.
There are 8526 ways to get here in the model. This is the shortest.

0. Start: Nothing of jstack's on disk: No expert yet
1. You start the expert in thread 1. Now: Nothing of jstack's on disk: Expert in thread 1 starting, no webhook
2. T3 Code makes a webhook into this thread. Now: Nothing of jstack's on disk: Expert in thread 1 starting, a webhook no record names
3. It keeps the new webhook. Now: Nothing of jstack's on disk: Expert in thread 1 starting, its webhook kept, posting into thread 1, its address not kept yet
4. The turn stops. Now: Nothing of jstack's on disk: Expert in thread 1, its webhook kept, posting into thread 1, its address lost, its turn stopped
5. You start the expert in thread 1. Now: Nothing of jstack's on disk: Expert in thread 1 starting, its webhook kept, posting into thread 1, its address not kept yet
6. It finds its own webhook kept. Now: Nothing of jstack's on disk: Expert in thread 1, its webhook kept, posting into thread 1, its address lost

## 4. Nothing of jstack's on disk: Expert in thread 1, a webhook no record names, its address lost

Rule broken: An expert has at most one live webhook, and once a start has ended, its record names it and the thread it posts into.
Why: the turn stopped before it kept the webhook it made.
There are 4872 ways to get here in the model. This is the shortest.

0. Start: Nothing of jstack's on disk: No expert yet
1. You start the expert in thread 1. Now: Nothing of jstack's on disk: Expert in thread 1 starting, no webhook
2. T3 Code makes a webhook into this thread. Now: Nothing of jstack's on disk: Expert in thread 1 starting, a webhook no record names
3. It keeps the new webhook. Now: Nothing of jstack's on disk: Expert in thread 1 starting, its webhook kept, posting into thread 1, its address not kept yet
4. The turn stops. Now: Nothing of jstack's on disk: Expert in thread 1, its webhook kept, posting into thread 1, its address lost, its turn stopped
5. You start the expert in thread 2. Now: Nothing of jstack's on disk: Expert in thread 2 starting, its webhook kept, posting into thread 1, its address not kept yet
6. It binds the webhook to this thread. Now: Nothing of jstack's on disk: Expert in thread 2 starting, a webhook no record names, its address not kept yet
7. The turn stops. Now: Nothing of jstack's on disk: Expert in thread 2, a webhook no record names, its address lost, its turn stopped
8. You start the expert in thread 1. Now: Nothing of jstack's on disk: Expert in thread 1 starting, a webhook no record names, its address not kept yet
9. It finds its own webhook kept. Now: Nothing of jstack's on disk: Expert in thread 1, a webhook no record names, its address lost
