A reviewer that is to run again is sent `/pr-review run {slug} again`, always.
The reviewer takes `again` whether or not the brief has a `## Review` section: with one it is a second pass, and with none it is the review the brief is still owed.
The plain `/pr-review run {slug}` is the message of a first launch and nothing else: a reviewer that finds a `## Review` under it stops, and says the line above.
