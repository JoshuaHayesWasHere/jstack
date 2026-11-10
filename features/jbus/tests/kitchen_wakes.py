"""What one project's home thread took from the kitchen's T3 Code, as the wakes jbus sends it.

pytest does not collect it: the name has no `test_` prefix, and `test_jbus_kitchen.py` imports it.
"""


class Wakes:
    """`Wakes` is what one project's home thread took from the one list (`jbus.wakes`): `listed`
    holds the lines of each message, a send whose retry key is `wakes|<project>|...`. While
    `refused` holds a reason, T3 Code refuses the project's wakes with it."""

    def __init__(self):
        self.refused = ""
        self.listed = []

    def listing(self, message):
        lines = message.split("\n\n")[1].splitlines()
        self.listed.append([line.removeprefix("- ") for line in lines])

    @property
    def said(self):
        """Each line the home was told, in order, across its messages."""
        return [line for lines in self.listed for line in lines]
