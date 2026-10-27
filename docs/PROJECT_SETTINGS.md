# Game Arts project settings

Your game's visual preferences, set up inside Claude Code or Codex. No programming or command line is needed.

## Start, review, change
Say **"Set up Game Arts for this game."** The agent shows you each question with its choices, one at a time: what kind of world the game has, which look you want (a ready-made style to start from, see the [genre recipes](GENRE_RECIPES.md)), the viewpoint, the tile size or scale, the screen, facing directions, movement, the image generator, the engine or tool that will use the art, and a palette. **You choose every one: nothing is filled in with a default.** The agent may tell you which choice it recommends, but your pick is what is saved, and your own words for each pick are kept beside it. Before you confirm, the agent shows you what was written in plain words, what each pick means for the work, and a short version code; your confirmation is tied to exactly that version. Later: **"Show my Game Arts settings."**, **"Change my game's art style."**, **"Update the camera/viewpoint."** The agent reads the saved settings first and never asks what is already saved.

## Where it is saved
`<game-repository>/.gamearts/project.json` — in **your game**, never in this framework repository. Commit it so every session and teammate uses the same choices. The contract is [`schemas/gamearts-project.schema.json`](../schemas/gamearts-project.schema.json); the agent validates against it.

## Owner confirmation
After you confirm, the agent records who and when:
```json
{ "settings_status": "owner_confirmed", "confirmed_at": "2026-10-23T12:00:00Z", "confirmed_by": "owner" }
```
A mockup can only be registered or approved while the settings are `owner_confirmed` (and `confirmed_at`, `confirmed_by` are present). A text concept can be discussed earlier. If the style, camera, scale, directions, animation, world kind, screen or export settings change materially, the status becomes `needs_review` until you confirm again; already approved art is flagged for your review, never silently revoked. Re-formatting the file or editing other fields changes nothing. If you say you will confirm later ("I confirm once you show them back"), the agent shows your settings, saves them as `inferred` if it must, and waits; nothing can be registered or approved until you confirm. A storyboard does not need confirmed settings.

