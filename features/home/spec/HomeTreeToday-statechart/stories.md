## 1. Child a retired, crew out: nothing for you

Rule broken: No child retires while a call, gate, pull request or crew thread of its is open.
Why: nothing checks what a scope has out when its handoff ends it.
Not listed: no config of HomeTreeDesign.tla expects TLC to break this rule. None of its configs expects TLC to break a rule.
There are 680 ways to get here in the model. This is the shortest.

0. Start: No child yet: nothing for you
1. The root makes child a. Now: Child a working: nothing for you
2. Child a launches a crew. Now: Child a working, crew out: nothing for you
3. You retire child a. Now: Child a retired, crew out: nothing for you

In the design, step 3 (you retire child a) cannot happen, so you stay at: Child a working, crew out: nothing for you.

## 2. Child a working, crew out, quiet for its patience: nothing for you

Rule broken: The root flags a child within K checks of observable quiet with work out, and a routine on a missed beat, from signals the child does not send.
Why: a hung thread is a quiet event, logged and sent to nobody.
Not listed: no config of HomeTreeDesign.tla expects TLC to break this rule. None of its configs expects TLC to break a rule.
There are 272 ways to get here in the model. This is the shortest.

0. Start: No child yet: nothing for you
1. The root makes child a. Now: Child a working: nothing for you
2. Child a launches a crew. Now: Child a working, crew out: nothing for you
3. The root's check runs. Now: Child a working, crew out, quiet for its patience: nothing for you

In the design, step 3 (the root's check runs) takes you to: Child a working, crew out, quiet for its patience: the root nudged a once.

## 3. Child a working, pull request ready: the root merging child a's pull request

Rule broken: jbus is the only merger; child homes never merge their own pull requests.
Why: on home merges a child runs jmerge for its own pull request, and the root may too.
Not listed: no config of HomeTreeDesign.tla expects TLC to break this rule. None of its configs expects TLC to break a rule.
There are 240 ways to get here in the model. This is the shortest.

0. Start: No child yet: nothing for you
1. The root makes child a. Now: Child a working: nothing for you
2. Child a launches a crew. Now: Child a working, crew out: nothing for you
3. Child a's crew opens its pull request. Now: Child a working, pull request open: nothing for you
4. Child a's pull request is green and reviewed. Now: Child a working, pull request ready: nothing for you
5. The root reads main to merge child a's pull request. Now: Child a working, pull request ready: the root merging child a's pull request

In the design, step 5 (the root reads main to merge child a's pull request) takes you to: Child a working, pull request ready: jbus merging child a's pull request.
