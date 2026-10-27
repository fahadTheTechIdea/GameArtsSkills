# Game Arts style coverage and usability plan

Status: **planned, 2026-10-24; revised the same day after two owner instructions: "we are mainly using godot" and "make framework work for all, depends on developers and projects setting he picks".**
Nothing in this plan is implemented. The revision makes the **engine a per-project setting** (like the image generator): Godot is the first fully documented profile because the owner uses it,
a `generic` profile is the default, and nothing in the framework becomes Godot-only (§0 "Engines", D-16 to D-19). Written as plan only, after reviewing the framework (method and limits in §1) and
researching comparable systems (§3.3, sources in §11). Tracker: [MASTER_TRACKER.md](MASTER_TRACKER.md) (phases P9 to P14, decisions D-8 to D-15).
This is the second workstream of the repository's improvement work. The first, [ENHANCEMENT_FIX_PLAN.md](ENHANCEMENT_FIX_PLAN.md), hardened the gates and is implemented
and locally verified; this plan builds on it and does not reopen it.

Claim classes follow the SDLC evidence policy: **[O]** observed (file read or command run, with a locator), **[I]** inferred from named observations,
**[P]** proposed, **[U]** unknown. Severity: **S1** blocks a whole kind of game or user, **S2** materially weakens the result, **S3** polish.

## 0. Goal and what "better" can honestly mean

Goal: make Game Arts better at producing art for **different 2D game styles and genres**, and **friendlier** to use.

No framework can make an image model draw better, and nothing here measures artistic quality (master §2 and §26 already say so). What the framework can improve,
and what this plan targets:

1. **Specification**: a game states its look and genre by choosing, not by writing policy prose (style presets, genre recipes, world kinds).
2. **Consistency**: one approved style reference that every later image is conditioned on and checked against (style anchor, palette, pixel-grid and animation checks).
3. **Coverage**: asset kinds that real 2D games need and the framework cannot yet describe or validate (tilesets, 9-slice UI, tags, soft edges, effects).
4. **Visibility and effort**: see the state of the art at a glance, use a lighter path for small jobs, know what happens next, recover from an unready environment.

**Engines.** Every developer and project picks its own engine and tools, so the framework adapts to the setting and assumes nothing:

- The outputs stay engine-neutral files (key-colour PNG sheets, measured atlases, bundles, and the new tileset, UI and tag metadata). That is what makes the framework usable with any engine.
- A new per-project setting, `engine_target` (an engine profile id, optional version note; `generic` when absent), selects a **profile**: validated data under `presets/engines/` that says, for that engine,
  which derived exports to write by default, what import settings to recommend for the saved art style, and how each framework concept maps to the engine's own (atlas frame, animation tag, nine-slice,
  UI state, blend mode, tile layout, parallax layer, easing). The profile is guidance and export selection. It is **not** engine code, and it never changes the art, the gates or any approval.
