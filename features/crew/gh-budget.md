- GitHub's API allowance is one for jbus, `jmerge` and every thread, and a loop of `gh` calls can spend it for all of them, merges included.
  Before a loop of more than ten `gh` calls, such as a fetch for each job, run or pull request, run `uv run --project "$T/../source" jbus budget --calls <n>` with the calls it will make: it reads `gh api rate_limit`, which spends nothing.
  While it says `held` and ends 75, make none of those calls, since the allowance is at the floor jbus keeps for merges: fetch less, or stop and say so in the Result.
