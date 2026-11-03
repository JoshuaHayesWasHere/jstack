## 1. Main red from outside: 1 a draft, its review first, holds main's fix, 1 red only from main's break

Rule broken: "While main is red and nothing else can happen, its fix waits on nothing of yours but your word: the lift of a pull request you hold, or your approval of a row whose brief you must approve." Since #547 jbus approves every fix row it files, main's and the browser run's, by rule, so no approval of a fix row is yours.
Why: main's fix row closed with its fix in a follow-up that merges only after the other, and the other is red from main's break, which jmerge judges again only once main is green.
There are 40 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting to launch
2. Its review is written and fixed, and jmerge marks it ready. Now: Main green: 1 waiting for a check, 1 waiting to launch
3. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting for a check
4. Something outside breaks main. Now: Main red from outside, its run rerun: 1 a draft, its review first, 1 waiting for a check
5. Jbus reruns main's failed run, and it fails again. Now: Main red from outside: 1 a draft, its review first, 1 waiting for a check
6. Jbus judges main's red, and files its fix row. Now: Main red from outside, its fix row filed: 1 a draft, its review first, 1 waiting for a check
7. Jbus approves main's fix row by rule, and its crew puts the fix in an open pull request. Now: Main red from outside: 1 a draft, its review first, holds main's fix, 1 waiting for a check
8. Its check runs. Now: Main red from outside: 1 a draft, its review first, holds main's fix, 1 red only from main's break

The design cannot take these steps: it starts on another screen.

## 2. Main red from outside: 1 a draft, its review first, 1 holds main's fix, red from its own break

Rule broken: "While main is red and nothing else can happen, its fix waits on nothing of yours but your word: the lift of a pull request you hold, or your approval of a row whose brief you must approve." Since #547 jbus approves every fix row it files, main's and the browser run's, by rule, so no approval of a fix row is yours.
Why: the pull request that holds main's fix broke a test of its own, and its crew reads that failure as main's red, which only its merge ends.
There are 420 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting to launch
2. Its review is written and fixed, and jmerge marks it ready. Now: Main green: 1 waiting for a check, 1 waiting to launch
3. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting for a check
4. Something outside breaks main. Now: Main red from outside, its run rerun: 1 a draft, its review first, 1 waiting for a check
5. Jbus reruns main's failed run, and it fails again. Now: Main red from outside: 1 a draft, its review first, 1 waiting for a check
6. Jbus judges main's red, and files its fix row. Now: Main red from outside, its fix row filed: 1 a draft, its review first, 1 waiting for a check
7. Jbus approves main's fix row by rule, and its crew puts the fix in an open pull request. Now: Main red from outside: 1 a draft, its review first, 1 waiting for a check, holds main's fix
8. Its check runs. Now: Main red from outside: 1 a draft, its review first, 1 holds main's fix, red from its own break

The design cannot take these steps: it starts on another screen.

## 3. Main red from outside: 1 passed, holds main's fix, stacked on the other, 1 red only from main's break

Rule broken: "While main is red and nothing else can happen, its fix waits on nothing of yours but your word: the lift of a pull request you hold, or your approval of a row whose brief you must approve." Since #547 jbus approves every fix row it files, main's and the browser run's, by rule, so no approval of a fix row is yours.
Why: main's fix row closed with its fix in an open pull request that waits on another, which cannot move.
There are 75 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting to launch
2. Its review is written and fixed, and jmerge marks it ready. Now: Main green: 1 waiting for a check, 1 waiting to launch
3. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting for a check
4. Its review is written and fixed, and jmerge marks it ready. Now: Main green: 2 waiting for a check
5. Something outside breaks main. Now: Main red from outside, its run rerun: 2 waiting for a check
6. Jbus reruns main's failed run, and it fails again. Now: Main red from outside: 2 waiting for a check
7. Jbus judges main's red, and files its fix row. Now: Main red from outside, its fix row filed: 2 waiting for a check
8. Jbus approves main's fix row by rule, and its crew puts the fix in an open pull request. Now: Main red from outside: 1 waiting for a check, 1 waiting for a check, holds main's fix
9. Its check runs. Now: Main red from outside: 1 red only from main's break, 1 waiting for a check, holds main's fix
10. Its check runs. Now: Main red from outside: 1 passed, holds main's fix, stacked on the other, 1 red only from main's break

The design cannot take these steps: it starts on another screen.
