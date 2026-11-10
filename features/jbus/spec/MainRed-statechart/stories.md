## 1. Main red: two reverts open

Rule broken: At most one revert of jbus's is open at a time.
Why: main went green at a later commit and red again before a pass saw the green alone, so reverts.close, which waits for a green main, left the first revert open while culprits.judge opened a second for the new red.
There are 108 ways to get here in the model. This is the shortest.

0. Start: Main green: nothing open to fix it
1. A row's pull request merges. Now: Main's run going: nothing open to fix it
2. Jbus's pass reverts the one clear culprit. Now: Main red: a revert open
3. Jbus's pass reverts the one clear culprit. Now: Main red: two reverts open
