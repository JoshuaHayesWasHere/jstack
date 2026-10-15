# review-concurrency: let up to three reviews run at once instead of one at a time
Task: "Something is blocking our process and making a run in a one at a time basis or something" and, asked how many reviews may run at once: "three at a time".
Done when:
- The cause of reviews running one at a time is found and named in the PR description
- Up to three reviews run at the same time when three or more are queued
- A fourth review waits until one of the three finishes, then starts
- Scouts and crewmates run the same way as before the change
- The existing tests pass, and a new test covers the three-at-once limit and the fourth one waiting
Where: the code that launches and queues reviewers in jstack's Python commands, and any lock, semaphore or queue it uses
Do not touch: concurrency limits for scouts, crewmates or the home thread; playbooks and skills unrelated to review
Decisions: reviews may run "three at a time"
Design: none, the user set the limit and the fix is to find and loosen one blocking point
Pull request: ask first
Review: review
Playbook: none
