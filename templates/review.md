## Review
By: <the line Start printed: the provider, the model and the effort, or inherit>
Verdict: clean | findings
Head: <the pull request's head commit, in full>   Unchanged by the review: yes | no
Patch-id: <`git patch-id --stable` of the diff from the base to that head>
Reviewers: 1, <how many findings the reading gave>   Proof: <the command that ran>, exit <its exit code>, <the last line or two it printed> | unproven, <the fact>
Meets the brief: yes | no, and then each `Done when` line a finding says is not met
In flight: none | <each pull request or brief that shares a file, and the files>
Findings:
- <severity> <file>:<line> <what is wrong> (principle: <name> | none) (bucket: Act on | Consider) (risk: <area>, only on security, auth, billing, data, migrations or concurrency) (or the one word "none")
Dropped: <how many findings were outside the diff: the number only>
Noted: <how many findings the lead judged true and not worth acting on: the number only>
Dismissed: <how many findings the lead dismissed, and under this line one line for each, or none>
- <severity> <file>:<line> <what is wrong> (principle: <name> | none) (dismissed: <the reason, in one line>)
Sent to: <the thread id the findings went to, or "not sent" and why>
