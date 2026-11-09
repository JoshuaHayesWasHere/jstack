# The Go adapter's commands for the Makefile's targets, over each Go module of the repo, with no
# go.work. scripts/go.py runs gofmt, go vet and go test module by module, and selects in python3
# alone, so CI's plan selects before any setup.
STACK_LINT = python3 scripts/go.py lint
STACK_TEST = python3 scripts/go.py test
STACK_SELECT = python3 scripts/go.py select
