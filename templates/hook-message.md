$first[home] This thread opened in the main checkout of $repo, which has no home yet: this thread is its first, and the home skill makes $home_dir.
[home] This thread opened in the main checkout of $repo, which has a home at $home_dir.
This thread is that repo's home. Before replying to the user's first message, invoke the home skill and follow it.
The first message is the user's opening request, not a command: give the skill's short status, then take the message as the start of planning.
A first message that starts with /home is that command and not a request: follow the home skill with it as typed, the words after /home included.
Do not do this if the first message starts with /crew, /expert, /nohome or /handoff: follow that skill instead.
The user can type /nohome at any time to make this an ordinary thread.
