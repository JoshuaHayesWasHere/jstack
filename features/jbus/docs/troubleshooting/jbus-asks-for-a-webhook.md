# `jbus` asks for `webhook_url` and `webhook_key`

A project with no `webhook_url` or no `webhook_key` is one of the things that wait on you. Each hour `jbus` raises this line on the desktop and prints it in the journal:

```
waiting-on-user <project>: set webhook_url and webhook_key for <project> in its [[project]] table, or at the top of ~/.config/jbus/config.toml for every project · unblocks events to the Chef · since <HH:MM zone>
```

`jbus` still merges, launches and settles. It sends no event anywhere. To end the line, make a Chef as [The Chef](../chef.md) says and put its URL and a key in the config: at the top for every project, or in the project's table for it alone.
