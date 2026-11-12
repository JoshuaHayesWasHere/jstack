## 1. Installing, uninstall leaves ~/.local/state/jstack behind: No expert yet

Rule broken: Every path jstack made is recorded or not made: an uninstall leaves nothing behind.
Why: the install makes jstack's state folder before a record names it.
There are 1182 ways to get here in the model. This is the shortest.

0. Start: Nothing of jstack's on disk: No expert yet
1. You run install.sh: the install makes a folder. Now: Installing, uninstall removes it all: No expert yet
2. It makes ~/.local/state/jstack. Now: Installing, uninstall leaves ~/.local/state/jstack behind: No expert yet