- **Godot is the first complete profile** (the owner's engine), written against the official 4.7 documentation and verified in a throwaway project outside the repository with the installed 4.7.2. `generic`
  ships with it. Further profiles (Unity, Phaser, GameMaker, Defold and others) are added one at a time, each only after its primary documentation has been read and cited; none is invented. A game that
  uses an engine with no profile works exactly as it does today.
- Where Godot already provides a capability (terrain matching, sprite animation, 9-patch, parallax, blend modes), the plan describes how the neutral data maps onto it and never re-implements it (the owner's
  standing rule for Godot projects); the importers that turn neutral data into Godot resources belong to the game project or a separate integration package, as D-2 and the hand-off document already say.

Targets, stated as measurable outcomes to be checked in P14 (they are targets, not results):

- T-1 From an empty game folder to confirmed settings for a preset-based game in **3 user messages or fewer**, with no world-geometry question for a game that has no world.
- T-2 Every one of 12 genre recipes (S-11) can be started without the agent inventing a number the user did not give or the framework did not derive and show back.
- T-3 A pixel-art asset that is off its pixel grid, outside the palette, or loops badly is **reported with the measured reason** before the user is asked to approve it.
- T-4 A small job (one icon, one prop, one tile) needs **at most two** user approvals; a composite job keeps every gate it has today.
- T-5 The user can open one file and see every mockup and asset, its status, its approval quote and what is next, without a terminal.
- T-6 Changing the saved engine target changes the integration guidance and the default exports and **nothing else**: no approved art is flagged, no hash of a material setting moves, and a game with no profile for its engine behaves as it does today.
- T-7 For the Godot profile, every mapping it states (tile layout to terrain mode, animation tag to loop mode, nine-slice to patch margins, easing to track interpolation, blend mode, parallax layer) has been exercised in a headless Godot 4.7.2 project and the result is recorded as observed, not assumed.

## 1. Method, coverage and limits

- **Read in full this session:** the master standard (all 27 sections), all 10 skills of the `.claude` tree (a guard test keeps `.agents` identical), 6 of the 7 docs
  (`ATLAS_GENERATION`, `COMMANDS`, `COMPONENT_ANIMATION`, `PROJECT_SETTINGS`, `STORYBOARD`, `USER_WORKFLOW`), `README.md`, `README_INSTALL.md`,
  `schemas/gamearts-project.schema.json`, `scripts/build_sheet_atlas.py`, the tracker and the header of the first plan.
- **Read in part:** `docs/ASSET_LIFECYCLE.md` (the mockup-metadata section), `scripts/prepare_reference_crop.py` (lines 120-165), `scripts/gamearts_asset_lifecycle.py`
  (mockup, approval and registration code), `scripts/sync_local_agents.py` (constants and the update path), `scripts/build_component_bundle.py` (interpolation only),
  `tests/test_docs_guard.py` (what it enforces).
- **Not re-read this session:** the other nine scripts, 15 other schemas and the tests line by line. Their behavior is taken from the first plan (read in full on 2026-10-23), from the
  tracker's verification record, and from the targeted searches below. Absence claims in §3 were each checked with a search of `scripts/` and `schemas/` and are labelled with it.
- **Live evidence from this session's runs** (tracker V-11 to V-17): ten fresh Claude agents and four Codex sessions followed the installed files and reported where the text or the
  tooling made them guess. Those reports are the main usability evidence. The "users" in them were scripted.
- **Research:** official documentation fetched on 2026-10-24 where a primary page exists, search summaries otherwise; each source is marked in §11. Vendor and third-party pages are claims
  about the vendors' products, not verified behavior.
- **Godot (added in the same-day revision):** five Godot 4.7 class pages were fetched on 2026-10-24 (G1 to G5) and the installed engine was identified with `--version` (4.7.2 stable, .NET build, headless console executable).
  No Godot code has been run yet; every mapping in §3.3 is documented, not yet observed (A14.5).
- **No code was changed, no test was run for this plan, no image was generated, no git command was used.** Hosted CI, the interactive hook trust review and a real-model run of any new
  check remain unrun (tracker).

## 2. What the framework does well today (keep all of it)

[O] The exact opaque `#FF00FF` key and near-key rejection; mockup-first approval with hash-bound exact revisions; locked masters and reference crops; deterministic sheets, atlases and
component bundles with sampled poses; the clean-parent rule with raster proof and human review boards; generated, approved and revoked lifecycles with rollback; the per-game image-generator
setting; a style-neutral core (master §5: pixel-art rules are never forced on other styles); honest grades (`not_tested`, `not_assessed`); one owner per fact with guards. Nothing below weakens
a gate. Where a change touches one (lanes, batch approval, soft edges) §4 and the acceptance criteria say exactly how it stays safe.

## 3. Findings

### 3.1 Style and genre coverage

| ID | Sev | Class | Finding | Locator / evidence |
| --- | --- | --- | --- | --- |
| S-1 | S1 | O | Every game must declare ground-world geometry. The project schema requires `world` and `directions`; `world` requires `grid`, `logical_tile_m`, `ground_tile_px`, `pixels_per_meter` and `construction_snap_m`; `animation.animated_attachment_anchors` must be `true`. A card, match-3, visual-novel, idle or other screen-space game cannot be described truthfully, and the fresh agents had to invent "1 tile = 1 m" even for a top-down game. | `schemas/gamearts-project.schema.json:5-13,87-93,171-174`; tracker V-17 |
| S-2 | S2 | O | Grid and camera presets are oblique, top-down, side, isometric 2:1 and `custom`. There is no hex grid, no layered or parallax scene, no screen-space profile, and `side` has no platformer conventions (ground line, slopes, one-way platforms). Anything else is `custom`, where the master says "never guess" and gives no template. | master §6 table |
| S-3 | S1 | O | Six `art_style.id` values with free-text policy fields. There are no concrete looks (pixel-density tiers, cel-shaded, painterly, ink line art, flat vector, cut-out, rendered-to-2D) and no per-look checks, so every game re-derives its policy in chat. Comparable tools ship presets or themes. | master §5; schema `art_style`; §3.3 |
| S-4 | S1 | O | There is no style anchor. `art_style.reference` is a string; the only visual lock is the individual mockup, so each new scene restarts the style. Cross-asset consistency is the known hard problem of generated art and the comparable tools attack it with trained style models or style references. | schema `art_style.reference`; master §8; §3.3 |
| S-5 | S1 | O | No palette or pixel-grid tooling. A search of `scripts/` finds `palette` only as a printed settings key. Pixel-art rules (master §5: deliberate clusters, curated palette, integer scaling) are unmeasured: no palette conformance, colour count, grid alignment or integer-scale check. Generators routinely return off-grid "mixels" and tool vendors ship fixers for exactly this. | `scripts/prepare_reference_crop.py:155`; §3.3 |
| S-6 | S1 | O | No tileset support. `tile` exists only as a direction label for the `terrain` class and as `full_bleed`; a search of `scripts/` for tileset, autotile, wang, tilemap, hex, parallax and 9-slice finds nothing relevant. There is no tile-size or seamless-edge check, no autotile layout contract, no transition inventory and no tileset metadata. Grid-world games depend on these [I]. | `scripts/prepare_reference_crop.py:133`; master §10, §13 |
| S-7 | S2 | O | UI art is "one view, full-bleed, native text" with no nine-slice borders, no state grouping (normal, hover, pressed, disabled), no icon-set consistency check and no scale variants in any schema (a search of `schemas/` finds none). | master §7, §10; `schemas/` search |
| S-8 | S2 | O | Sheets are one uniform grid whose cell fits the largest frame; frames carry `action` and `direction` but there are no animation tags (name, range, loop, ping-pong), no trim and no packing; the only output is the framework's own JSON. The ecosystem's tools export tags, trim, packing and de-facto array or hash JSON. | `scripts/build_sheet_atlas.py:75-81`; `schemas/` search; §3.3 |
| S-9 | S2 | O | Soft edges are second-class. An opaque key PNG cannot carry fractional alpha, so smoke, glow, glass, shadows and antialiased painted or vector edges either get a hard edge or live in "separate metadata" that no script produces or checks. OpenAI's current image guide documents `background: "transparent"` for named models [O]; whether the Codex built-in tool exposes it is **[U]**. | master §15 "Style-aware edges"; §3.3 |
| S-10 | S2 | O | Animation checks the standard names are not automated: loop closure, clipping and static-region drift (master §21, §26). No script renders a preview (a search finds no GIF, APNG, HTML or contact-sheet code), though the animation-planner skill speaks of "animation preview for visual QA". Frame-by-frame looks (pixel art) depend on exactly these checks. | master §21, §26; animation-planner skill; `scripts/` search |
| S-11 | S2 | O | No genre guidance. Nothing maps a game type to a camera, presets, asset classes, their order or the gates that matter, so a user making a platformer, a card game or a visual novel gets the generic pipeline and must know what to ask for. | docs/, skills (read in full) |
| S-12 | S3 | O | The asset-class table has four classes; others are named in passing (terrain, prop, effect, portrait) without a profile. Missing: tileset, parallax layer, portrait or expression set, card layer set, icon set, effect sprite. (Bitmap fonts are a style-specific need; backlog.) | master §7 |
| S-13 | S2 | O | Direction sets: free-facing mobile assets need all eight unless every job sets `rotation_policy: explicit_limited`. Four-direction top-down games and two-direction mirrored side-view games (very common) need a per-asset exception, not a project choice. | `scripts/prepare_reference_crop.py:130-139` |
| S-14 | S3 | O | Cut-out animation interpolates linearly only (rotation can opt into the shortest arc). There are no easing curves and no stepped or hold keys, which cut-out looks use for weight and for limited-animation timing. | `scripts/build_component_bundle.py:9-10,242`; `docs/COMPONENT_ANIMATION.md` |
| S-15 | S1 | O | The framework has no notion of the developer's engine. The integration contract is generic prose ("your engine"), the project settings have no engine field, and nothing adapts to what a project uses. The owner's games use Godot, and the removed addon's lessons (hand-written interpolation, forced nearest filtering, a per-frame loop, an unescaped scene injection) show what a generic hand-off leaves to each game. Other developers use other engines. | master §22; `plans/enhancements/ENGINE_HANDOFF.md` findings 1-10; schema (no engine field) |
| S-16 | S2 | O | Every delivered sheet needs game-side key removal that each game must write for itself: the master says "the game project removes the key at import or render time", and the removed runtime did it with a chroma-key shader that also forced nearest filtering. No derived, runtime-ready sheet exists, so even a straightforward import needs custom code that the engines' own import pipelines would make unnecessary. | master §22; ENGINE_HANDOFF finding 4 |

### 3.2 Usability

| ID | Sev | Class | Finding | Locator / evidence |
| --- | --- | --- | --- | --- |
| U-1 | S1 | O | No at-a-glance view of the art. Results are files under `.gamearts/outputs/` and manifests; "show approved art" is text. The only image boards are the cleanup review boards. The comparable products are visual galleries. | `docs/COMMANDS.md`; `scripts/visual_review_cleanup.py`; §3.3 |
| U-2 | S1 | O | The process weight is the same for a coin icon and a composite workshop: mockup approval for "anything new", twelve gates, up to five kinds of approval (storyboard sequence, mockup, master, review boards, final art), no batch approval (24 icons are 24 approvals). | master §3, §8 |
| U-3 | S2 | O | Setup is five questions plus derived technical fields. The fresh agents showed many open items at once (the skill says both "one clear question at a time" and "show the summary, ask once") and invented derived numbers. | setup skill; tracker V-17 round 2 |
| U-4 | S2 | O | Jargon reaches the user (atlas, pivot, key colour, near-key, clean plate, anchors). There is no glossary and no rule to explain a term at first use; the lifecycle skill's "Say it simply" covers reporting only. | skills; docs |
| U-5 | S2 | O | No environment doctor. A missing `jsonschema` is a clear hard failure, but agents improvise installs (tracker U-7 open) and this session met Windows traps: no `python3`, venv launchers, hooks run in Git Bash. | tracker V-15, V-16, U-7 |
| U-6 | S2 | O | Only mockups can be brought in. Existing sprites, sheets and tilesets cannot be registered as assets; `register-asset` expects a bundle the pipeline built. Many users arrive with half-made art, and adopting it as the style anchor is the fastest route to consistency. | `scripts/gamearts_asset_lifecycle.py` (import-mockup only); master §20 |
| U-7 | S2 | O | No uniform ending for a stage ("what exists / what I need from you / what comes next"). The storyboard has `next`; restore has a `next_step`; the fresh agents wrote their own endings, good but varied. | storyboard script; lifecycle `restore`; tracker V-17 |
| U-8 | S3 | I | No cost or effort preview. Image calls cost time and, for a connected tool, credits; nothing tells the owner how many calls a plan needs, and the owner's rule is not to spend a paid tool's credits unasked. | owner rules; master §4 |
| U-9 | S3 | O | Discoverability: the phrase list lives in the README and COMMANDS; inside a game there is no defined "what can I do now" behavior. | README, COMMANDS |
| U-10 | S3 | I | No rule that the agent answers in the user's language, or that review artifacts have text alternatives and sufficient contrast. | master §23 |

### 3.3 What comparable systems do (adopt, adapt, avoid)

"Documented" means a primary page states it; "claimed" means a vendor or third party states it. The decisions are mine.

| System | Documented or claimed capability (source ids in §11) | Decision |
| --- | --- | --- |
| Tiled | Terrain sets are Wang sets of type corner, edge or mixed; a complete 2-terrain set has 16 (corner), 16 (edge) or 256 (mixed) tiles; the 47-tile blob is a reduced mixed set (15 with rotation); up to 254 terrains; completeness is not required [documented, T1] | **Adopt** the vocabulary and layout kinds; **adapt**: our validator reports completeness and seam matches, and exports a Tiled-readable description as a file format. |
| Godot 4.7 `TileSet` / `TileMapLayer` | Tile shapes square, isometric, half-offset square and hexagon; tile layouts (stacked, stairs, diamond) and an offset axis for the half-offset shapes; terrain modes match corners and sides / corners / sides; sixteen peering positions (sides and corners around a cell); `TileMapLayer` is the node that uses a `TileSet` [documented, fetched 2026-10-24, G1] | **Primary consumer.** Our tile layout kinds map onto the terrain modes (blob 47 to corners and sides, Wang corner 16 to corners, Wang edge 16 to sides) and our per-tile neighbour labels onto the peering positions; the dual-grid layout needs a second layer offset by half a tile, which is a game-side arrangement. The mapping lives in the Godot **profile** (D-16), never in code here. |
| Godot 4.7 `SpriteFrames` and `Animation` | Per-animation frames with a **relative duration** and a speed in frames per second; loop modes none, linear and **ping-pong**; animation tracks with interpolation nearest, linear, cubic, linear-angle (shortest rotation) and cubic-angle, and a per-key `transition` curve for generic tracks; the docs do not say whether position, rotation and scale tracks accept a per-key transition [documented, G2, G3] | **Primary consumer.** Atlas `tags` map to animations (forward, reverse, ping-pong), `duration_ms` to relative duration and speed, `easing` to interpolation and transition; the undocumented per-key case is verified in a headless run (T-7) before the profile states it. |
| Godot 4.7 `CanvasItemMaterial` and `Parallax2D` | Blend modes mix, add, subtract, multiply and premultiplied alpha (no screen mode); `Parallax2D` has `scroll_scale`, `repeat_size`, `repeat_times` and `autoscroll` [documented, G4, G5] | **Primary consumer.** The effect blend metadata and parallax layer fields use names that map one to one; a blend mode the engine lacks (screen) is marked "needs a shader" in the profile instead of being silently dropped. |
| Godot 4.7 `NinePatchRect`, Theme and import options | Per-side patch margins; "Fix Alpha Border" and "Premult Alpha" remedies for dark halos; lossless compression recommended for pixel art [documented, N1, E1] | **Primary consumer** through the profile; no sheet extrusion (see Aseprite row). |
| LDtk | Auto-layer rules over IntGrid values; pure auto-layers [documented, L1] | **Avoid** building rule engines (game and editor concern). |
| Dual-grid tiles | Display grid offset half a tile from the data grid; 15 to 16 tiles instead of 47; needs an offset layer at runtime [claimed by community implementations, D1] | **Adopt as a layout kind**: far fewer tiles to keep consistent in generated art; the offset layer is the game's job. |
| Aseprite CLI | Sheet export with `--list-tags`, `--list-slices`, `--sheet-pack`, `--trim`, `--extrude`, padding options; JSON in hash or array layout [documented, A1]; the JSON structure itself is not fully documented officially [A2] | **Adopt** tags (name, range, direction, repeat); **adapt** trim and pack as options; **adapt** an exporter, compatibility "best effort" until a real export is compared **[U]**; **avoid** extrusion inside delivered sheets (it would put non-key pixels outside frame cells, against master §15; the engine-side remedy is documented, E1). |
| Engine import options | "Fix Alpha Border" and "Premult Alpha" are documented remedies for dark halos at transparent edges [documented, E1] | **Adopt as guidance** in each engine profile (D-16); the master's integration contract stays worded for "your engine". |
| Nine-patch UI | Per-side margins keep corners fixed and stretch or tile the rest [documented, N1] | **Adopt** `nine_slice` margins as frame metadata. |
| Retro Diffusion, PixelLab, SpriteCook | Grid-aligned limited-colour output, palette input, tile and animation modes, skeleton animation, themes or presets that "lock style and mood" [claimed by vendors and hosts, R1, P1, C1] | **Adopt as checks, not as a dependency**: palette lock and grid conformance are tool-agnostic validators; **adapt** presets as data; **avoid** naming any vendor in presets. |
| Scenario, Layer | Style models trained on a small, consistent set (Scenario's article, as read: at least 5 images, 10 to 15 recommended for beginners and at most 20, 1024 px or larger); Layer: style training and 40+ pre-built styles [documented S1; claimed L2] | **Adapt**: the style anchor is a small curated reference set plus a palette; training is a tool capability a `connected_tool` can use. |
| Midjourney, OpenAI image edits | Style references carry look without subject; edits accept one or more reference images, a mask applies to the first image [documented M1, O1] | **Adopt** attaching the approved anchor as an extra reference wherever the chosen tool accepts several images. |
| Pixel-art fixers (open-source cleaner, Retro Diffusion fixer, snappers) | Detect the virtual pixel grid, downscale each block to one pixel (centre, region or majority), optionally map to a palette; limits: anti-aliased boundaries blend, wide irregular pixels miscount [documented README, X1; claimed X2] | **Adopt the algorithm outline** as a working-copy tool; **avoid** copying code (the cleaner is reported GPL-3.0, so write it from the described method). |
| Atlas bleeding | Gutter plus edge extrusion prevents neighbour bleed when filtering [claimed by tool docs and forums, B1] | **Keep padding (default 2)**; extrusion stays engine-side. |
| Gallery products | The compared products are visual web apps with galleries and presets [claimed, C1, L2, S1] | **Adapt** as one offline HTML report, no service, no account (D-8 scope). |

## 4. Decisions taken (the owner may overrule any of them)

Taken under the standing rule to research and decide rather than hand questions back. They continue the tracker's D-1 to D-7.

| ID | Decision | Why |
| --- | --- | --- |
| D-8 | The exact opaque `#FF00FF` PNG stays the canonical delivery for every style. Soft edges get an **additive** companion coverage file (`<name>.matte.png`), only for presets that declare `soft_edges`, and only after the P12.4 spike proves a source of true alpha. Pixel art never gets a matte. | Keeps the owner's masking standard intact while removing the quality ceiling for smooth styles. |
| D-9 | Presets are **data** (validated JSON in `presets/`), never policy. Policy stays once in the master; presets name values for the master's existing fields and the checks to run. No preset names a vendor or an engine. | One owner per fact; shipped-text guard. |
| D-10 | Exporters write **file formats** of the framework's measured data (Aseprite-style JSON, array JSON, Tiled tileset XML). No engine node, scene, script or addon is added (D-2 stands). | Interoperability without engine work. |
| D-11 | No new runtime dependency: Pillow, `jsonschema` and the standard library only (HTML, GPL palette text and GIF/APNG are all writable with them). | Install guide stays two packages. |
| D-12 | Lanes shorten the **conversation**, never a gate. Quick applies only to a static single asset the analyzer classifies as having no detachable parts; each approval is still recorded against its exact revision. One user message may approve several named revisions (batch). | T-4 without weakening master §8 or §17. |
| D-13 | Every schema change is additive and optional; every existing `project.json`, manifest and bundle stays valid with an unchanged material-settings hash (frozen fixtures plus the legacy-updater test prove it). | Enrolled games must not break (tracker D-6 lesson). |
| D-14 | A style anchor is a **mockup with scope `style`**, not a new lifecycle kind. It reuses register, approve, revoke, restore, hashes and rollback. | Rule 3: one lifecycle owner. |
| D-15 | Tile layouts supported first: `single`, `variants`, `wang_corner_16`, `wang_edge_16`, `blob_47`, `dual_grid_16`. Each tile carries neutral neighbour labels (centre plus the eight sides and corners); engine-specific terrain resources and rule engines are out of scope. | Matches the documented standards (Tiled, and the Godot peering positions map onto the same eight neighbours) without engine work. |
| D-16 | The engine is a **per-project setting**. `engine_target` names a profile (`generic` when absent) and an optional version note. Profiles are validated data in `presets/engines/` (what to export by default, what to recommend for the saved art style, how each framework concept maps to the engine's own), each with dated primary sources. Godot is the first complete profile; further profiles are added only after their primary documentation has been read. `engine_target` is not a material setting: changing it never flags approved art. | The owner uses Godot; other developers use other engines; one framework must serve both (owner, 2026-10-24). |
| D-17 | D-2 stands for **code**: no engine node, scene, script, shader, addon, fixture or workflow in this repository, and the guard keeps failing on engine files. What changes is *data*: engine names may appear in `presets/engines/*.json` and in a game's own `project.json`, nowhere else in shipped text. The docs guard is narrowed to that single exception. | The profiles must name engines to be useful; this keeps the exception as small as it can be. The owner may revert it. |
| D-18 | A **derived runtime export** (`export_runtime.py`): from a key-colour sheet and its atlas (and, when present, its matte) write an RGBA PNG with real alpha into a separate `runtime/` folder next to the bundle, hash-linked to its source. The key-colour sheet stays the canonical, approved delivery; the derived files are never approved, never a source and can be regenerated. | Removes the need for every game to hand-write key removal (S-16) and lets an engine's own import pipeline do the rest. |
| D-19 | Concept names are chosen to map one to one onto widely used engine terms where the terms agree (loop `none`/`loop`/`pingpong`; interpolation `nearest`/`linear`/`cubic` plus shortest-arc rotation; UI states `normal`/`hover`/`pressed`/`disabled`/`focus`; blend `normal`/`additive`/`subtractive`/`multiply`/`premultiplied` and `screen`; parallax `scroll_scale`/`repeat`/`autoscroll`). A concept an engine lacks is marked in that engine's profile, never dropped. | Keeps profiles thin and mappings checkable. |

## 5. Phases

Order and gates: **P9 → P10 → (P11 ∥ P13.1 to P13.3) → P12 → (P13.4 to P13.6) → P14.** P9 comes first because presets and recipes refer to world kinds and direction sets.
Each phase's checks are written first as failing tests against the current behavior, then the change lands, then the test passes and a revert-the-fix proof shows it can fail (the first plan's rule;
tracker "Completion rules"). Verification is focused (named test files or cases); CI runs the rest. Policy changes go to the master first, then both skill trees, schemas, scripts, docs and tests together,
in place. Delivery slices are in §9.

### P9: Profiles that fit every game (S-1, S-2, S-12, S-13)

Acceptance criteria
- A9.1 `world_kind` (`grid_world` default when absent, `free_world`, `layered_scene`, `screen_space`) decides which `world` fields are required. A `screen_space` project with no `world` block passes `check-settings`, registers a mockup and gets a reference crop; `grid_world` without tile fields still fails with a message naming the missing field.
- A9.2 `directions` accepts a named set (`dirs_8`, `dirs_4`, `dirs_2_mirrored`, `dirs_1`) or an explicit list. A four-direction project prepares a mobile crop with no per-job exception; a job asking for a different count is refused with the reason; the eight-direction behavior is byte-for-byte unchanged.
- A9.3 The grid and camera table gains `hex_pointy` and `hex_flat` (tile geometry and scale rules) and `layered_scene` (an ordered parallax layer list, each layer with `scroll_scale`, an optional `repeat` size and an `autoscroll` speed, D-19); `side` gains stated conventions (ground line, one-way platform, slope handled as a tile layout in P12). Each has a calibration rule.
- A9.4 The asset-class table gains `tileset`, `parallax_layer`, `portrait_set`, `icon_set`, `effect_sprite` and `card_layer_set`, each with view, direction, masking and atlas rules; the reference-job schema and the crop script resolve their directions.
- A9.5 Every existing fixture `project.json` validates unchanged and keeps its material-settings hash (D-13).

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P9.1 | `world_kind` with conditional requirements in the project schema; lifecycle and crop script read it | none | `test_project_schema.py`, `test_gamearts_asset_lifecycle.py`, frozen-fixture hash test | built, locally verified (V-19, re-run V-24) |
| P9.2 | Named direction sets; crop script derives allowed counts from the project | P9.1 | `test_prepare_reference_crop.py` | built, locally verified (V-19, re-run V-24) |
| P9.3 | Hex, layered-scene and side conventions in master §6 and the schema enums; calibration rules | P9.1 | `test_contract_schemas.py`, `test_docs_guard.py` | built, locally verified (V-19, re-run V-24); the `side` ground-line conventions are documented, not enforced |
| P9.4 | New asset classes in master §7, reference-job schema, crop script | P9.3 | `test_prepare_reference_crop.py` | built, locally verified (V-19, re-run V-24) |
| P9.5 | Frozen pre-change fixtures for project, manifests and bundle; legacy-updater test re-run | none | `test_sync_local_agents.py`, new fixture test | built, locally verified (V-19, re-run V-24): the frozen hashes live in `test_world_kinds.py`, the legacy-updater test in `test_sync_local_agents.py` |

### P10: Style presets, genre recipes, setup by choice (S-3, S-11, U-3, U-4 in part)

Acceptance criteria
- A10.1 `presets/styles/*.json` validate against a new `schemas/gamearts-style-preset.schema.json`. First release: at least ten looks, candidates `pixel_low` (8-bit era), `pixel_mid` (16-bit era), `pixel_hd`, `cel_shaded`, `painterly`, `ink_line`, `flat_vector`, `cutout_paper`, `rendered_2d`, `minimal_silhouette`. Each has: id, title, a description of at most 40 words, the `art_style` policy values, compatible camera presets, native-size guidance, animation approach (frame-by-frame or cut-out), at most five generator pitfalls, `required_checks` (names from P11), `soft_edges`.
- A10.2 A guard test fails when a preset names a vendor, an engine or a check that does not exist, and when a preset's compatible cameras are not in the master table.
- A10.3 The setup flow becomes: (1) what kind of game (a recipe, or "describe it"), (2) pick a look from at most six suggestions for that genre plus "something else", (3) a six-line plain summary and one confirmation. Derived technical fields (tile metres, scale, snap, direction set) are proposals, never questions. The chosen preset is saved as `art_style.preset`; changing it is a material change under the existing rule.
- A10.4 `docs/GENRE_RECIPES.md` covers 12 genres (top-down RPG and farming sim, platformer and metroidvania, isometric tactics and city builder, tower defense, shoot-'em-up, fighting and beat-'em-up, roguelike with modular rooms, card and board, match-3 and puzzle, visual novel, idle and clicker, endless runner), each with camera and grid, suggested presets, asset classes in order, the gates that matter and pitfalls. It is design guidance and says so [I].
- A10.5 The updater ships `presets/` (a prefix and extension test with an injected fetcher); an updater from before this change simply ignores the folder.
- A10.6 **Engine target (D-16, D-17).** `engine_target` is an optional project setting `{profile, version_note}`; the profile id is a slug checked against the files in `presets/engines/` (so the schema names no engine), `generic` when absent, and it is not part of the material-settings hash. `schemas/gamearts-engine-profile.schema.json` validates profiles. A profile holds: `id`, `title`, `documented_against` (engine version and date), `default_exports` (names of derived exports to write), `import_guidance` (per art-style family: filter, compression, alpha-edge handling, pixel snapping), `concept_map` (framework concept, engine term, note, `support`: `native`, `needs_custom` or `absent`) and `sources` (URL, retrieval date, `documented` or `claimed`). No profile contains code, a shader or a scene.
- A10.7 Two profiles ship first: `generic` (no engine named, plain guidance) and `godot` (written from the 4.7 documentation read on 2026-10-24 and every mapping exercised in a headless 4.7.2 run, T-7). A guard fails when a profile lacks a source for a `native` claim, names a concept the framework does not have, or contains anything but data.
- A10.8 The setup flow asks one question, "Which engine or tool will use this art?", listing the profiles found in `presets/engines/` plus "something else" and "not decided yet"; the answer is saved without confirmation friction (like the image generator) and `check-settings` prints the resolved profile. The docs guard allows engine names only inside `presets/engines/*.json`.
- A10.9 Starting a new game from another: when the user names an existing game folder, the agent proposes that game's engine target, image generator and style preset as defaults to confirm. Nothing outside the named folder is read and nothing is written to the user's home folder.

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P10.1 | Preset schema, ten presets, guard test | P9.1 | new `test_style_presets.py`, `test_docs_guard.py` | built, locally verified (V-19, re-run V-24): ten presets; the guard is in `test_presets.py`, not a separate `test_style_presets.py` |
| P10.2 | Setup skill and `PROJECT_SETTINGS.md` rewritten around choices (policy stays in master §4 and §5) | P10.1 | fresh-agent eval E-1, E-3 | built, locally verified (V-19); the fresh-agent evaluation is P14 |
| P10.3 | `docs/GENRE_RECIPES.md` and recipe pointers in the orchestrator skill | P10.1 | link and name checks in the docs guard | built, locally verified (V-19) |
| P10.4 | `presets/` in the updater's shipped set | P10.1 | `test_sync_local_agents.py` | built, locally verified (V-19, re-run V-24) |
| P10.5 | `docs/GLOSSARY.md` and the "explain a term at first use" rule in master §23 | none | docs guard; rubric in P14 | built, locally verified (V-19); the rubric is P14 |
| P10.6 | `engine_target` in the project schema (non-material), profile schema, `generic` profile, loader shared by `check-settings`, the exporters and the report | P9.1 | `test_project_schema.py`, `test_contract_schemas.py`, new `test_engine_profiles.py` (hash unchanged when the target changes) | built, locally verified (V-19, V-24): the profile loader and schema are covered by `test_presets.py`, and the unchanged hash and the engine switch by `test_engine_switch.py` (there is no `test_engine_profiles.py`) |
| P10.7 | Godot profile written from the 4.7 documentation, every mapping verified in a throwaway headless project (scripts and project kept in the session scratch folder, no engine file enters the repository) | P10.6, P12.1 to P12.6 for the mappings they define | recorded run output in the tracker; profile guard | built; observed in Godot 4.7.2 (V-18, V-22, V-23, re-run V-24). The probe projects live in `plans/enhancements/evidence/godot_profile_verification` and `godot_integration`, not in a scratch folder, because they are the record; the docs guard skips `plans/` |
| P10.8 | Docs guard narrowed to the single data exception (D-17); setup skill question; `check-settings` echo | P10.6 | `test_docs_guard.py` (engine files and engine words elsewhere still fail), setup skill eval | built, locally verified (V-19, V-24); the setup-skill evaluation is P14 |
| P10.9 | Profile backlog: Unity, Phaser (web), GameMaker, Defold. Each is added only after its primary documentation is read and cited; none is written from memory | P10.6 | per profile: the same guard plus a cited-source check | four profiles built (Unity, Phaser, GameMaker, Defold) from cited pages read 2026-10-24 (V-23); **documented only, none run in its engine** |

### P11: Consistency and quality checks (S-4, S-5, S-10)

Acceptance criteria
- A11.1 `style` is a mockup scope (the four-place enum: lifecycle constant and three schemas). An anchor is a `style` mockup, a board of hero asset(s), palette swatches, an outline sample, a shading sample, a tile and a UI sample, approved once. `art_style.anchor` names its `{mockup_id, revision}`. When set, every reference packet lists the anchor board as a secondary reference image, hash-bound; `verify` fails if it changed; an anchor revoked or superseded blocks new production until a new one is approved.
- A11.2 Style exploration: a script builds a labelled contact sheet of 1 to 6 candidate mockups (labels outside the art, nearest or smooth scaling by style); candidates are ordinary `generated` mockups made by the owner's tool; the user's pick becomes the anchor draft. The sheet is a review aid, never art.
- A11.3 `extract_palette.py` reads an approved anchor or mockup and writes `palette.json` plus a GIMP-style `.gpl` text next to it, with a colour cap, deterministically (same input, same palette).
- A11.4 `validate_style_conformance.py` runs the checks a preset lists and returns `passed`, `failed` or `untested` per check: `palette_exact`, `palette_near` (Lab distance, tolerance per preset), `colour_count_max`, `pixel_grid` (detected virtual pixel size and the share of off-grid pixels), `integer_scale`. It is wired into the technical artwork gate of `approve` only for the checks the asset's preset lists.
- A11.5 `snap_to_pixel_grid.py` produces a **labelled working copy**: detect the grid, take the block majority colour, optionally map to the palette, keep the original, write a report; it refuses an input with no consistent grid and says why.
- A11.6 `check_animation.py` reports loop-seam difference against the mean frame-to-frame difference, pivot drift, clipping at the cell edge, static-region drift outside a declared moving region, duplicate frames and the duration total; `render_preview.py` writes a strip PNG and an animated GIF or APNG with nearest scaling and a key-colour toggle. Previews are review aids, never art; thresholds come from the preset.
- A11.7 Every new check is deterministic, reports what it did not assess, and is measured at 2048 px and 4096 px so a performance budget is recorded (V-6 style).

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P11.1 | `style` scope, anchor field, anchor in reference packets | P10.1 | `test_gamearts_asset_lifecycle.py`, `test_prepare_reference_crop.py`, `test_contract_schemas.py` | built, locally verified (V-20) |
| P11.2 | Contact-sheet builder and the exploration step in the mockup-creator skill | P11.1 | new `test_contact_sheet.py`; eval E-1 | built, locally verified (V-20) |
| P11.3 | Palette extraction and files | P11.1 | new `test_palette.py` (golden output) | built, locally verified (V-20) |
| P11.4 | Style-conformance validator and its hook into `approve` | P11.3 | new `test_style_conformance.py` with synthetic fixtures: clean pixel art, the same art upscaled 3.3x with blur, palette-drifted art | built, locally verified (V-20) |
| P11.5 | Pixel-grid snapper (clean-room) | P11.4 | fixture: clean art enlarged 4x with noise recovers exactly; a no-grid input is refused | built, locally verified (V-20) |
| P11.6 | Animation checks and previews | none | new `test_animation_checks.py`: perfect loop vs broken seam, clipped frame, drifting pivot | built, locally verified (V-20); static-region drift not built |
| P11.7 | Timing at 2048 px and 4096 px recorded in the tracker | P11.4-P11.6 | measured, not asserted | measured (V-21) |

**What slice 2 built, and where it differs from the text above**
- The animation checks, the palette module and the grid detector are separate owners: `check_animation.py`, `gamearts_palette.py` and `gamearts_pixelgrid.py` (the pixel-grid check and the snapper share the one detector). `render_preview.py` also owns the checkerboard the offline report draws.
- `check_animation.py` implements loop seam, pivot drift, clipping and repeated frames. **Static-region drift outside a declared moving region is not built** (no atlas field declares a moving region yet); the master states it as not automated. The checks inform and never block approval until atlases carry animation tags (a walk is a loop, an attack is not, and the framework cannot tell them apart today).
- A failed style-conformance check **blocks approval**; `untested` and `not_applicable` never do. Only checks the preset lists run, and only the still-image ones (`palette_exact`, `palette_near`, `colour_count_max`, `pixel_grid`, `integer_scale`).
- Grid detection scores a candidate grid *above chance* (a fine grid catches many edges by luck) and numbers cells gap by gap, so missing edges (neighbouring cells of one colour) and fractional enlargements do not break it. Both were found by tests that first failed (V-20).
- The contact sheet writes to `.gamearts/system/exploration/` and the report's animation previews to `.gamearts/system/report/previews/`; neither is registered, approved or a source. The report shows each animation as a still strip with a link to the GIF, because a GIF that starts by itself cannot be paused.

### P12: Asset-kind depth (S-6, S-7, S-8, S-9, S-12, S-14, S-16)

Acceptance criteria
- A12.1 **Tilesets.** `schemas/gamearts-tileset.schema.json` records tile size, layout kind (D-15), terrain names, per-tile neighbour labels (the centre plus the eight sides and corners, D-15) and the required-tile list derived from the layout. `build_tileset.py` assembles supplied tiles into a sheet and atlas; `validate_tileset.py` reports missing tiles by name, edges that claim adjacency but do not match, wrong tile size and key-policy failures. An exporter writes a Tiled-readable tileset description from the measured data.
- A12.2 **UI kits.** The atlas frame gains optional `nine_slice: [left, top, right, bottom]` and `state` (`normal`, `hover`, `pressed`, `disabled`, `focus`). The validator checks margins lie inside the frame, a declared control has its full state set, and an icon set shares size and padding.
- A12.3 **Atlas depth.** Optional `tags` (name, from, to, direction `forward`/`reverse`/`pingpong`, repeat), `trim` (cell sized per frame from the measured ink bounds) and `pack` (shelf packing); default padding stays at least 2; no extrusion in the delivered sheet. `export_exchange.py` writes Aseprite-style JSON (array and hash), array JSON and the tileset description; compatibility is stated as "best effort" until the owner compares a real export (§8).
- A12.4 **Soft edges.** After the spike (P12.0): if the chosen tool can return true alpha, deliver `<name>.png` (key) plus `<name>.matte.png` (8-bit coverage, same geometry) for presets with `soft_edges`; `validate_matte` proves the pair is consistent (coverage 0 exactly where the key PNG is key and nothing but key lies outside ink; coverage 255 inside solid art; hashes recorded in the atlas). If no true alpha is available the limitation stays documented and the presets recommend hard-edge treatment. Master §15 is amended additively.
- A12.5 **Effects.** The `effect_sprite` class carries advisory blend-mode metadata (`normal`, `additive`, `subtractive`, `multiply`, `screen`, `premultiplied`, D-19) in the atlas for the game project to use; nothing here applies it. An engine profile marks each mode `native`, `needs_custom` or `absent`.
- A12.6 **Cut-out timing (S-14).** An optional per-track `interpolation` (`linear` default, `nearest`, `cubic`; rotation also accepts `shortest`, which today's `rotation_interpolation` already provides and which stays valid) and an optional per-keyframe `easing` (`linear` default, `ease_in`, `ease_out`, `ease_in_out`) in the component job; `sampled_poses` honor both so they stay the numeric oracle; a job without them builds byte-identically to today.
- A12.7 **Runtime-ready export (S-16, D-18).** `export_runtime.py` writes, for a bundle or a single sheet, an RGBA PNG whose pixels outside art are fully transparent and whose art pixels keep their colour (alpha 255, or the matte's coverage when a matte exists), plus a runtime atlas JSON with identical rectangles, pivots and tags. Every derived file records the hash of its source; re-compositing the export over the key colour reproduces the canonical sheet exactly (the round-trip test). Derived files live in `runtime/`, are listed in the manifest as `derived`, are never approved and never a source for new art. The default is chosen by the engine profile's `default_exports`.

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P12.0 | Spike: can the owner's chosen tool return true alpha (**[U]**)? Run once with a real session in the owner step | none | recorded result in the tracker | ran 2026-10-27 with Codex's built-in tool (tracker V-26): it returned a genuine RGBA file with soft alpha when asked for a transparent background; one sample |
| P12.1 | Tileset schema, builder, validator, exporter | P9.4 | new `test_tileset.py`: complete `blob_47` passes; a missing tile and a mismatched edge are named; `dual_grid_16` passes | built, locally verified (V-22): schemas, builder, validator, gate, Tiled export |
| P12.2 | UI kit metadata and validator | P9.4 | new `test_ui_kit.py` | built, locally verified (V-22) |
| P12.3 | Tags, trim, pack, exchange export | none | `test_build_sheet_atlas.py`, `test_validate_sheet_atlas.py`, new `test_exchange_export.py` | built, locally verified (V-22): tags, trim, shelf pack, Aseprite array and hash export; checks with tag awareness are not built |
| P12.4 | Matte companion and validator (only if P12.0 says yes) | P12.0, P12.3 | new `test_matte.py` | built, locally verified (V-26): `gamearts_matte.py` (split, check), job option `soft_alpha`, atlas `matte` record, matte-driven runtime alpha, refusal for hard-edged looks |
| P12.5 | Effect class and blend metadata | P9.4 | `test_contract_schemas.py` | built, locally verified (V-22): advisory `blend_mode` on the atlas (the `effect` class already existed) |
| P12.6 | Track interpolation and keyframe easing in the component builder and the sampled poses | none | `test_component_bundle.py`: unchanged output without them; a known curve at known times | built, locally verified (V-22) |
| P12.7 | Runtime-ready export and its manifest listing | P12.3 | new `test_export_runtime.py`: exact round trip over the key colour, hashes recorded, a changed source is detected, the canonical sheet is untouched | built, locally verified (V-22) |

**What slice 3 built, and where it differs from the text above**
- One module, `gamearts_atlas.py`, owns the meaning of tags, nine-slice margins, control states and icon sets and the picture rectangle of a frame; `gamearts_tileset.py` owns the layouts. The builder, the validator, the exporters and the tests all ask them.
- Tags follow Aseprite's frame tags (four directions, `repeat` 0 or absent meaning forever). `check_animation.py` does not yet use tags to judge only the frames that loop; its loop-seam result stays informational, as the master says.
- Trim is a per-frame cell of the art joined with the pivot, and it requires the shelf layout. A nine-slice frame is never trimmed, because its margins are measured on the whole source frame.
- The tileset file holds labels only; geometry stays in the atlas it names (tile *n* is frame *n*), so there is one owner of every rectangle. Seams are judged against each tile's own texture variation, which is a heuristic for tiles that look right, not a proof that they do.
- The runtime export writes to `.gamearts/outputs/runtime/<asset>/<revision>/`, outside the status folders, records `derived_exports` on the asset, is checked by `reconcile-assets` and deleted by `revoke`. The engine profile's new `default_exports` makes it automatic on approval for Godot; `generic` makes none. It produces no soft alpha (P12.4 is the only route to that).
- **Cubic interpolation is the framework's own curve and the engine's differs** (observed: 5.0 where the framework gives 6.25), so the Godot profile marks it `needs_custom`; easing is exact (transition values 2.0, 0.5 and -2.0).
- Writing the runtime export exposed a Windows defect that had been an unexplained intermittent test failure: moving a freshly written folder (approve, revoke, publish) can fail with "access denied" while a scanner holds it open. Every move and replace now goes through one bounded-retry owner in `gamearts_common.py`, and a source test fails if a script moves a path any other way (V-22).

### P13: Friendly operation (U-1 to U-10)

Acceptance criteria
- A13.1 **Report.** `gamearts_report.py` writes `.gamearts/report/index.html`: one self-contained page, no network request and no script dependency beyond optional toggles. It shows next steps, settings in plain words, the style anchor and palette swatches, storyboard progress, mockups and assets as cards (status, thumbnail, the user's approval quote, validation grades in plain labels, animation preview where one exists), an "Integration notes" panel built from the saved engine profile and art style, and revoked items collapsed. Pixel presets render with nearest-neighbour scaling; a key/checkerboard toggle is offered. It is built **only** from the manifests and reports, so it can never show a status the records do not hold. It is regenerated after every successful lifecycle operation; if rendering fails the operation is not failed, and the failure is reported and logged, never swallowed. Accessible: text alternatives, contrast, keyboard focus, reduced-motion respected.
- A13.2 **Doctor.** `check-environment` reports Python and package versions, write access to `.gamearts/`, the saved image generator and whether this session has it, the saved engine target and whether its profile exists, updater state, and OS notes (which interpreter command works), with a fix hint per failure; machine-readable output for the agent; it never installs anything itself.
- A13.3 **Next-step contract.** Master §23 gains: every stage ends with what exists, what is needed from the user and what comes next, in the user's language, with jargon explained at first use; the orchestrator skill gains a "what can I do now" behavior driven by project state. Every lifecycle operation returns `ok`, `message` and `next_step` so the line is built from facts.
- A13.4 **Plan card and lanes.** Before the first image call the agent shows: lane (Quick, Standard, Full), the number of expected image calls, the approvals the user will be asked for, and, for a connected paid tool, the credits implied. Quick applies only to a static single asset or tile with no detachable parts; an attempt to use Quick for a composite asset is refused by the existing cleanup gate, which is tested.
- A13.5 **Batch approval.** `approve-batch` approves a named list of exact mockup or asset revisions on one user reference; each item goes through the existing single-approval path with its own audit and rollback; an item that was not shown, is not `generated` or fails its gate is reported and left unapproved while the rest proceed.
- A13.6 **Adopt existing art.** `import-asset` wraps a supplied sheet (a stated grid, or an Aseprite-style or array JSON the user has) into a measured atlas, registers it as `generated` with provenance `supplied by the user` and rights from the user's words, and offers the art as the style anchor. The original is never altered.

| ID | Task | Depends | Check | Status |
| --- | --- | --- | --- | --- |
| P13.1 | Report generator and its hook | none | new `test_report.py`: golden page for a fixture game, no external URL, well-formed HTML by the standard parser, statuses equal the manifests | built, locally verified (V-19) |
| P13.2 | Doctor | none | new `test_environment_check.py`: missing package, unwritable folder, no image tool | built, locally verified (V-19) |
| P13.3 | Structured operation results; next-step contract; help behavior | none | contract test across operations; rubric in P14 | built, locally verified (V-19); the fresh-agent rubric is P14 |
| P13.4 | Plan card and lanes in master §3 and §8 and the orchestrator skill | P10.2, P13.3 | eval E-1 (icon), E-7 (composite); gate test | built, locally verified (V-23); the evaluations are P14 |
| P13.5 | `approve-batch` | P13.3 | `test_lifecycle_operations.py`, revert-the-fix proofs | built, locally verified (V-23): `test_approve_batch.py` |
| P13.6 | `import-asset` and style-anchor-from-existing-art | P11.1, P12.3 | new `test_import_asset.py` | built, locally verified (V-23) |

**What slice 4 built, and where it differs from the text above**
- The plan card is one owner, `gamearts_plan_card.py`. It counts pictures with a stated formula (retries and revisions are not counted), names the lane and the approvals, and **never states a price**: the framework cannot know what a paid tool charges, so the card says who bills and tells the owner to ask a connected tool for a quote. Quick does not make a composite asset easier: the cleanup and review gates still decide. The master's lane text and the orchestrator skill's step 4 point at it.
- `approve-batch` takes `--item ID:REVISION` (repeatable) and `--shown ID:REVISION` (the revisions the owner was actually shown). Each item goes through the ordinary single approval, so each has its own gate, audit and rollback; an item that was not shown, is not waiting, is missing or fails its gate is reported and left, and the rest go ahead. One approval reference (the owner's own words) covers the batch. It is a mutating operation under the one lock.
- `import-asset` takes exactly one of a grid, a cell size or an Aseprite data file (array or hash form, which also supplies frame times and tags). A soft pixel is refused with its count unless the owner chooses an alpha threshold, which is recorded in the provenance; trimmed frames are restored to their source canvas; rotated frames are refused; a blank cell stays a blank frame and is counted. The reference picture is approved on the owner's own words and the production asset is registered as `generated`, still needing its own approval. Everything is checked in a scratch folder first; a failed registration removes the new bundle and says which reference stayed. With `--anchor` the same picture is also offered as the style anchor and saving it stays the owner's change through setup.

### P14: Evaluate

Acceptance criteria
- A14.1 The nine scenarios below are run by fresh agents against the installed files, at least twice each in Claude Code agents and once in a Codex session where the tool is available; every repetition and every failure is recorded, not only the good ones (SDLC evidence policy).
- A14.2 Each scenario passes only if every rubric line holds; a failed line produces a finding and a fix, then a re-run.
- A14.3 The owner runs one real-model session per slice (§9), checks the report opens, and imports the exports into a real Godot project of theirs and compares an exporter output in a real tool; the results go in the tracker as owner-run evidence, separate from agent evidence.
- A14.5 **Engine mappings are observed, not assumed (T-7).** For every mapping the Godot profile states, a throwaway project in the session scratch folder (never in the repository) loads the framework's output with the installed Godot 4.7.2 headless console build (a `TileSet` with terrain sets from the neighbour labels, `SpriteFrames` from tags and durations, a `NinePatchRect` from margins, an `Animation` from interpolation and easing, a `CanvasItemMaterial` blend mode, a `Parallax2D` from layer fields, import of the derived RGBA export) and records command, exit status and the observed result. A mapping that fails or cannot be shown is marked `needs_custom` or `absent` in the profile, never left as `native`.
- A14.6 **Engine switching is safe (T-6).** A fixture game with approved art has its engine target changed from `godot` to `generic` and back: material-settings hash identical, no `review_flags`, no approval state changed, only the guidance and default exports differ.
- A14.4 Guards: a skill size budget test keeps every `SKILL.md` below a stated size (the skills were deliberately cut to about 40%); new shipped text names no engine and no vendor.

| Scenario | Request (scripted user) | Rubric (observable behavior) |
| --- | --- | --- |
| E-1 | Cozy pixel top-down farm sim, 32 px, "make me a coin icon" | Three messages to confirmed settings; no world-geometry invention; Quick lane named in a plan card; two approvals at most; palette and grid checks run and reported; report path offered. |
| E-2 | Painted side-scrolling platformer with parallax backgrounds | `layered_scene` or `side` chosen from plain words; parallax layers listed as an inventory; soft-edge limitation disclosed or the matte lane used, never silent. |
| E-3 | Flat-vector match-3 game | `screen_space`; no world questions; UI kit with nine-slice and states; icon-set consistency reported. |
| E-4 | Visual novel | `screen_space`; `portrait_set` with an expression list; backgrounds as scenes; native-text rule respected. |
| E-5 | Card game | `card_layer_set` and `icon_set`; text stays native; batch approval of a set. |
| E-6 | Isometric tactics (regression) | Unchanged isometric behavior; settings hash unchanged for the old fixture. |
| E-7 | Cut-out animated character and a composite workshop (regression) | Component pipeline and cleanup gate unchanged; Quick lane refused for the workshop; animation checks reported. |
| E-8 | User arrives with an existing sprite sheet and palette | `import-asset`, measured atlas, anchor from the user's art, palette extracted, continuation conditioned on the anchor. |
| E-9 | The same pixel game set up twice, once with the Godot target and once with no engine named (or an engine with no profile) | Both complete setup; the Godot run shows Godot-specific import advice and defaults the runtime export; the other states plain guidance and offers the same exports on request; the art and the approvals are identical; no engine is assumed anywhere in the second run. |

## 6. Cross-cutting rules

- **Compatibility (D-13).** Additive schemas, `schema_version` stays "1.0", frozen fixtures, the legacy-updater test. New folders (`presets/`) join the updater's prefixes with a test.
- **Shipped-text guards.** The docs guard bans the word "godot", one game's name, engine files, version labels and corrupted text in shipped text, and requires shipped links to stay inside shipped files. Everything this plan adds to the master, skills, docs and scripts must pass it unchanged and keeps to the spirit of D-2 beyond the words the guard checks: engine documents are cited here, in `plans/`, never in shipped prose, which says "your engine" or "the engine profile". The one exception is D-17: engine names may appear in `presets/engines/*.json` data files (and in a game's own settings); the guard is narrowed to exactly that and keeps failing on engine files, engine workflows and engine words anywhere else.
- **Master headings.** New master sections are cited by heading, never by number; the numbered-once-and-in-order guard means new sections renumber the ones after them.
- **One owner per fact.** Policy once in the master; skills route and keep procedure; docs describe; presets are data. A skill that grows past its budget is a sign that policy leaked into it.
- **Honest grades.** Every new check reports `passed`, `failed` or `untested` and lists what it did not assess. Nothing certifies art quality.
- **Licences.** The open-source pixel-art cleaner is reported GPL-3.0: no code is copied; the snapper is written from the documented method.
- **Performance.** Pillow-only analysis is budgeted at 2048 px and 4096 px (P11.7); a check that exceeds its budget is reported as `untested`, not skipped silently.
- **Logging and failure.** Every new script reports failures through the same exit-code and message contract as the existing ones; none catches an exception without reporting it.

## 7. Verification strategy

- Failing test first, then the change, then a revert-the-fix proof added to `evidence/mutation_proofs.py` for each new guard.
- Fixtures are drawn with Pillow at test time (no art files in the repository): clean and blurred pixel art, palette-drifted art, perfect and broken loops, complete and incomplete tilesets, nine-slice panels, soft-edge sprites with a matching and a mismatching matte.
- Focused runs only (named files); CI runs the whole suite. Windows and Linux are both recorded; the Python 3.11 and Pillow 9.5.0 leg is included because the first plan's V-15 showed it finds real problems.
- Behavior claims need agent evidence: the P14 scenarios, not structure checks. Mechanical checks and a good-looking report prove nothing about art.

## 8. Unknowns and spikes

| ID | Unknown | Resolves in |
| --- | --- | --- |
| U-S1 | Whether the owner's chosen tool (Codex's built-in image tool) can return true alpha; OpenAI's guide documents `background: "transparent"` for named models but support differs by model | **Observed 2026-10-27 (tracker V-26): yes, with its transparent-background option, one sample.** Other prompts, looks and model versions are unobserved |
| U-S2 | The exact fields of Aseprite's JSON (no complete official schema was found) and of the array layout | P12.3: compare a real export from the owner's Aseprite before claiming compatibility |
| U-S3 | Tiled's tileset and Wang-set XML details | P12.1: read the TMX format reference at that time, then test with a real Tiled by the owner |
| U-S4 | Cost of palette and grid analysis at 2048 px and 4096 px with Pillow only | P11.7 |
| U-S5 | Whether real generator output honors a palette or a pixel grid well enough for `palette_exact` to be a default gate rather than a report | Owner session with real art, measured by P11.4 |
| U-S6 | Whether users prefer the HTML report to images shown in chat (Claude Code and Codex differ) | Owner session |
| U-S7 | How many presets and recipes are the right number | P14 results; start with ten and twelve |
| U-S8 | Godot behaviors the 4.7 documentation leaves open: whether position, rotation and scale tracks accept a per-key transition; which tile layout and offset axis a pointy-top and a flat-top hex grid need; how `Parallax2D` repeats a layer of a given width | P10.7 and A14.5: observed in the installed Godot 4.7.2 before the profile states them |
| U-S9 | Whether the owner's games use the GDScript or the C# build (the installed Godot is the .NET build) and which Godot versions they target; the profile is written against 4.7 and says so | Owner step; the profile's `documented_against` field keeps the claim honest |
| U-S10 | Which other engines matter to other developers, and what each one's primary documentation says | P10.9, one profile at a time |

## 9. Delivery slices

1. **Slice 1: fit any game, any engine, friendlier first hour.** P9, P10 (including the engine target, the `generic` profile and the narrowed guard, P10.6 and P10.8), P13.1 (report), P13.2 (doctor), P13.3 (next-step contract). Evidence: E-1, E-3, E-6, E-9. The Godot profile (P10.7) is completed in slice 3, after the metadata it maps exists.
2. **Slice 2: consistent style.** P11. Evidence: E-1, E-2, E-7.
3. **Slice 3: deeper asset kinds.** P12 (P12.0 first), the runtime export (P12.7), and the Godot profile with its headless verification (P10.7, A14.5). Evidence: E-2, E-3, E-4, E-9.
4. **Slice 4: lighter process and existing art.** P13.4, P13.5, P13.6, then the full P14 sweep. Evidence: E-1, E-5, E-7, E-8.

Each slice ends with a tracker update, a focused-test record and the owner steps it needs (push, session, real-model run).

## 10. Risks and non-goals

| Risk | Handling |
| --- | --- |
| Scope creep and skill bloat | One owner per fact; the skill size budget (A14.4); slices; presets as data. |
| Lanes weaken a gate | D-12; Quick limited by the classification; a test that a composite asset is refused. |
| Validators give false confidence | Three-state grades, "not assessed" lists, wording that never says "good art". |
| Presets go stale or copy vendor claims | Data only, no vendor names, dated sources, reviewed in P14. |
| Enrolled games break | D-13, frozen fixtures, the legacy-updater test. |
| Exporters claim compatibility they do not have | "Best effort" until compared with a real export (U-S2, U-S3). |
| Over-fit to one platform | Windows and Linux runs; the 3.11 and 9.5.0 leg. |
| The framework becomes Godot-shaped | The engine is a setting (D-16); `generic` is the default and is tested (E-9, A14.6); the profile schema names no engine; only data may name one (D-17). |
| A profile states engine behavior that is wrong or has changed | Every claim carries a source and a date; `documented_against` names the version; `native` claims are observed in a headless run (A14.5); stale profiles are re-verified when the owner changes engine version. |

Non-goals: engine code, scenes, nodes, shaders or addons (D-2, D-17); choosing an engine for a developer (the setting is theirs); a Godot-only framework; a hosted service or account; choosing or recommending an image tool for the owner (the per-game setting stays); automatic approval of anything;
claiming a generated asset is "game ready" or "good"; rule engines for autotiling; training image models.

## 11. Sources (retrieved 2026-10-24)

"Fetched" means the page was read; "search" means only the search summary was seen.

- T1 Tiled manual, terrain sets: https://doc.mapeditor.org/en/stable/manual/terrain/ (fetched)
- G1 Godot 4.7 `TileSet` class reference (tile shapes, layouts, offset axes, terrain modes, peering positions): https://docs.godotengine.org/en/stable/classes/class_tileset.html (fetched)
- G2 Godot 4.7 `SpriteFrames`: https://docs.godotengine.org/en/stable/classes/class_spriteframes.html (fetched)
- G3 Godot 4.7 `Animation`: https://docs.godotengine.org/en/stable/classes/class_animation.html (fetched)
- G4 Godot 4.7 `CanvasItemMaterial`: https://docs.godotengine.org/en/stable/classes/class_canvasitemmaterial.html (fetched)
- G5 Godot 4.7 `Parallax2D`: https://docs.godotengine.org/en/stable/classes/class_parallax2d.html (fetched; the introducing version is not stated on the page)
- G6 The installed engine: Godot 4.7.2 stable, .NET build, with a headless console executable, found at `H:\dev\Godot` on 2026-10-24 (observed with `--version`)
- L1 LDtk, auto-layers: https://ldtk.io/docs/general/auto-layers (fetched)
- D1 Dual-grid tilemap implementations: https://github.com/jamesplease/dual-grid-tilemap-system-godot-gdscript and https://github.com/pablogila/TileMapDual (search; community claims, counts differ between 15 and 16)
- A1 Aseprite CLI: https://www.aseprite.org/docs/cli/ (fetched)
- A2 Aseprite community thread on the undocumented JSON structure: https://community.aseprite.org/t/what-exactly-does-the-data-in-exported-json-represent/28435 (search)
- E1 Godot, importing images (Fix Alpha Border, Premult Alpha): https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_images.html (fetched)
- N1 Godot `NinePatchRect`: https://docs.godotengine.org/en/latest/classes/class_ninepatchrect.html (search)
- O1 OpenAI image generation guide: https://developers.openai.com/api/docs/guides/image-generation (fetched, first 100,000 of 114,677 characters read)
- S1 Scenario, train a style model: https://help.scenario.com/articles/8374017641-train-a-style-model (fetched)
- M1 Midjourney, style reference: https://docs.midjourney.com/docs/style-reference (search)
- R1 Retro Diffusion models, via Scenario's documentation: https://docs.scenario.com/get-started/generation/third-party-model-generation/third-party-model-generation-retro-diffusion (search; vendor details not read at the vendor's own site)
- P1 PixelLab skeleton animation: https://www.pixellab.ai/docs/tools/skeleton-animation (search)
- C1 SpriteCook, generate sprites: https://www.spritecook.ai/docs/guide-generate-sprites (fetched)
- L2 Layer, style training and Forge: https://www.layer.ai/features/style-training and https://help.layer.ai/en/articles/11033613-how-to-forge-2d-assets-on-layer (search; vendor marketing)
- X1 Pixel Art Cleaner README: https://github.com/Danamir/pixelart-cleaner (fetched; the GPL-3.0 licence comes from the search summary)
- X2 Other fixers: https://retrodiffusion.ai/tools/pixel-art-fixer/ , https://www.spritefusion.com/pixel-snapper , https://dev.to/jenissimo/how-to-tame-your-ai-pixel-art-3pk5 (search)
- B1 Atlas bleeding and extrusion: https://www.mintlify.com/Hexeption/FastPack/packing/extrude and the Defold forum threads in the same search (search)

Repository evidence: the tracker's verification record V-11 to V-17 and the first plan's findings register.
