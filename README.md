# Game Arts Skills

[![Game Arts tests](https://github.com/fahadTheTechIdea/GameArtsSkills/actions/workflows/atlas-tests.yml/badge.svg)](https://github.com/fahadTheTechIdea/GameArtsSkills/actions/workflows/atlas-tests.yml)

**Engine-agnostic, AI-assisted 2D game-art production for Claude Code and OpenAI Codex.** Import this repository into a game project's folder; from then on you ask for art in plain words and the agent follows one standard: storyboard and mockups first, explicit approval, detailed breakdown, reference-conditioned master art, deterministic sheets, atlases and bundles, human review of cutouts, and a managed generated / approved / revoked history.

It makes art and metadata. It contains no game-engine code: engine import, runtime and engine tests belong to the game project (the master standard's *Engine-neutral integration contract* says exactly what the files mean).

## Just talk to Claude or Codex
No special commands. Open the game project and ask:

| What you say | What Game Arts does |
|---|---|
| "Set up my game art." | A short in-chat settings wizard (kind of game, look, viewpoint, directions, image generator, engine); saves choices in the game. |
| "Create a storyboard for my game." | Drafts the key scenes from your prompt (or imports yours) and waits for your approval of the sequence. |
| "Create a city scene mockup." | Renders a real preview and asks for approval. |
| "Here is a mockup I made." / "…it's already approved." | Imports a managed copy; nothing is recreated. |
| "Approve this mockup." | Locks the reference, then analyzes every visible detail. |
| "Generate sprites from the approved mockup." | One master, then components, sheets and measured atlases, all traceable to that mockup. |
| "Approve this sprite." / "Reject this version." | Promotes or revokes the whole package; revoked art is never reused. |
| "Show approved art." | Reads the manifests. |

All everyday phrases: [docs/COMMANDS.md](docs/COMMANDS.md). The flow: [docs/USER_WORKFLOW.md](docs/USER_WORKFLOW.md).

## What it guarantees
- **Mockup-first.** New art starts from a mockup the user explicitly approved; the approved image's real pixels (a reference crop) condition production prompts.
- **Exact key colour.** Every delivered PNG is fully opaque with exact `#FF00FF` in unused pixels; near-key fringe is rejected. Terrain and full-panel UI may fill the canvas.
- **Measured, not guessed.** Sheets and atlases are built by scripts from real frames; one atlas per sheet; component bundles carry sampled composed transforms.
- **Clean parents.** Every movable, removable, interactive, replaceable or animated element is absent from the static parent and exported on its own, proven by a raster check and reviewed by a human.
- **Honest approvals.** Mechanical checks, visual acceptance and engine behavior are separate; approvals are exact-revision, hash-bound and rolled back on any failure.
- **Any style, any game, any engine.** Ten ready-made looks from 8-bit pixel art to flat vector, any world grid and camera (including hexagon tiles, scrolling layers and games with no ground world), and an engine setting per project; the outputs are plain files that any engine can use.
- **Individual files.** No ZIP-only delivery.

## Install
| Tool | Project instructions | Skills |
|---|---|---|
| Claude Code | [CLAUDE.md](CLAUDE.md) | [`.claude/skills/`](.claude/skills/) |
| Codex | [AGENTS.md](AGENTS.md) | [`.agents/skills/`](.agents/skills/) |

Copy the instruction file, the skill folders, `scripts/`, `schemas/`, `docs/` and the master standard into the game repository and follow [README_INSTALL.md](README_INSTALL.md). Requirements: Python 3, Pillow and `jsonschema`, plus an image-generation tool for the agent. An optional [updater](scripts/sync_local_agents.py) keeps both agents' installed copies current.

## Skills
| Skill | Purpose |
|---|---|
| [game-arts](.claude/skills/game-arts/SKILL.md) | Orchestrator: routes every request and states the gates |
| [game-arts-project-setup](.claude/skills/game-arts-project-setup/SKILL.md) | In-chat setup of a game's saved settings |
| [game-arts-custom-instructions](.claude/skills/game-arts-custom-instructions/SKILL.md) | Per-game saved art rules |
| [game-arts-storyboard](.claude/skills/game-arts-storyboard/SKILL.md) | Campaign storyboard before scene mockups |
| [game-arts-mockup-creator](.claude/skills/game-arts-mockup-creator/SKILL.md) | Real mockups, revisions, registration |
| [game-arts-lifecycle](.claude/skills/game-arts-lifecycle/SKILL.md) | Generated / approved / revoked mockups and assets |
| [mockup-analyzer](.claude/skills/mockup-analyzer/SKILL.md) | Blueprint, inventory, reference-crop regions |
| [art-profile](.claude/skills/art-profile/SKILL.md) | Style, camera and scale resolved into the prompt |
| [animation-planner](.claude/skills/animation-planner/SKILL.md) | Moving parts, directions, key poses |
| [sheet-atlas](.claude/skills/sheet-atlas/SKILL.md) | Sheets, atlases, component bundles |

The two skill folders hold the same text (a test enforces it); the master standard owns the policy and the skills only route to it.

## Reference
- [Master standard](GAME_ARTS_MASTER_STANDARD.md): the single canonical specification. A small pointer file under the old versioned name sits beside it only for updaters installed before the rename and is deleted once every enrolled game has updated.
- Guides: [settings](docs/PROJECT_SETTINGS.md), [genre recipes](docs/GENRE_RECIPES.md), [glossary](docs/GLOSSARY.md), [storyboard](docs/STORYBOARD.md), [atlas](docs/ATLAS_GENERATION.md), [component animation](docs/COMPONENT_ANIMATION.md), [lifecycle records](docs/ASSET_LIFECYCLE.md).
- Contracts: [`schemas/`](schemas/). Scripts: [`scripts/`](scripts/). Ready-made looks and engine profiles (validated data): [`presets/`](presets/).
- Improvement plan and tracker for this repository: [plans/enhancements](plans/enhancements/MASTER_TRACKER.md).

## Contributing
Update the master standard first, then the skills, schemas, scripts, docs and tests together, all in place; never add a numbered copy or a duplicate guidance file. Run only the tests for what you changed (`python -m unittest discover -s tests -p "test_<area>.py"`); CI runs the rest. Never claim a sprite, atlas or approval without the check that proves it.
