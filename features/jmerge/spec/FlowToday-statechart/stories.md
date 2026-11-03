## 1. Main green: 2 a draft, waiting on your word

Rule broken: "Work never stops flowing: once nothing more happens on its own and main is green, it settles merged or waiting on your word."
Why: a draft that touches a path that needs you is held before jmerge marks it ready, and jmerge --accept refuses a draft, so your word cannot move it.
There are 100 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, waiting on your word, 1 waiting to launch
2. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 2 a draft, waiting on your word

The design cannot take these steps: it starts on another screen.

## 2. Main red from a merge, its run rerun, machine full: 1 merged, 1 waiting to launch

Rule broken: "A merge never turns main red."
Why: its check missed a test that reads the changed path past what the selector sees, so a change that breaks that test merges.
This is the only way to get here in the model.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green, machine full: 1 a draft, its review first, 1 waiting to launch
2. Its review is written and fixed, and jmerge marks it ready. Now: Main green, machine full: 1 waiting for a check, 1 waiting to launch
3. Its check runs. Now: Main green, machine full: 1 passed, waiting to merge, 1 waiting to launch
4. It merges. Now: Main red from a merge, its run rerun, machine full: 1 merged, 1 waiting to launch

The design cannot take these steps: it starts on another screen.

## 3. Main red from outside: 1 a draft, waiting on your word, 1 a draft, waiting on your word, holds main's fix

Rule broken: "While main is red and nothing else can happen, its fix waits only on your approval, or on your word for its pull request." Since #547 jbus approves both fix rows it files, main's and the browser run's, by rule, so no approval of a fix row is yours: of the rule's waits, only your word is still yours, the go of a row you held or whose brief changed (Approve) and the lift of a pull request's hold (Accept).
Why: main's fix row closed with its fix in an open draft, which jmerge never marks ready while it waits on your word, and jmerge --accept refuses a draft.
There are 168 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, waiting on your word, 1 waiting to launch
2. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 2 a draft, waiting on your word
3. Something outside breaks main. Now: Main red from outside, its run rerun: 2 a draft, waiting on your word
4. Jbus reruns main's failed run, and it fails again. Now: Main red from outside: 2 a draft, waiting on your word
5. Jbus judges main's red, and files its fix row. Now: Main red from outside, its fix row filed: 2 a draft, waiting on your word
6. Jbus approves main's fix row by rule, and its crew puts the fix in an open pull request. Now: Main red from outside: 1 a draft, waiting on your word, 1 a draft, waiting on your word, holds main's fix

The design cannot take these steps: it starts on another screen.

## 4. Main red from outside: 1 a draft, waiting on your word, 1 passed, holds main's fix, stacked on the other

Rule broken: "While main is red and nothing else can happen, its fix waits only on your approval, or on your word for its pull request." Since #547 jbus approves both fix rows it files, main's and the browser run's, by rule, so no approval of a fix row is yours: of the rule's waits, only your word is still yours, the go of a row you held or whose brief changed (Approve) and the lift of a pull request's hold (Accept).
Why: main's fix row closed with its fix in an open pull request that waits on another, which cannot move.
There are 20 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, waiting on your word, 1 waiting to launch
2. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 a draft, waiting on your word
3. Its review is written and fixed, and jmerge marks it ready. Now: Main green: 1 a draft, waiting on your word, 1 waiting for a check
4. Something outside breaks main. Now: Main red from outside, its run rerun: 1 a draft, waiting on your word, 1 waiting for a check
5. Jbus reruns main's failed run, and it fails again. Now: Main red from outside: 1 a draft, waiting on your word, 1 waiting for a check
6. Jbus judges main's red, and files its fix row. Now: Main red from outside, its fix row filed: 1 a draft, waiting on your word, 1 waiting for a check
7. Jbus approves main's fix row by rule, and its crew puts the fix in an open pull request. Now: Main red from outside: 1 a draft, waiting on your word, 1 waiting for a check, holds main's fix
8. Its check runs. Now: Main red from outside: 1 a draft, waiting on your word, 1 passed, holds main's fix, stacked on the other

The design cannot take these steps: it starts on another screen.

## 5. Main red from outside: 1 a draft, waiting on your word, 1 holds main's fix, red from its own break

Rule broken: "While main is red and nothing else can happen, its fix waits only on your approval, or on your word for its pull request." Since #547 jbus approves both fix rows it files, main's and the browser run's, by rule, so no approval of a fix row is yours: of the rule's waits, only your word is still yours, the go of a row you held or whose brief changed (Approve) and the lift of a pull request's hold (Accept).
Why: the pull request that holds main's fix broke a test of its own, and its crew reads that failure as main's red, which only its merge ends.
There are 68 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, waiting on your word, 1 waiting to launch
2. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 a draft, waiting on your word
3. Its review is written and fixed, and jmerge marks it ready. Now: Main green: 1 a draft, waiting on your word, 1 waiting for a check
4. Something outside breaks main. Now: Main red from outside, its run rerun: 1 a draft, waiting on your word, 1 waiting for a check
5. Jbus reruns main's failed run, and it fails again. Now: Main red from outside: 1 a draft, waiting on your word, 1 waiting for a check
6. Jbus judges main's red, and files its fix row. Now: Main red from outside, its fix row filed: 1 a draft, waiting on your word, 1 waiting for a check
7. Jbus approves main's fix row by rule, and its crew puts the fix in an open pull request. Now: Main red from outside: 1 a draft, waiting on your word, 1 waiting for a check, holds main's fix
8. Its check runs. Now: Main red from outside: 1 a draft, waiting on your word, 1 holds main's fix, red from its own break

The design cannot take these steps: it starts on another screen.
