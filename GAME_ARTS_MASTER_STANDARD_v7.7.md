# Moved

The Game Arts master standard is `GAME_ARTS_MASTER_STANDARD.md` in this folder. This file exists only so that updaters
installed before the rename, which look for it by name, keep working until every enrolled game has updated. It is then
deleted. Do not read policy from it.

If `GAME_ARTS_MASTER_STANDARD.md` is missing next to this file, the installed updater is out of date: run
`python scripts/sync_local_agents.py update --game-root .` (or start a new trusted session) to receive it.
