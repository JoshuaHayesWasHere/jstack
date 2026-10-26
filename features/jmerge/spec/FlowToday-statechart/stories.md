## 1. Main red from a merge, machine full: 1 merged, 1 waiting to launch

Rule broken: "A merge never turns main red."
Why: its check missed a test that reads the changed path past what the selector sees, so a change that breaks that test merges.
There are 244 ways to get here in the model. This is the shortest.

0. Start: Main green: 2 waiting to launch
1. Jbus launches its crew, which opens its pull request. Now: Main green, machine full: 1 waiting for a check, 1 waiting to launch
2. Its check runs. Now: Main green, machine full: 1 passed, waiting to merge, 1 waiting to launch
3. It merges. Now: Main red from a merge, machine full: 1 merged, 1 waiting to launch

The design cannot take these steps: it starts on another screen.
