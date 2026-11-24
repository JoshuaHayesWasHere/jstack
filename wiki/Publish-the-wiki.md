Use this guide to publish the pages in `wiki/` to the GitHub wiki.

The pages live in the repository so that changes to them go through the same commits as the skills. The GitHub wiki is a copy.

1. Before the first publish only, open the repository's **Wiki** tab on GitHub and save any first page. GitHub creates the wiki's git repository at that point. The script replaces that page.
2. Commit your page changes in jstack.
3. Run the script:

	```sh
	~/repos/jstack/scripts/publish-wiki
	```

	The script clones the wiki, replaces its pages with the contents of `wiki/`, and pushes. If nothing changed, it prints `wiki is up to date`.

## Page rules

- The file name is the page title, with hyphens for spaces. `Ship-a-change.md` is the page "Ship a change".
- Link to another page with `[[Page title]]`, or `[[link text|Page title]]`.
- `_Sidebar.md` and `_Footer.md` appear on every page.
- Write pages to the [`technical-writing`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/technical-writing/SKILL.md) skill. Each page has one job: a tutorial, a how-to guide, reference, or explanation.
