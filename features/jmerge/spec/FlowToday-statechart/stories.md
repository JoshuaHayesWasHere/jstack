## 1. Main green, machine full: 1 passed, merges after the other, 1 waiting to launch

Rule broken: "Work never stops flowing: once nothing more happens on its own and main is green, every pull request has merged."
Why: a crew left an idle process running at its pull request, which jbus stops only once its row ended, so the machine stays full and the next row never launches.
There are 8 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request. Now: Main green, machine full: 1 waiting for a check, 1 waiting to launch
2. Its check runs. Now: Main green, machine full: 1 passed, merges after the other, 1 waiting to launch

The design cannot take these steps: it starts on another screen.

## 2. Main green, machine full: 1 passed, merges after the other, 1 waiting to launch

Rule broken: "Once nothing more happens on its own, the machine has room."
Why: a crew left an idle process running at its pull request, and jbus stops an idle one only once its row ended.
There are 267 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request. Now: Main green, machine full: 1 waiting for a check, 1 waiting to launch
2. Its check runs. Now: Main green, machine full: 1 passed, merges after the other, 1 waiting to launch

The design cannot take these steps: it starts on another screen.

## 3. Main red from outside, machine full: 1 passed, waiting to merge, 1 waiting to launch

Rule broken: "While main is red and nothing else can happen, its fix waits only on your approval."
Why: an idle process a crew left fills the machine, so even an approved fix for main cannot start.
There are 261 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request. Now: Main green, machine full: 1 waiting for a check, 1 waiting to launch
2. Its check runs. Now: Main green, machine full: 1 passed, waiting to merge, 1 waiting to launch
3. Something outside breaks main. Now: Main red from outside, machine full: 1 passed, waiting to merge, 1 waiting to launch

The design cannot take these steps: it starts on another screen.

## 4. Main red from a merge, machine full: 1 merged, 1 waiting to launch

Rule broken: "A merge never turns main red."
Why: its check selects the test that reads the whole tree only by chance, so a change that breaks that test merges.
There are 244 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request. Now: Main green, machine full: 1 waiting for a check, 1 waiting to launch
2. Its check runs. Now: Main green, machine full: 1 passed, waiting to merge, 1 waiting to launch
3. It merges. Now: Main red from a merge, machine full: 1 merged, 1 waiting to launch

The design cannot take these steps: it starts on another screen.
