## 1. Between passes: a run is out, a start stamp under a minute old; a run's lines are lost

Rule broken: Every run's lines are judged once: a run that wrote its record has its lines sent, or the record is still on disk for the next pass, or the pass holds it on its way to `_judged`.
Why: the pass marked a record read and died before it sent its lines, so what jmerge said of those pull requests never reaches anyone.
There are 14 ways to get here in the model. This is the shortest.

0. Start: Between passes: no run out; no record yet
1. The pass writes the start stamp. Now: Between passes: no run out, a start stamp under a minute old; no record yet
2. The pass starts a run of jmerge in the background. Now: Between passes: a run is out, a start stamp under a minute old; no record yet
3. The run writes its record. Now: Between passes: a run is out, a start stamp under a minute old; a record waits for the next pass
4. The pass takes the oldest unread record. Now: A pass holds a record it has not sent: a run is out, a start stamp under a minute old; its lines not yet sent
5. The pass dies. Now: Between passes: a run is out, a start stamp under a minute old; a run's lines are lost

## 2. Between passes: no run out; a run died and nobody is told

Rule broken: A run that died before it wrote its record is told, or its stamp still stands to be told.
Why: a run died before it wrote its record, and its stamp went before any pass said so.
There are 21 ways to get here in the model. This is the shortest.

0. Start: Between passes: no run out; no record yet
1. The pass writes the start stamp. Now: Between passes: no run out, a start stamp under a minute old; no record yet
2. The pass starts a run of jmerge in the background. Now: Between passes: a run is out, a start stamp under a minute old; no record yet
3. The run's process dies. Now: Between passes: no run out, a start stamp under a minute old; no record yet
4. A minute goes by. Now: Between passes: no run out, a start stamp past a minute; no record yet
5. A pass looks at the runs folder. Now: A pass removed a stale stamp and has not said why: no run out; no record yet
6. The pass dies. Now: Between passes: no run out; a run died and nobody is told

## 3. Between passes: a run is out; the pass said a run left no record, though it did, a record waits for the next pass

Rule broken: The pass says a run ended with no record only of a run that wrote none.
Why: the pass says a run ended with no record while that run wrote one, or is still starting.
There are 12 ways to get here in the model. This is the shortest.

0. Start: Between passes: no run out; no record yet
1. The pass writes the start stamp. Now: Between passes: no run out, a start stamp under a minute old; no record yet
2. The pass starts a run of jmerge in the background. Now: Between passes: a run is out, a start stamp under a minute old; no record yet
3. A minute goes by. Now: Between passes: a run is out, a start stamp past a minute; no record yet
4. A pass looks at the runs folder. Now: A pass removed a stale stamp and has not said why: a run is out; no record yet
5. The pass says the last run ended with no record. Now: Between passes: a run is out; a run was said to have left no record
6. The run writes its record. Now: Between passes: a run is out; the pass said a run left no record, though it did, a record waits for the next pass
