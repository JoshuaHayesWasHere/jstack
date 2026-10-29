## 1. Main green: 1 a draft, its review first, 1 a draft, waiting on your word

Rule broken: "Work never stops flowing: once nothing more happens on its own and main is green, it settles merged or waiting on your word."
Why: a draft that touches a path that needs you is held before jmerge marks it ready, and jmerge --accept refuses a draft, so your word cannot move it.
There are 280 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, waiting on your word, 1 waiting to launch
2. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 a draft, waiting on your word

The design cannot take these steps: it starts on another screen.

## 2. Main red from outside: 2 a draft, its review first

Rule broken: "While main is red and nothing else can happen, its fix waits only on your approval, or on your word for its pull request."
Why: main's fix row closed with its fix in an open draft, which jmerge never marks ready while main is red, so its check never runs to prove the fix.
There are 768 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting to launch
2. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 2 a draft, its review first
3. Something outside breaks main. Now: Main red from outside: 2 a draft, its review first
4. You approve main's fix, and its crew puts it in an open pull request. Now: Main red from outside: 2 a draft, its review first

The design cannot take these steps: it starts on another screen.

## 3. Main red from a merge, machine full: 1 merged, 1 waiting to launch

Rule broken: "A merge never turns main red."
Why: its check missed a test that reads the changed path past what the selector sees, so a change that breaks that test merges.
There are 3236 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green, machine full: 1 a draft, its review first, 1 waiting to launch
2. Its review is written and fixed, and jmerge marks it ready. Now: Main green, machine full: 1 waiting for a check, 1 waiting to launch
3. Its check runs. Now: Main green, machine full: 1 passed, waiting to merge, 1 waiting to launch
4. It merges. Now: Main red from a merge, machine full: 1 merged, 1 waiting to launch

The design cannot take these steps: it starts on another screen.

## 4. Main red from outside: 1 a draft, its review first, 1 passed, holds main's fix, not proved

Rule broken: "While main is red and nothing else can happen, its fix waits only on your approval, or on your word for its pull request."
Why: main's fix row closed with its fix in an open pull request, whose check proves the fix only if it ran each test main failed, and the selector reads the diff, not those tests.
There are 64 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting to launch
2. Its review is written and fixed, and jmerge marks it ready. Now: Main green: 1 waiting for a check, 1 waiting to launch
3. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting for a check
4. Something outside breaks main. Now: Main red from outside: 1 a draft, its review first, 1 waiting for a check
5. You approve main's fix, and its crew puts it in an open pull request. Now: Main red from outside: 1 a draft, its review first, 1 waiting for a check
6. Its check runs. Now: Main red from outside: 1 a draft, its review first, 1 passed, holds main's fix, not proved

The design cannot take these steps: it starts on another screen.

## 5. Main red from outside: 1 a draft, its review first, 1 holds main's fix, red from its own break

Rule broken: "While main is red and nothing else can happen, its fix waits only on your approval, or on your word for its pull request."
Why: the pull request that holds main's fix broke a test of its own, and its crew reads that failure as main's red, which only its merge ends.
There are 32 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting to launch
2. Its review is written and fixed, and jmerge marks it ready. Now: Main green: 1 waiting for a check, 1 waiting to launch
3. Jbus launches its crew, which opens its pull request as a draft. Now: Main green: 1 a draft, its review first, 1 waiting for a check
4. Something outside breaks main. Now: Main red from outside: 1 a draft, its review first, 1 waiting for a check
5. You approve main's fix, and its crew puts it in an open pull request. Now: Main red from outside: 1 a draft, its review first, 1 waiting for a check
6. Its check runs. Now: Main red from outside: 1 a draft, its review first, 1 holds main's fix, red from its own break

The design cannot take these steps: it starts on another screen.