## Fields
```json
{
  "schema_version": "1.0",
  "project_id": "my-game",
  "world_kind": "grid_world",
  "settings_status": "owner_confirmed", "confirmed_at": "...", "confirmed_by": "owner",
  "art_style": { "id": "illustrated", "preset": "cel_shaded", "reference": "...", "outline_policy": "...",
                 "shading_policy": "...", "texture_policy": "...", "pixel_density": "...", "ui_camera": "..." },
  "world": { "grid": "orthogonal_square", "camera_profile": "orthogonal_3_4_oblique",
             "object_camera": "elevated 3/4 top-down oblique, orthographic", "ground_camera": "...",
             "logical_tile_m": [16, 16], "ground_tile_px": [256, 256], "pixels_per_meter": 16, "construction_snap_m": 1 },
  "directions": "dirs_8",
  "animation": { "preferred_method": "hybrid", "animated_attachment_anchors": true },
  "workflow": { "mockup_approval_required": true, "detail_decomposition_required": true },
  "export": { "background_hex": "#FF00FF", "background_alpha": 255, "atlas_per_sheet": true, "no_zip": true },
  "image_generation": { "tool": "built_in_image_gen", "notes": "optional: a model or quality preference" },
  "engine_target": { "profile": "generic", "version_note": "optional: the engine version you use" }
}
```
- `art_style.id`: `pixel_art`, `hand_painted`, `illustrated`, `vector`, `rendered_2d` or `custom`. The optional policy fields shape the prompts.
- `world.grid`: `orthogonal_square`, `isometric`, `hex_pointy`, `hex_flat` or `custom`; `world.camera_profile`: `orthogonal_3_4_oblique`, `isometric_3_4`, `top_down`, `side` or `custom`. `object_camera` and `ground_camera` are the exact plain-language views inserted into every image prompt; `art_style.ui_camera` is the UI view.
- Presets: orthogonal square + 3/4 oblique is 16 m cells, 256 x 256 px tiles, 16 px/m, 1 m snap; isometric 2:1 uses 256 x 128 px diamond tiles at 16 px/m across the diamond width. When you state your own tile size (64 x 32, say) it is used instead: one tile is 1 m and your stated angle is written into the camera text. The framework supports every preset; a project selects one. Never edit the framework to store one game's camera.
- Top-down and side games have no fixed cell size: from your tile size in pixels the agent proposes one tile = 1 m (32 px tiles: 32 px/m, 1 m snap) and shows it back before you confirm. "Top-down" can mean straight down (`top_down`: roofs and floors) or from above and a little in front (`orthogonal_3_4_oblique`: the fronts of walls and objects show); the agent asks which.
- `world_kind` says what the game's world is: `grid_world` (a tile map; the default when the field is absent), `free_world` (open space without tiles), `layered_scene` (scrolling layers, listed in `world.layers` with a `scroll_scale` each) or `screen_space` (no ground at all: cards, match-3, visual novels, menus). A `screen_space` game states its screen (`screen.base_resolution_px`) and needs no `world` or `directions`; it can only make screen-space art.
- `directions` is the default set for free-facing mobile assets: a list, or a name: `dirs_8`, `dirs_4`, `dirs_2_side` (left and right), `dirs_1_side` (one side, mirrored by the game where the art allows) or `dirs_1_front`. Mobile assets need exactly that set unless a limited profile is approved. Static structures, terrain and UI are classified per asset and ignore it.
- `art_style.preset` records the ready-made look the game started from (list them with "show me the looks"). Setup copies the look's values into your settings, so changing or updating a look later never alters your game; its "avoid" list goes into every image prompt and its checks are the ones your art is measured with.
- `engine_target.profile` names the engine or tool that will use the art, from the profiles that come with Game Arts (`generic` when you name none). It selects the import advice you are shown and, later, which extra exports are made by default. It never changes your art or your approvals, and a game whose engine has no profile works exactly the same. A profile can also list `default_exports`: derived files made automatically when an asset is approved (the engine-ready copies, for an engine that cannot remove the magenta background itself). `generic` lists none.
- `art_style.palette_reference` is a palette stated in words or, once you have one, the path of a saved palette file (`.gamearts/palette/main.palette.json`, made from an approved picture). Only a saved file can be checked against; words cannot, and the checks then say so. Any other stated constraint goes in `prompting.additional_constraints`.
- `art_style.anchor` names your approved style board as `{ "mockup_id": "...", "revision": "v001" }`. When it is set, every reference crop for a new asset carries that board too, so art made on different days keeps one look. A game without one works as before.
- `image_generation.tool`: your choice of image generator, asked once and remembered. `built_in_image_gen` is the agent's own built-in image tool (Codex's `image_gen`), `cli_image_gen` is Codex's command-line fallback (needs an OpenAI API key), `connected_tool` is a connector or plugin tool you name in `tool_name`, and `user_supplied` means you make the pictures yourself and hand them in (the agent then never generates). The agent uses only the tool you chose, tells you when it is not available in the current session instead of using another, and records which tool made each mockup. It does not reopen approved art when you change it. Say **"Use the Codex image generator for this game"** or **"Change the image generator"** at any time.
- Optional `prompting`: `reference_lock`, `strict_camera_lock`, `single_master_first`, `additional_constraints`.
- `workflow` and `export` carry the fixed requirements (mockup approval, decomposition, exact opaque `#FF00FF`, a measured atlas per sheet, individual files); they are not options.

## Used in every image prompt
Every image or image-edit call reads these settings, the active instructions, the approved references and any asset profile, and writes the resolved style, camera, scale and export choices into the actual tool prompt. An approved master outranks a changed setting: a conflict is flagged, not silently resolved. Framework defaults only fill genuinely missing values.

## Custom instructions
Structured defaults live here. Free-form, scoped rules ("always use soft morning lighting", "UI icons stay simple") are saved one per file in `<game>/.gamearts/instructions/` through the `game-arts-custom-instructions` skill, read for every relevant task, and never allowed to weaken the master's mandatory requirements. A rule from a one-off request ("just this sprite") is not saved.

## Updater state is separate
The optional updater keeps its own state in `.gamearts/system/agent-sync-state.json` and never changes this file.
