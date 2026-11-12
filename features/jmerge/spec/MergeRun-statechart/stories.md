## 1. Between passes: a run is out, a start stamp under a minute old; a run's lines are lost

Rule broken: Every run's lines are judged once: a run that wrote its record has its lines sent, or the record is still on disk for the next pass, or the pass holds it on its way to `_judged`.
Why: the pass marked a record read and died before it sent its lines, so what jmerge said of those pull requests never reaches anyone.
There are 6 ways to get here in the model. This is the shortest.

0. Start: Between passes: no run out; no record yet
1. The pass writes the start stamp. Now: Between passes: no run out, a start stamp under a minute old; no record yet
2. The pass starts a run of jmerge in the background. Now: Between passes: a run is out, a start stamp under a minute old; no record yet
3. The run writes its record. Now: Between passes: a run is out, a start stamp under a minute old; a record waits for the next pass
4. The pass takes the oldest unread record. Now: A pass holds a record it has not sent: a run is out, a start stamp under a minute old; its lines not yet sent
5. The pass dies. Now: Between passes: a run is out, a start stamp under a minute old; a run's lines are lost
