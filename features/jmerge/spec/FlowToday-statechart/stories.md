## 1. Main red from a merge: 1 merged, 1 waiting for a check

Rule broken: "A merge never turns main red."
Why: its check skipped the test that reads the whole tree, so a change that breaks that test merges.
There are 74 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting for a check
1. Its check runs. Now: Main green: 1 passed, waiting to merge, 1 waiting for a check
2. It merges. Now: Main red from a merge: 1 merged, 1 waiting for a check

With the three fixes, step 2 (it merges) takes you to: Main green: 1 merged, 1 waiting for a check.

## 2. Main green: 1 merged, 1 red, its own break hidden behind main's

Rule broken: "Work never stops flowing: once nothing more happens on its own and main is green, every pull request has merged."
Why: its own break failed while main was red too, so its crew reads it as main's and waits for a message nothing sends.
There are 11 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting for a check
1. Its check runs. Now: Main green: 1 passed, waiting to merge, 1 waiting for a check
2. It merges. Now: Main red from a merge: 1 merged, 1 waiting for a check
3. Its check runs. Now: Main red from a merge: 1 merged, 1 red, its own break hidden behind main's
4. You approve main's fix. Now: Main green: 1 merged, 1 red, its own break hidden behind main's

With the three fixes, step 2 (it merges) takes you to: Main green: 1 merged, 1 waiting for a check.

## 3. Main green: 2 red only from main's break

Rule broken: "Work never stops flowing: once nothing more happens on its own and main is green, every pull request has merged."
Why: the pull request went red while main was red, and nothing checks it again once main is fixed.
There are 13 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting for a check
1. Something outside breaks main. Now: Main red from outside: 2 waiting for a check
2. Its check runs. Now: Main red from outside: 1 red only from main's break, 1 waiting for a check
3. Its check runs. Now: Main red from outside: 2 red only from main's break
4. You approve main's fix. Now: Main green: 2 red only from main's break

With the three fixes you see the same screens and steps, yet the rule holds, so the state labels do not show what the three fixes changes.

## 4. Main green, machine full: 1 merged, 1 red, its own break

Rule broken: "Work never stops flowing: once nothing more happens on its own and main is green, every pull request has merged."
Why: a crew left processes running, the machine stays full, and nothing new can start.
There are 8 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting for a check
1. Its check runs. Now: Main green: 1 red, its own break, 1 waiting for a check
2. Its crew fixes its change. Now: Main green, machine full: 2 waiting for a check
3. Its check runs. Now: Main green, machine full: 1 passed, waiting to merge, 1 waiting for a check
4. It merges. Now: Main green, machine full: 1 merged, 1 waiting for a check
5. Its check runs. Now: Main green, machine full: 1 merged, 1 red, its own break

With the three fixes you see the same screens and steps, yet the rule holds, so the state labels do not show what the three fixes changes.

## 5. Main red from outside, machine full: 2 passed, waiting to merge

Rule broken: "Once nothing more happens on its own, the machine has room."
Why: a crew left processes running, and nothing stops them.
There are 93 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting for a check
1. Its check runs. Now: Main green: 1 passed, waiting to merge, 1 waiting for a check
2. Its check runs. Now: Main green: 1 passed, waiting to merge, 1 red, its own break
3. Its crew fixes its change. Now: Main green, machine full: 1 passed, waiting to merge, 1 waiting for a check
4. Its check runs. Now: Main green, machine full: 2 passed, waiting to merge
5. Something outside breaks main. Now: Main red from outside, machine full: 2 passed, waiting to merge

With the three fixes you see the same screens and steps, yet the rule holds, so the state labels do not show what the three fixes changes.

## 6. Main red from outside, machine full: 2 passed, waiting to merge

Rule broken: "While main is red and nothing else can happen, its fix waits only on your approval."
Why: the machine is full, so even an approved fix for main cannot start.
There are 80 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting for a check
1. Its check runs. Now: Main green: 1 passed, waiting to merge, 1 waiting for a check
2. Its check runs. Now: Main green: 1 passed, waiting to merge, 1 red, its own break
3. Its crew fixes its change. Now: Main green, machine full: 1 passed, waiting to merge, 1 waiting for a check
4. Its check runs. Now: Main green, machine full: 2 passed, waiting to merge
5. Something outside breaks main. Now: Main red from outside, machine full: 2 passed, waiting to merge

With the three fixes you see the same screens and steps, yet the rule holds, so the state labels do not show what the three fixes changes.
