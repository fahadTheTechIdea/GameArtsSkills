---
name: game-arts-project-setup
description: Configure or update persistent Game Arts per-game settings with a wizard, or inspect and validate existing .gamearts/project.json settings. Use when the user requests setup, configuration, preferences or project initialization.
---

# Game Arts project setup

1. Read the canonical master specification `GAME_ARTS_MASTER_STANDARD_v7.2.md`.
2. Determine the **target game repository** (not the shared GameArtsSkills skills repository).
3. Check for `<game-root>/.gamearts/project.json`.
4. If it exists, read it and honor saved settings; never silently replace values. Use `python scripts/setup_gamearts.py --project-dir <game-root> --show` and `--validate`.
5. If absent or user requests reconfiguration, run `python scripts/setup_gamearts.py --project-dir <game-root>` (add `--overwrite` only for an explicit requested update).
6. Guide the user through style, camera, terrain and scale, directions, animation preference, and mockup scope questions.
7. Validate the saved file. Show the final selected settings, not just a success message.
8. Recommend checking the file into the target game repository so it persists across Claude/Codex sessions and teammates.
9. Settings are **project defaults**. The approved mockup and more specific asset profiles may refine artistic decisions. Never override universal invariants: mockup approval, detailed decomposition, exact opaque `#FF00FF` source PNG masking, a measured atlas per sprite sheet, applicable dynamic attachment/directional requirements, Godot validation and no ZIP.
10. Missing or unknown settings must be reported and resolved through the wizard or documented assumptions; do not invent a user's approval.

No game profile is stored in ChatGPT memory as a substitute for the file. The repository version is the authoritative project configuration.
