## 1. Main red from a merge, machine full: 1 merged, 1 waiting to launch

Rule broken: "A merge never turns main red."
Why: its check missed a test that reads the changed path past what the selector sees, so a change that breaks that test merges.
There are 2554 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request. Now: Main green, machine full: 1 waiting for a check, 1 waiting to launch
2. Its check runs. Now: Main green, machine full: 1 passed, waiting to merge, 1 waiting to launch
3. It merges. Now: Main red from a merge, machine full: 1 merged, 1 waiting to launch

The design cannot take these steps: it starts on another screen.

## 2. Main red from outside: 1 passed, holds main's fix, not proved, 1 passed, waiting to merge

Rule broken: "While main is red and nothing else can happen, its fix waits only on your approval."
Why: main's fix row closed with its fix in an open pull request, whose check proves the fix only if it ran each test main failed, and the selector reads the diff, not those tests.
There are 148 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request. Now: Main green: 1 waiting for a check, 1 waiting to launch
2. Its check runs. Now: Main green: 1 passed, waiting to merge, 1 waiting to launch
3. Jbus launches its crew, which opens its pull request. Now: Main green: 1 passed, waiting to merge, 1 waiting for a check
4. Something outside breaks main. Now: Main red from outside: 1 passed, waiting to merge, 1 waiting for a check
5. You approve main's fix, and its crew puts it in an open pull request. Now: Main red from outside: 1 passed, waiting to merge, 1 waiting for a check
6. Its check runs. Now: Main red from outside: 1 passed, holds main's fix, not proved, 1 passed, waiting to merge

The design cannot take these steps: it starts on another screen.

## 3. Main red from outside: 1 holds main's fix, red from its own break, 1 passed, waiting to merge

Rule broken: "While main is red and nothing else can happen, its fix waits only on your approval."
Why: the pull request that holds main's fix broke a test of its own, and its crew reads that failure as main's red, which only its merge ends.
There are 68 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request. Now: Main green: 1 waiting for a check, 1 waiting to launch
2. Its check runs. Now: Main green: 1 passed, waiting to merge, 1 waiting to launch
3. Jbus launches its crew, which opens its pull request. Now: Main green: 1 passed, waiting to merge, 1 waiting for a check
4. Something outside breaks main. Now: Main red from outside: 1 passed, waiting to merge, 1 waiting for a check
5. You approve main's fix, and its crew puts it in an open pull request. Now: Main red from outside: 1 passed, waiting to merge, 1 waiting for a check
6. Its check runs. Now: Main red from outside: 1 holds main's fix, red from its own break, 1 passed, waiting to merge

The design cannot take these steps: it starts on another screen.
