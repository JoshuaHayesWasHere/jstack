## 1. Checked at this head, not proved: a rebase record left behind

Rule broken: `RebaseRecorded`
Why: a rebase record stays after its push.
There are 5400 ways to get here in the model. This is the shortest.

0. Start: No check at this head: at work, no Result
1. The crew runs the check block. Now: the check runs: at work, no Result
2. The check block writes its Checked line, exit 0. Now: Checked at this head, not proved: at work, no Result
3. The crew writes its Result. Now: Checked at this head, not proved: the Result is written, no review yet
4. The crew runs proved.sh. Now: the proof runs: the Result is written, no review yet
5. Proved.sh writes its Proved line. Now: Checked and proved at this head: the Result is written, no review yet
6. Jbus launches the review. Now: Checked and proved at this head: the review runs
7. The reviewer writes its review. Now: Checked and proved at this head: reviewed, a finding to answer
8. GitHub says the pull request is in conflict. Now: Checked and proved at this head: the pull request is in conflict
9. The head is kept under pre-rebase. Now: Checked and proved at this head: rebasing
10. Git rebases. Now: No check at this head: rebased, not pushed
11. The crew runs the check block. Now: the check runs: rebased, not pushed
12. The check block writes its Checked line, exit 0. Now: Checked at this head, not proved: rebased, not pushed
13. The rebase is pushed with its lease. Now: Checked at this head, not proved: the rebase is pushed, its record not removed yet
14. The block is killed. Now: Checked at this head, not proved: a rebase record left behind
