package hello

import "testing"

func TestGreetNamesWhomItGreets(t *testing.T) {
	if got := Greet("repo"); got != "hello, repo" {
		t.Fatalf("Greet(%q) = %q", "repo", got)
	}
}
