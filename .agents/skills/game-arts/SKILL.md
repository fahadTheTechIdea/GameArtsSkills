---
name: game-arts
description: Use for any request to create, edit, review, animate, export or validate game artwork - storyboards, mockups, sprites, sprite sheets, scenes, world art, characters, UI, tilesets, effects, attachments, atlases or component bundles.
---

# Game Arts orchestrator

The master standard is `GAME_ARTS_MASTER_STANDARD.md` at the repository root. It is authoritative; this skill only routes to it. Cite its headings (written *like this*), never copy its text. Do not fill gaps by guessing. Never claim image generation, a validation run, an import or an approval that did not happen.

## Quietly, at the start of every art task
1. Find the **game** project (not this framework repository). Read `<game>/.gamearts/project.json` and the active `<game>/.gamearts/instructions/*.md`; apply saved choices without asking again. See *Project settings and the owner-confirmation gate* and *Automatic, invisible project experience*.
2. Settings need setup or change: `game-arts-project-setup`. A lasting rule: `game-arts-custom-instructions`. Missing optional settings never block a first mockup, but generating, registering or approving a mockup needs owner-confirmed settings.
3. Classify the request and route it. Do not require special phrases, scripts, folder handling or JSON editing from the user; run every script internally and report plainly.
4. Before the first picture of a request, show the plan card: `python scripts/gamearts_plan_card.py --game-root <game> --asset-class <class> [--actions N --frames-per-action N] [--detachable-parts N [--rig-by-transform]] [--pictures N] [--mockup-approved]`; `--rig-by-transform` for a cut-out rig that moves by transforms, so its frames are not counted as pictures (master *Precedence and canonical production workflow*). Read its `message` to the person: the lane, how many pictures, which approvals they will be asked for, and the credits sentence. Never state a price the card did not.
5. A script that stops on a missing package, interpreter or unwritable folder: run `python scripts/gamearts_doctor.py --game-root <game>` and pass on its fix in plain words (*Automatic, invisible project experience*). It only looks; install nothing without the user's go-ahead.
6. End every stage with what exists, what you need from the user and what comes next; a changing operation's `next_step` is the last of those. Answer in the user's language and explain a word from `docs/GLOSSARY.md` the first time you use it.

## Route
| Request | Use |
|---|---|
| A campaign, story, levels or several scenes in one request (not a single scene or asset; the request decides, not the project) | `game-arts-storyboard` first; scene mockups only for the approved sequence |
| New visual with no approved reference (world, scene, asset, character, UI) | `game-arts-mockup-creator` |
| A mockup made outside Game Arts | `game-arts-lifecycle`; see *External and user-supplied mockups* |
| An approved mockup to break down | `mockup-analyzer` (blueprint, inventory, reference crop region) |
| Style, camera, scale, direction policy, prompt style lock | `art-profile` |
| Parts that move, cycle, change state, directions, key poses | `animation-planner` |
| Sheets, atlases, bundles, exact key colour | `sheet-atlas` |
| Register, approve, reject, restore, list, select, audit | `game-arts-lifecycle` |
| Show my art, its status, "what is next", "what can I do now" | Open or rebuild the report (`python scripts/gamearts_report.py --game-root <game>`; every changing operation already rebuilds it and names its path) and answer from it and from `check-settings` |
| Which kind of game, which look, which engine | `game-arts-project-setup`; ready-made choices are `docs/GENRE_RECIPES.md` and `presets/` |
| "I already have a sprite sheet / art / a palette" | `game-arts-lifecycle` (`import-asset`); ask how the sheet is laid out (grid, cell size or an Aseprite data file) and whether it is theirs, and use their words as the approval reference |
| Compare looks, "show me some styles", pick one | `game-arts-mockup-creator` (its section on exploring a look) |
| A team colour, season, night or other recolour of approved art | `sheet-atlas` (its section on palette variants; `gamearts_palette.py recolour`) |
| Show how it moves; art came back too large or blurry; does it match the palette | `animation-planner`, `sheet-atlas` |
| A tileset, buttons with states, a stretching panel, named animations, a tighter sheet, files for Aseprite or Tiled, engine-ready files | `sheet-atlas` (and `game-arts-lifecycle` for `export-runtime`) |

## Gates that are never skipped (each is a heading in the master)
- *Mandatory mockup-first approval gate*: no production art for new work before an explicitly approved mockup revision; an already approved, unchanged reference is reused, not re-approved.
- *Reference-controlled image prompting* and *Reference crop and conditioning gate*: every image-tool call carries the resolved settings and the real approved crop as image input; one master first, then components, then key poses, then deterministic assembly. If the tool cannot take reference images, stop and say so. When `image_generation` is `user_supplied`, the same packet is the request to the owner (master *Project settings and the owner-confirmation gate*). Never ask a model to draw a sprite sheet or atlas.
- *Masking and PNG export policy*: every delivered PNG is fully opaque with exact `#FF00FF` in unused pixels; no near-key fringe.
- *Sprite sheets, atlases and component bundles*: build them with the scripts, one measured atlas per sheet.
- *Parent-artwork cleanup and separation gate*: every independently movable, removable, interactive, replaceable or animated element is absent from the static parent and exported separately.
- *Human-verifiable silhouette and reconstructed-background review*: for composite assets, show the review boards and obtain the user's real approval; never invent it.
- *Asset and mockup lifecycle*: exact ID and revision through the manifests; revoked or rejected art is never a source; every file move is done by the lifecycle script.
- *Quality gates and validation grades* and *Engine-neutral integration contract*: mechanical checks, visual acceptance and engine behavior are separate. Engine import and tests belong to the game project; this framework has no engine code.
- *Delivery*: individual files, never a ZIP alone.

## Scripts (in the game's `scripts/` folder; run internally, e.g. `python scripts/<name>.py ... --game-root .`)
`gamearts_asset_lifecycle.py`, `gamearts_storyboard.py`, `gamearts_report.py`, `gamearts_doctor.py`, `gamearts_disclosure.py`, `gamearts_plan_card.py`, `gamearts_presets.py`, `gamearts_palette.py`, `build_contact_sheet.py`, `prepare_reference_crop.py`, `build_sheet_atlas.py`, `validate_sheet_atlas.py`, `build_component_bundle.py`, `validate_component_bundle.py`, `validate_parent_cleanup.py`, `visual_review_cleanup.py`, `validate_style_conformance.py`, `validate_settings_fit.py`, `snap_to_pixel_grid.py`, `check_animation.py`, `render_preview.py`, `build_tileset.py`, `validate_tileset.py`, `detect_scene_objects.py` (optional extra), `extract_scene_objects.py`, `remove_scene_objects.py` (optional extra), `evaluate_extraction.py`, `export_exchange.py`, `export_runtime.py`, `validate_blueprint.py`, `sync_local_agents.py`. They need Python 3, Pillow and `jsonschema`; if one is missing install it with permitted tools or report the blocker. A script that cannot run means that check did not run, never that it passed.

Everyday user commands are listed in `docs/COMMANDS.md`; the full decision table is `docs/USER_WORKFLOW.md`.
