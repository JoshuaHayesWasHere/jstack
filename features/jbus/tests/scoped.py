"""A scope of a home's state, made as the root home's block makes one: a directory with its
`plan.md`, which makes it a scope (`jbriefs.home.scopes`), and a `home-id` once its home has
started."""


def scope(home, name, thread=""):
    """Make the scope `name` of `home`, with a `home-id` naming `thread` where one is given."""
    (home / name).mkdir()
    (home / name / "plan.md").write_text(f"# demo, {name}: plan\n")
    if thread:
        (home / name / "home-id").write_text(f"{thread}\n")
