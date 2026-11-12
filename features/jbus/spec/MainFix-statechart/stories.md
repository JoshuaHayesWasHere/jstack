## 1. Main red, then green again, between passes: a revert open on GitHub, not on record

Rule broken: "An open revert on GitHub has its reverts.json record by the next pass": a revert GitHub had open when a pass started is kept once that pass has run to its end. jmerge merges, and reverts.close closes, only a revert reverts.json keeps, so one it does not keep stays open.
Why: main turned green before a pass recorded the revert, so none judges it again.
There are 164 ways to get here in the model. This is the shortest.

0. Start: Main green, between passes: no revert
1. A merge turns main's Mac red. Now: Main's Mac red, between passes: no revert; main's Mac: no fix brief
2. A pass starts. Now: Main's Mac red, jbus in a pass: no revert; main's Mac: no fix brief
3. Jbus opens the revert on GitHub. Now: Main's Mac red, jbus in a pass: a revert open on GitHub, not on record; main's Mac: no fix brief
4. The pass dies. Now: Main's Mac red, after a pass that died: a revert open on GitHub, not on record; main's Mac: no fix brief
5. A pull request merges, a fix row's or one you merge, and main's Mac turns green. Now: Main red, then green again, after a pass that died: a revert open on GitHub, not on record
6. A pass starts. Now: Main red, then green again, jbus in a pass: a revert open on GitHub, not on record
7. Jbus finds main green. Now: Main red, then green again, between passes: a revert open on GitHub, not on record

## 2. Main's Mac red, between passes: a revert open on GitHub, not on record; main's Mac: a fix brief with no row

Rule broken: "After any crash a red tip has a fix row and its brief, or neither, by the next pass": main's red tip and its Mac's each, and each red run of a nightly, also one that aged past NIGHTLY_WINDOW. A brief with no row is a fix no crew is launched for. A pass that runs to its end queues each brief it writes, so this holds at the end of every such pass, the next one after a crash among them.
Why: the pass died after the fix brief, and the next pass reverted in place of filing.
There are 260 ways to get here in the model. This is the shortest.

0. Start: Main green, between passes: no revert
1. A merge turns main's Mac red. Now: Main's Mac red, between passes: no revert; main's Mac: no fix brief
2. A pass starts. Now: Main's Mac red, jbus in a pass: no revert; main's Mac: no fix brief
3. Jbus writes the fix brief. Now: Main's Mac red, jbus in a pass: no revert; main's Mac: a fix brief with no row
4. The pass dies. Now: Main's Mac red, after a pass that died: no revert; main's Mac: a fix brief with no row
5. A pass starts. Now: Main's Mac red, jbus in a pass: no revert; main's Mac: a fix brief with no row
6. Jbus opens the revert on GitHub. Now: Main's Mac red, jbus in a pass: a revert open on GitHub, not on record; main's Mac: a fix brief with no row
7. Jbus finds main green. Now: Main's Mac red, between passes: a revert open on GitHub, not on record; main's Mac: a fix brief with no row

## 3. Main red, between passes: a revert open on GitHub, not on record; main: its fix row queued

Rule broken: "An open revert on GitHub has its reverts.json record by the next pass": a revert GitHub had open when a pass started is kept once that pass has run to its end. jmerge merges, and reverts.close closes, only a revert reverts.json keeps, so one it does not keep stays open.
Why: GitHub did not answer, and the pass filed a row in place of recording the revert.
There are 132 ways to get here in the model. This is the shortest.

0. Start: Main green, between passes: no revert
1. A merge turns main red. Now: Main red, between passes: no revert; main: no fix brief
2. A pass starts. Now: Main red, jbus in a pass: no revert; main: no fix brief
3. Jbus opens the revert on GitHub. Now: Main red, jbus in a pass: a revert open on GitHub, not on record; main: no fix brief
4. The pass dies. Now: Main red, after a pass that died: a revert open on GitHub, not on record; main: no fix brief
5. A pass starts. Now: Main red, jbus in a pass: a revert open on GitHub, not on record; main: no fix brief
6. Jbus writes the fix brief. Now: Main red, jbus in a pass: a revert open on GitHub, not on record; main: a fix brief with no row
7. Jbus queues the fix row. Now: Main red, between passes: a revert open on GitHub, not on record; main: its fix row queued

## 4. Main's Mac red, between passes: a revert on record, never said; main's Mac: no fix brief

Rule broken: jbus says each revert it opened: a revert reverts.json keeps has its line in events.jsonl.
Why: the pass died after it recorded the revert, and no later pass says it.
There are 364 ways to get here in the model. This is the shortest.

0. Start: Main green, between passes: no revert
1. A merge turns main's Mac red. Now: Main's Mac red, between passes: no revert; main's Mac: no fix brief
2. A pass starts. Now: Main's Mac red, jbus in a pass: no revert; main's Mac: no fix brief
3. Jbus opens the revert on GitHub. Now: Main's Mac red, jbus in a pass: a revert open on GitHub, not on record; main's Mac: no fix brief
4. Jbus writes the revert's brief. Now: Main's Mac red, jbus in a pass: a revert open on GitHub, its brief written, not on record; main's Mac: no fix brief
5. Jbus records the revert in reverts.json. Now: Main's Mac red, jbus in a pass: a revert on record, never said; main's Mac: no fix brief
6. The pass dies. Now: Main's Mac red, after a pass that died: a revert on record, never said; main's Mac: no fix brief
7. A pass starts. Now: Main's Mac red, jbus in a pass: a revert on record, never said; main's Mac: no fix brief
8. Jbus finds main green. Now: Main's Mac red, between passes: a revert on record, never said; main's Mac: no fix brief
