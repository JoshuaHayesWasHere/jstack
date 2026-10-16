Next is "End", step 1: check the checkout against the note taken at the start, before telling anyone anything.

I run this in one call, with the block at the top of the file (R, H, T) and `S` set to the slug, and show what it prints:
`echo "There at the start:"; git status --porcelain | grep -Fxf "$H/scouts/$S.start"; echo "New since the start:"; git status --porcelain | grep -Fxvf "$H/scouts/$S.start"`

If anything is listed, I name each line and whose it is, and correct the report's `Repo:` line to match. Then I go on to End step 2: confirming the report and the brief are on disk, with no page to check.
