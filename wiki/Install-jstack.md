Use this guide to set up jstack on a machine, or to repair its links.

1. Clone the repository:

	```sh
	gh repo clone JoshuaHayesWasHere/jstack ~/repos/jstack
	```

2. Run the installer:

	```sh
	~/repos/jstack/install
	```

	On a machine without `~/repos/jstack/settings.json`, the installer copies `settings.example.json` to `settings.json`. It prints `copied settings.example.json to settings.json (edit it)`.

3. If the installer copied the template, edit `~/repos/jstack/settings.json`. Add a `Read(...)` deny rule for each private config folder on this machine.

4. Check the result:

	```sh
	~/repos/jstack/install --dry-run
	```

	No output means every link is in place.

5. Start a new agent session. Existing sessions load skills only at startup.

If the installer prints `conflict: <path> exists and is not a link`, a real file or folder sits where a link should go. Move it aside, then run the installer again.

For what the installer links and where, see [[Repository layout]].
