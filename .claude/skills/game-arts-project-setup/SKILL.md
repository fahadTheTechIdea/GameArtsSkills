---
name: game-arts-project-setup
description: Friendly in-chat Game Arts project setup - a wizard that asks every setting as a question with choices (world, look, viewpoint, scale, directions, animation, image generator, engine, palette), saves only what the owner picks, and confirms it. Use for setup, showing or changing settings, or when a game has no confirmed configuration and an art task needs it.
---

# Game Arts project setup (in chat)

Policy: master *Project settings and the owner-confirmation gate* (its **setup wizard** bullet), *Art-style profiles*, *World geometry, projection and scale*. Run inside the current Claude Code or Codex chat. The user needs no Python, terminal, JSON or git. Be brief and friendly. **Every setting is the owner's own pick: no setting is ever filled in with a default.** You may say which option you recommend and why; you never choose it for them. Never claim a setting is saved unless the command succeeded and you read it back.

## Start
1. Find the game project (not this framework repository) and read `<game>/.gamearts/project.json` if it exists. For a plain request use it as it stands; for a configuration request summarize it simply and ask what to change.
2. Run `python scripts/gamearts_setup.py status --game-root <game>`. A game with no wizard answers (new, or set up before the wizard existed) gets the whole wizard; the wizard marks each existing value as `(current setting)` and only the owner's pick counts. Do not stop brainstorming or early concept talk while setup is open.
3. If the user names another game folder of theirs, mention its choices as suggestions while you ask; the owner still picks each one.

## The wizard (the loop)
1. `python scripts/gamearts_setup.py next --game-root <game>` returns the next unanswered question: `question.prompt`, the numbered `options` (value, label, description) and a ready `text`. **Show it as given**: use your own choice control (a multiple-choice prompt) where you have one, otherwise print `text` and wait for the number or the words. Add "Something else" only where the options include it.
2. Record the pick: `python scripts/gamearts_setup.py answer --game-root <game> --id <question id> --value <option value> [--text "<owner's words>"]`. A pick that needs the owner's own words (another size as `WIDTHxHEIGHT`, a connected tool's name, a palette description or picture path, an engine's name, an angle for isometric) takes `--text`. A refused answer says why; ask again.
3. Repeat until `next` says `complete`. Answering an earlier question again resets only the later questions that depend on it. `python scripts/gamearts_setup.py show --game-root <game>` lists every question, its options and what is answered, for a review or a change.
4. `python scripts/gamearts_setup.py finish --game-root <game>` writes `project.json` from the answers. It refuses while any question is open; nothing is written before that, so a half-answered game has no settings file.

The questions, in order: the game's name (it becomes the short name that starts every file), world kind, look, viewpoint, tile size or scale, background layers, screen size and scaling, facing directions, animation, image generator, engine, palette. Which ones apply depends on the world kind (a tile map asks for the viewpoint and tile size, a screen-only game for the screen). The look list comes from `presets/styles/` and the engine list from `presets/engines/`. A look with soft edges needs one more sentence from you, once (master *Masking and PNG export policy*): say it and save the owner's answer in `prompting.additional_constraints`. A "top-down" answer is the viewpoint question: the choice between seen from above and a little in front, and straight down, is shown as two options. The isometric tile size and the owner's own angle follow the master's *World geometry, projection and scale*.

Ask only what the wizard asks as a setting. Ask about frame counts, layer names and the like only when an art task needs them, not as settings. Policy constants (the mockup gate, the key colour, one atlas per sheet) are not wizard choices.

## Confirm and save
1. After `finish`, give the owner a plain summary of what they picked ("Pixel art, 16-bit look, seen from above and a little in front, 32 px tiles, four directions, automatic animation, you supply the pictures, the engine you named") and ask for a short confirmation. If they defer, wait; the settings stay `inferred`. A scripted or simulated acceptance is not an owner confirmation.
2. On the owner's confirmation run `python scripts/gamearts_asset_lifecycle.py confirm-settings --game-root <game> --by <owner or role> --user-confirmation-ref "<their words>"`. It stamps the real time, refuses settings the wizard did not write or that miss an answer, and never takes a typed `confirmed_at`. After a later material change (`art_style`, `world`, `world_kind`, `screen`, `directions`, `animation`, `export`) `finish` sets `needs_review` until the owner reconfirms; existing approved art is flagged for review, never silently revoked. `image_generation` and `engine_target` are not material: an unchanged confirmation stands.
3. Verify: `python scripts/gamearts_asset_lifecycle.py check-settings --game-root <game>` must report valid, owner-confirmed and `setup.complete: true`. It also names the engine profile and the import notes for the chosen look; pass the notes on to the user once. Tell the user in simple terms what was saved and where. If a command failed, say nothing was saved.
4. Mention once that "Add a Game Arts instruction" customizes the pipeline for this game (`game-arts-custom-instructions`).

## Rules
Do the work, not syntax lessons. Never show raw JSON unless asked. Do not re-ask what the saved answers already say unless the owner wants a change. Explain a word from `docs/GLOSSARY.md` in one clause the first time you use it. If your agent has no image tool of its own, do not recommend one: say so when the image generator question comes up and offer "I make the pictures myself" and any connected tool you can see, never picking a paid one for the owner. The mandatory standards (mockup-first approval, exact opaque `#FF00FF`, a measured atlas per sheet, locked masters, honest validation, no ZIP-only delivery) are not choices.
