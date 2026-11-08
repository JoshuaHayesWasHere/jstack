# A repo on the repo standard

This repo holds to the repo standard of jstack, at the version `.repo-standard.yml` pins.
Each feature lives in its own folder under `features/`, with a `feature.json` that names it.

## Check a change

`make check` runs the lint and every test.
`make check-fast BASE=origin/main` runs the lint and the tests the change from `origin/main` reaches.
`make select BASE=origin/main` prints those tests, or `all`.

## Features

<!-- generated: features -->
<!-- generated: end -->
