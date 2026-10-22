# GAME ARTS — MASTER STANDARD
**Version:** 7.7  
**Status:** Consolidated Master Production Specification  
**Scope:** Universal 2D game graphics, all visual styles, all asset profiles  
**Target Engine:** Godot 4

---

## 1. Purpose

Game Arts is a universal, production-grade system for generating, reviewing, validating, and delivering 2D game artwork and related metadata for Godot-based games.

This standard applies to all current and future asset categories, including but not limited to:
- world-space environments and scene mockups
- terrain and tilesets
- buildings and structures
- vehicles and machinery
- props and interactive objects
- characters, agents, and mechanical entities when requested
- UI, HUD, icons, and screen-space graphics
- animated effects and stateful visual components
- sprite sheets, atlas JSON, and related metadata
- Godot-ready resources and composed scene structures

No asset category may override the universal system with ad hoc rules.  
Specialized behavior must be defined through approved asset profiles.

---

## 2. Core production principle

All Game Arts assets must be:
- visually coherent
- technically consistent
- reusable
- measurable
- validated
- production-ready for Godot integration

Never sacrifice scale consistency, visual fidelity, atlas correctness, attachment correctness, or masking correctness for speed or convenience.

---

## 3. Mandatory mockup-first approval gate

Before production generation of any new artwork for a game, first produce one or more reviewable visual mockups appropriate to the request.

The workflow is:

**Mockup → Explicit approval → Locked reference → Production assets → Validation → Delivery**

### 3.1 Mockup-first is mandatory
No final production generation begins before mockup approval for new artwork.

### 3.2 Applicable mockup types
Mockups may be created for:
- scenes
- environments
- structures
- props
- characters
- UI
- effects
- composite gameplay situations
- any other game-art deliverable

### 3.3 Mockup approval states
Each mockup revision must be explicitly marked as:
- approved
- revise
- rejected

Do not infer approval from silence.

### 3.4 Accepted mockup becomes a locked reference
Once approved, a mockup becomes an authoritative visual reference for later production.

Retain:
- mockup_id
- mockup_revision
- game_id
- asset_or_scene_id
- approval_status
- approved_reference_file
- approved visual notes
- style/palette/camera notes
- unresolved assumptions
- reference hash when available

### 3.5 Material changes require renewed approval
If composition, camera, proportions, silhouette, layout, lighting, color direction, or other major visual decisions change, generate a revised mockup and obtain renewed approval before regenerating final production art.

---

## 4. Mandatory mockup decomposition and detail extraction

After mockup approval, the agent must treat the approved mockup as a detailed production blueprint, not merely a concept or moodboard.

### 4.1 Decomposition is required
The agent must extract and inventory all relevant visible sub-elements from the approved mockup.

This includes:
- geometry
- texture and surface treatment
- material separation
- scale relationships
- local composition
- edge treatment
- repeated patterns
- decorative detail
- utility detail
- interaction detail
- animated or stateful elements

### 4.2 Scene decomposition
For scenes, the decomposition must identify:
- primary structures
- secondary structures
- roads, paths, pavement, curbs, medians
- terrain/ground regions
- grass, soil, rocks, trees, plants
- decorative elements
- street furniture and utility objects
- lights, signs, poles, barriers, fences
- interactive and animated objects
- ambient animated details

### 4.3 Object or character decomposition
For objects, props, structures, or characters, the decomposition must identify:
- major forms
- subcomponents
- attached elements
- moving parts
- stateful parts
- materials
- repeated details
- animated candidates
- interaction points

### 4.4 UI decomposition
For UI and HUD, the decomposition must identify:
- layout regions
- panels
- buttons
- icons
- indicators
- progress/display elements
- decorative motifs
- state variations
- animation candidates
- text zones

### 4.5 Production plan required
The decomposition becomes the production asset plan and animation plan.

Final production should not proceed until the approved mockup has been decomposed into:
- static asset inventory
- animated asset inventory
- state inventory
- required sprite-sheet list
- required atlas list
- required Godot integration notes

---

## 5. Universal real-life animation candidate rule

If a visible object or component has a real-world visible animated, changing, opening, rotating, flickering, swaying, sliding, deforming, or state-changing behavior, it must be treated as an animation candidate by default.

Examples include, but are not limited to:
- doors
- windows
- gates
- barriers
- flags
- fans
- signs
- lights and indicators
- bulbs
- screens
- shutters
- garage doors
- tree sway
- plant sway
- water movement
- smoke or vent output
- mechanical moving parts
- other real-world stateful or moving details

This applies to:
- major objects
- minor scene detail
- ambient detail
- utility elements
- decorative animated detail

Animation may be implemented through:
- sprite-sheet animation
- transform animation
- hierarchical animation
- shader animation
- procedural animation
- hybrid approaches

The selected method must suit the asset profile and visual fidelity requirements.

---

## 6. Asset profile system

Every asset must be governed by an approved asset profile.

Each asset profile defines:
- asset category
- gameplay role
- game identity
- visual style
- scale rules
- projection
- required orientations/directions
- animation requirements
- component hierarchy
- background/masking rules
- atlas requirements
- Godot integration rules
- validation rules
- performance requirements

Do not globally hardcode category-specific assumptions.

---

## 7. Universal visual quality and style-aware rendering

Each game uses an **approved art-style profile**. No particular artistic treatment is mandatory across all games. All styles must preserve silhouette clarity, reference fidelity, visual consistency, legibility, physical/world-scale relationships where applicable, and correct source-to-output traceability.

Pixel-art requirements (nearest sampling, pixel clusters, sharp pixel boundaries, restricted or curated palette, integer scaling) apply **only** when the active profile is pixel art or explicitly requests those effects. Do not impose pixelation, nearest filtering, limited colors, or a universal antialiasing ban on painted, illustrated, vector, or rendered graphics.

For any art style, avoid accidental blur, compression damage, unapproved color shifts, distorted geometry, haloing, and unintentional edge artifacts. Select resampling, smoothing, texture import, resolution, and shading rules according to the active style and target runtime.

## 8. Universal masking and background policy

All generated and delivered Game Arts PNG artwork must use an exact, fully opaque chroma pink background in all unused regions.

**Required mask color**
- HEX: `#FF00FF`
- RGB: `(255, 0, 255)`
- Alpha: `255`

Rules:
- never use transparent PNG backgrounds unless explicitly requested
- never substitute another mask color
- never use gradients or textured pink backgrounds
- never leave empty regions unfilled
- preserve clean asset boundaries suitable for color-key masking

This rule applies universally to:
- source sprite sheets
- components
- mockups exported as Game Arts PNGs
- UI artwork
- terrain-related PNGs
- scene assets
- effects sprites
- all future asset categories

---

## 9. Shared world geometry and scale — current orthogonal profile

### 9.1 Authoritative game-world coordinate model
All world assets in the same game use the same approved meter-based world coordinates, dimensions, origins, physical footprints and collision/interaction conventions. Distinguish **world coordinates**, **grid coordinates**, and **screen/rendered pixels**.

### 9.2 Current primary world profile (supersedes obsolete diamond settings)
- World map: **orthogonal square grid**.
- Logical terrain tile: **16 × 16 world meters**.
- Initial ground-tile canvas: **256 × 256 pixels**, corresponding to **16 px per world meter** in the two ground-plane axes at native scale.
- Ground mapping at zero camera rotation: `screen_x = 16 × world_x`, `screen_y = 16 × world_y` before camera and viewport transforms.
- Art depiction for above-ground objects: **elevated 3/4 top-down oblique, non-isometric** as an approved *art-style/camera profile*; do not rotate the world grid into 2:1 diamonds.
- Vertical projection and depiction of height: a **separately calibrated visual-height convention** fixed within a game profile, not the obsolete isometric `8 × sqrt(1.5)` coefficient.
- Existing 256 × 128 diamond terrain art is **legacy source artwork** requiring deliberate rework to the square grid; never stretch old diamond tiles to 256 × 256.

### 9.3 Placement precision
- Default construction snapping: **1 world meter**.
- Finer snapping is permitted by an approved profile.
- Movement, physics, and world positioning use continuous world coordinates.
- Logical terrain tile centers do not constrain all object placement.

### 9.4 World scale and adaptive asset size
Use real or intended physical dimensions and the agreed world pixel calibration. Never resize each asset to fill a fixed category frame. Default Godot Sprite2D scale is `(1,1)`; only explicit profile-controlled exceptions may change it.

### 9.5 Separate geometry contracts
Track independently: physical footprint, visual bounds, selection bounds, collision shape, elevation/height, operating/animation envelope, attachment positions, navigational clearance and sprite pivot. Do not infer world dimensions from PNG canvas bounds.

### 9.6 Grid compatibility gate
Before large-scale production, test a calibration scene containing terrain adjacency, an assortment of differently scaled structures and mobile assets, access geometry, sprite-ground origins, scene sorting and camera zoom. Keep geometry authoritative even if a stylized visual exaggeration is approved.

## 10. Adaptive frame sizing

There is no universal fixed frame size per asset category.

Frame dimensions must be determined from:
- world scale
- projection
- required directions
- animation extents
- component movement bounds
- required padding

Use variable-sized sprite cells or sheets as required.

Do not enlarge small assets or shrink large assets merely to fit a predetermined cell size.

Godot runtime default sprite scale is `(1, 1)` unless explicitly approved otherwise.

---

## 11. Master artwork locking

Every asset family must have approved master artwork.

Production sequence:
1. analyze references and profile
2. create mockup
3. obtain approval
4. decompose mockup
5. create production master
6. validate master
7. lock approved master
8. derive directions, states, animations, and components from the locked master

Do not independently redraw unchanged geometry for every variation if doing so changes identity or causes drift.

---

## 12. Directional artwork

Direction count is profile-dependent.

For directional assets:
- preserve scale, identity, materials, and silhouette logic
- preserve camera/projection consistency
- maintain stable pivots and attachment logic
- preserve asymmetrical details when applicable
- store documented direction order

Do not assume every asset needs eight directions.

However, when an approved profile requires eight directions, all required directional rules below become mandatory.

---

## 13. Universal modular component system

Any asset with independently movable, replaceable, interactive, or state-changing parts must be represented as a modular asset when appropriate.

### 13.1 Component discovery
Detect and record:
- static geometry
- independently moving parts
- parts with multiple visual states
- linked components
- repeated or nested moving parts
- stateful or interactive parts

### 13.2 Parent-child hierarchy
Each modular component must define:
- component ID
- parent ID
- parent attachment reference
- component type
- local pivot
- rest transform
- local attachment role
- state metadata
- animation references
- render layer / occlusion metadata

### 13.3 Static master + separate moving parts
Generate the static master once and separate independently moving parts when appropriate.

Do not rebake the full parent asset into every animated frame unless the chosen profile explicitly requires full-frame animation.

---

## 14. Animated attachments and nested component motion

Attachment points are not limited to static mount locations.  
An attachment may itself be animated.

The system must support:
- fixed attachment points
- animated attachment transforms
- nested moving attachments
- simultaneous parent and child animation
- hierarchical transform composition
- frame-based or keyframed attachment motion
- state-dependent attachment behavior

Attachment transforms may vary by:
- direction
- parent action
- state
- frame
- normalized time
- interpolation model

This means the system must support:

**Base → Animated Attachment → Animated Component → Animated Attachment → Animated Component**

for arbitrary validated hierarchy depth.

---

## 15. Direction-aware component attachment standard

For every multi-direction asset with independently moving or attached components, attachments must be aware of all required directions.

### 15.1 When base asset has 8 directions
If the parent/base asset has **8 facing directions**, then every visible independently moving component must also provide complete compatible visual coverage for those same 8 directions.

That means:
- the component must have direction-correct artwork or a validated direction-independent rendering method
- the component must have direction-specific or validated shared pivots
- the component must have direction-specific attachment placement
- the component must participate correctly in direction changes

### 15.2 Parent-local physical attachment
Each attachment must have a stable physical definition in parent-local world coordinates (meters).

### 15.3 Direction-specific measured anchors
For each required facing direction, store the measured pixel anchor corresponding to the physical attachment point.

### 15.4 Component pivots
Each component must define per-direction pivots and per-frame pivots when required.

### 15.5 Animated attachments
If the parent attachment is animated, store:
- per-frame measured transforms, or
- keyframed/interpolated transforms,
for each applicable direction and state.

### 15.6 Atomic direction switching
When the parent changes direction:
1. switch parent frame/direction
2. switch child direction
3. retrieve correct directional anchor
4. retrieve correct directional pivot
5. preserve active animation progress where applicable
6. apply correct render order and occlusion
7. update all related components atomically

No visible detachment is allowed.

### 15.7 Nested hierarchy support
Every child inherits the appropriate parent transforms, including animated attachment transforms.

---

## 16. Animation requirements

Every animation must define:
- animation ID
- applicable directions
- state mapping
- frame count or transform model
- timing / FPS
- loop behavior
- playback direction
- start/end states
- interaction with parent state
- component dependencies

Do not use a fixed frame count universally.

Use the required number of frames or animation method based on motion and profile.

---

## 17. Sprite sheets and atlas generation

Every multi-frame sprite sheet must have a matching measured JSON atlas.

### 17.1 Atlas content
Include applicable metadata such as:
- schema version
- asset ID
- component ID
- parent ID
- image filename
- frame rectangles
- frame count
- frame dimensions
- pivots
- trim offsets
- source canvas dimensions
- direction mapping
- animation metadata
- rest transforms
- named attachment anchors
- per-direction attachment coordinates
- animated attachment tracks where applicable
- render-layer metadata
- state metadata
- mask color
- validation status

### 17.2 Measured, not guessed
All atlas coordinates must be derived from the actual exported PNGs and validated.

---

## 18. Terrain, structures, scenes, and environmental continuity

Terrain and structural assets must follow the approved world-scale system and must be compatible with the game's physical layout.

Requirements include:
- coherent world placement
- correct relative size against nearby objects
- modular compatibility where applicable
- scene continuity
- correct road/path/building relationships
- visually credible access/clearance geometry
- preserved structural height under the approved projection

Terrain and environmental production must not ignore scene detail visible in approved mockups.

---

## 19. Godot integration

Generated artwork and metadata must be suitable for Godot 4 integration.

Use appropriate systems such as:
- Sprite2D
- AnimatedSprite2D
- SpriteFrames
- AnimationPlayer
- AnimationTree when needed
- TileMap / TileSet workflows
- AtlasTexture
- Node2D component hierarchies
- CollisionShape2D
- LightOccluder2D
- GPUParticles2D
- shaders / procedural systems where appropriate

Godot import/runtime systems must:
- apply chroma-pink masking
- reconstruct component hierarchies
- apply pivots and attachment transforms
- preserve direction/state synchronization
- support dynamic animated attachments
- preserve correct render ordering and occlusion

---

## 20. Validation and testing

An asset or scene is not production-ready until it passes validation.

Validation includes:
- visual fidelity to approved mockup
- consistency with locked master
- direction correctness
- component alignment correctness
- animated attachment correctness
- pivot correctness
- scale consistency
- masking correctness
- frame geometry correctness
- atlas correctness
- no clipping
- no jitter
- correct state behavior
- correct collision/interaction metadata where applicable
- correct render ordering
- Godot composed-scene validation
- performance suitability for intended usage

### 20.1 Visual regression
Compare production results against:
- approved mockup
- approved production master

Track and reject unapproved visual drift.

---

## 21. Delivery

Deliverables must be provided as individual files.

Do not package final Game Arts deliverables only as ZIP archives.

Deliver as applicable:
- PNG artwork
- sprite sheets
- atlas JSON- state metadata
- component hierarchy metadata
- optional Godot resource files
- validation/approval notes

---

## 22. Permanent master workflow

1. identify game, request, and asset profile
2. gather references
3. create mockup
4. obtain explicit approval
5. decompose approved mockup
6. build static and animated asset inventory
7. identify animation candidates
8. create production master
9. lock master
10. generate directions/states/components
11. generate animation sheets or alternative animation resources
12. generate measured atlas JSON
13. integrate and validate in Godot
14. perform visual regression and technical checks
15. deliver individual validated files

---

## 23. Master rule (retained from v6.9)

Game Arts is a universal, extensible, mockup-first, detail-aware, animation-aware, world-scale-consistent production system.

It must:
- respect approved mockups as detailed production references
- preserve all visible detail relevant to the final game art
- treat real-life moving/state-changing details as animation candidates by default
- support modular component animation with nested animated attachments
- require complete directional compatibility when a base asset has directional coverage
- use exact opaque `#FF00FF` masking
- generate one measured atlas JSON per sprite sheet
- validate all composed assets in Godot before approval

**Historical v6.9 rule retained; the current authoritative document is this consolidated v7.0 specification, including its newer art-style and world-geometry provisions.**


---

## 24. AI sprite production controls — mandatory v6.9

These controls apply to every AI-assisted 2D production task when relevant to its asset profile. They extend, rather than replace, the mockup approval and detailed decomposition gates in Sections 3–5. The AI model is responsible for visual ideation and controlled source art; deterministic asset tools own frame rectangles, exact dimensions, masking verification, metadata generation and validation. Never assert that a model-generated grid or metadata was measured or verified when it was not.

### 24.1 Reference-conditioned generation

- For new artwork, produce a mockup first and obtain explicit approval. Promote the **specific approved mockup revision** to the controlling visual reference. After decomposition, derive a locked production master.
- On subsequent generation or editing, provide the actual approved visual reference, relevant region crops, previous master directions and component source art to the generator when the tool supports image conditioning. A textual paraphrase alone is insufficient when approved reference imagery is available.
- Maintain stable IDs linking `source_mockup_id`, `mockup_revision`, `source_region`, `master_asset_id`, `master_revision`, original user references and derived artwork.
- Record which attributes are locked (silhouette, geometry, materials, palette, light direction, projected physical scale, attachment positions, static pixels), which may be edited, and why.
- Preserve small, meaningful details discovered in the approved mockup decomposition. Do not discard them merely to simplify AI generation.
- Distinguish observed reference facts from inferred, stylized, or newly invented details. When the generator cannot maintain a locked feature, repair the artwork or request re-approval for a material redesign.

### 24.2 Controlled directional masters

- Determine directions dynamically from the approved asset profile; do not assign eight directions to all assets.
- For a directional asset, first build and visually validate a coherent turnaround from the shared reference and consistent geometric/world-scale model. Lock each approved directional master before making animations.
- Each view must retain identity, dimensions, projection, pixel density, lighting logic, named attachment points, contact origins, and intentional asymmetries. Do not independently invent a new version of the asset for each facing.
- Reflection/mirroring is permitted only if meaningful asymmetries and direction-specific features remain correct and the result passes validation.
- For any parent with an eight-direction profile, every visible moving component must have validated matching eight-direction appearance and anchors. Transform/procedural equivalents are allowed only if they are direction-correct.
- Record master image revision, direction mapping, frame-local pivots, measured direction-specific anchors and per-direction occlusion behavior.
- For complex shapes, a 3D or geometric blockout may be used as a temporary consistency aid without changing the final 2D art requirements.

### 24.3 Key-pose-first animation generation

- Plan animation intent and physical constraints before generating intermediary images. Choose meaningful key poses (typically initial, major transition/peak, and final), plus appropriate breakdown or cyclic poses where necessary.
- Lock the component's appearance, pivot, attachments, and relevant unchanged pixels across poses.
- Generate intermediate frames by controlled edits, frame interpolation followed by review, deterministic local transforms, hand pixel editing, or other validated methods. Do not generate unrelated full-scene redraws for each frame.
- Frame count, frame rate, durations, looping and state transitions are profile-dependent; never impose a global six-frame rule. Honor more specific approved profiles where applicable.
- Moving attachment anchors have their own track: direction, parent action, logical state, time/frame, position, rotation, optional scale and interpolation. Child components can animate at the same time as their parent mounts.
- On direction changes, transfer normalized logical progress and switch the full parent-child visual/attachment state atomically. Validate physically plausible motion and correct composition at sampled times, not merely at key poses.

### 24.4 Pixel cleanup and exact mask gate

- Inspect exported artwork for unexpected antialiasing, blended edges, mixed pixel densities, stray pixels, jagged broken contours, palette drift, inconsistent highlights and changed static pixels.
- Use selective pixel-level repair. Do not apply destructive blanket quantization, sharpening or outline filters that erase intentional material detail.
- All delivered Game Arts PNGs, including extracted sprite frames, sprite sheets, moving parts, icons and effects, must retain fully opaque source pixels (`alpha=255`) and **exact** solid `#FF00FF` where there is no art. No delivered alpha-transparent derivatives without explicit user exception.
- Detect and fix near-magenta contamination at boundaries. Do not permit mask-color pixels to be confused with intended visible artwork.
- Verify the final source PNG's encoding, dimensions and mask after every resampling, sheet assembly or conversion step; no unobserved image-processing success claims.

### 24.5 Deterministic sprite-sheet assembly and measured atlas

- Produce or extract approved individual frames first. Verify count, direction/action mapping, bounds, source cell dimensions, pivots and unchanged-pixel contract.
- Assemble the final PNG using a deterministic frame-order/layout specification, documented padding/spacing, appropriate pixel-exact operations and background fill `#FF00FF` with alpha 255.
- Compute the companion atlas JSON **from the actual exported PNG** and the frame placement manifest, not from prompt assumptions. Each sheet has its own atlas; standalone single images may use appropriate asset metadata.
- Record image size, frame rectangles, untrimmed source sizes, optional trim offsets, measured pivots, direction/state/action/frame mapping, duration, palette/mask policy and validation state.
- For modular assets, include physical parent-local mount points, measured pixel anchors for every applicable direction, per-frame component pivots, rest transforms, time-varying attachment tracks, nested hierarchy, draw order/occlusion and state dependencies.
- Validate that frame rectangles are within the PNG, frame count/layout match, every required facing/action exists, and resulting composites are correctly positioned. JSON syntax validation alone is insufficient.
- Preserve a separate approved source/master and optionally create optimized runtime resources without altering the delivered opaque-pink originals.

### 24.6 Animation regression and composed-art tests

- Compare each produced frame with the locked source for permitted changed areas, silhouette changes, palette shifts, missing details, accidental repeats and incorrect movement.
- Evaluate pivot stability, attachment drift, contact-point changes, clipping, range-of-motion constraints and unwanted jumps between adjacent frames and at loop wraparound.
- Test every applicable direction/action/state/frame combination for visible component correctness. Test direction changes while parent and nested children are actively moving, keeping normalized playback time consistent.
- Validate scene composition against the **approved mockup**: inventory coverage, object placement, surface detail, material treatment, geometry, animation candidate coverage and occlusion.
- In Godot, verify chroma-key compositing, native-scale rendering, scene sorting, interaction/collision/navigation changes, lighting effects where relevant, and representative runtime performance.
- Classify validation findings as passed, failed, untested or not applicable. Do not mark a package production-ready when applicable failures or untested critical requirements remain.

### 24.7 Generation provenance and reproducibility

- Record the AI provider/tool, model identifier or version when available, generation date, source IDs, conditioning images, edit mode, prompt/configuration version, seed when exposed, output hashes, human corrections and approval decisions.
- Preserve rights/usage notes for supplied references and generated artwork; do not assume approved visual appearance establishes commercial usage rights. Record unresolved permissions for follow-up.
- Keep one canonical asset manifest with immutable IDs and explicit revision links for the mockup, blueprint, locked master, individual frames, assembled sheets, atlases and imported Godot resources.
- Re-running the deterministic assembly and metadata stages with unchanged approved inputs must produce equivalent frame coordinates, mappings and attachment results. Treat nondeterministic image generation as a separately versioned step.
- Changing the approved art profile, geometry, projection, primary identity or animation behavior requires a documented impact review and renewed visual approval when the change is material.

## 25. Unified AI-generation contract and handoffs

The mockup blueprint is the controlling handoff between approved concept art and the generation pipeline. Every extracted asset should have a structured contract, with relevant fields such as:

- `asset_id`, `game_id`, `source_mockup_id`, `mockup_revision`, `source_region`
- `art_profile_id`, `art_profile_version`, `world_scale_profile_id`, `coordinate_system`
- `observed_details`, `inferred_details`, `required_details`, `material_texture_spec`
- `master_asset_id`, `master_revision`, `locked_features`, `permitted_edits`
- `required_directions`, `required_states`, `animation_candidates`, `selected_animation_methods`
- `component_hierarchy`, `named_anchors`, `moving_attachment_tracks`, `collision_references`
- `frame_manifest`, `sprite_sheet_files`, `atlas_json_files`, `validation_results`
- `source_rights_status`, `generation_provenance`, `approval_status`

The manifest must not claim unavailable measurements, visible details or provenance facts as verified. Use explicit `unknown`/`estimated` values when justified. Validate blueprint coverage before generating large asset batches.

## 26. Historical AI-production workflow from v6.9 (superseded by Section 28)

1. Identify the game, asset request, technical requirements and approved profile.
2. Collect source references and produce an initial visual mockup.
3. Obtain explicit approval of the exact mockup revision, or reuse a previously approved identifiable mockup.
4. Perform exhaustive detailed mockup decomposition: geometry, textures, components, visible micro-detail, spatial relationships, state/animation candidates and intended resources.
5. Build and validate the unified asset blueprint and static/animated inventory; flag observations versus inferences and gaps requiring review.
6. Use actual approved reference imagery for controlled generation; create, validate and lock the production master.
7. Produce coherent, approved directional masters where the profile requires orientations, including direction-correct child art and measured mounts.
8. Plan animation key poses, nested moving attachments, timing and state transitions before creating intermediary frames.
9. Generate or deterministically transform/edit individual frames while preserving identity, scale, unchanged regions and attachment alignment.
10. Run pixel cleanup and exact opaque-pink mask validation.
11. Assemble each sprite sheet deterministically, then derive and validate its companion atlas JSON from actual exported geometry.
12. Build corresponding Godot resources and complete component hierarchies where applicable.
13. Run automatic animation regression, mockup-coverage comparisons, attachment/atlas checks and composed Godot tests.
14. Record provenance, rights notes, revisions, approvals and pass/fail/untested validation evidence.
15. Deliver **individual** PNG and matching atlas JSON files plus relevant metadata. **Never deliver ZIP archives** for Game Arts packages.

**v6.9 master rule:** AI supplies controlled reference-conditioned visual content. Approved mockups determine the full scene-detail contract. Deterministic tools supply exact geometry, frame packing, metadata and verifiable compositing. Never bypass mockup approval, global opaque `#FF00FF` masking, measured atlases, dynamic moving attachments, required directional completeness or Godot validation.

---

## 27. Universal 2D graphics framework — v7.0

This section is authoritative wherever prior clauses assume a specific graphical style. It extends the existing mockup, inventory, component, atlas, and validation contracts without weakening them.

### 27.1 Three-layer architecture

**Layer A — Universal core:** Applies to every game and graphical style.
- Mockup-first approval and locked visual references.
- Comprehensive mockup decomposition: geometry, textures, materials, features, vegetation, details, UI regions, and animated/stateful candidates.
- A structured blueprint linking each visible meaningful feature to an approved asset, layer, system, or explicit omission decision.
- Reference-conditioned, identity-preserving generation and locked production masters.
- Independent and nested moving components; animated anchors and direction-aware alignment wherever needed.
- Controlled poses and animation tracks; deterministic output assembly.
- Exact opaque #FF00FF masking for **all delivered Game Arts PNGs**, with style-aware edge handling.
- Measured JSON atlas for every sprite sheet, correct pivots, frame timing and dynamic attachments.
- Godot composition, visual regression, technical validation, provenance and individually delivered files; no ZIPs.

**Layer B — Art-style profile:** Defines how pixels, textures, curves, edges, lighting, palettes, antialiasing, resampling and resolution are authored and rendered.

**Layer C — Asset profile:** Defines what is being created, world versus UI coordinates, projection, dimensions, directions, components, actions/states, output topology and engine needs. These properties are determined by the brief and mockup, not hardcoded category-specific rules.

An asset can combine multiple styles only under an expressly approved hybrid style profile; record which rules control each layer.

### 27.2 Required art-style profile schema

Each art-style profile defines:
- `style_id`, `version`, `target_game`, approved references and visual examples.
- Shape language, stroke/outline conventions, texture and material treatment.
- Color system, highlights/shadows, lighting model and compositing mode.
- Nominal resolution, screen density, detail density and minimum legible size.
- Edge policy: pixel-sharp or smoothed; permitted antialiasing; edge matte/halo constraints.
- Rasterization method and scaling policy (including optional vector/3D intermediate sources).
- Texture filtering, mipmaps, compression and zoom behavior appropriate to final Godot rendering.
- Animation aesthetic, frame-rate/timing principles and permissible transform or mesh deformation.
- Validation criteria and tolerances specific to the profile.
- Exact opaque chroma-pink export contract, without any alpha-transparent deliverables unless user explicitly overrides the global requirement.

### 27.3 Supported styles (open, not exhaustive)

**Pixel art:** Deliberate pixel clusters, consistent pixel size, controlled palette/outline patterns, native-scale review, nearest filtering by default and integer display scaling where appropriate.

**Hand-painted or painterly:** Continuous tones, gradients, brush texture and appropriate soft antialiasing; smooth sampling where appropriate. Do not apply palette quantization or nearest-neighbor defaults mechanically.

**Hand-drawn / illustrated / cartoon:** Intentional outlines and shape rhythm, expressive posing, clean antialiasing where the profile requires it, and consistent line weights across asset sizes.

**Vector / flat:** Editable source geometry where available, stable strokes and shapes, deterministic rasterization at approved export resolution; the deliverable PNG still uses exact opaque pink unused regions.

**3D-rendered-to-2D:** The 3D setup can serve as a consistency reference for dimensions, perspective, lights and multi-view turnarounds; export raster frames that match the game art profile. This does not require the game itself to use 3D.

**Custom or hybrid:** Specify deviations explicitly and test that the result remains coherent with the approved game art direction.

These names are examples of styles, **not** an exhaustive list or forced choice.

### 27.4 Keep the world grid independent of visual style

The current approved game profile uses an orthogonal square grid and oblique non-isometric *object artwork*. A painterly asset does not change the tile footprint; pixel art does not automatically imply diamond tiles. Only an explicitly versioned world profile change can revise map geometry.

### 27.5 Style-specific edge handling under mandatory pink masking

All final Game Arts PNGs use `#FF00FF` RGB `(255,0,255)` with alpha `255` for background/unused pixels, in every art style. This does not mean soft styles must have jagged artwork.

- Preserve correct smooth/antialiased object *interior* visual treatment as the style requires.
- Avoid baking chroma-pink blend fringes into visible edge colors; use a source-layer mask, controlled matte, or a separate edge-coverage representation within the authoring/import pipeline.
- If the exact opaque pink export cannot encode soft fractional edge coverage by itself, retain that coverage in **separate non-PNG metadata or authorized intermediate working format**, or explicitly accept a hard-edge output for that asset. Do not silently claim exact color-key extraction recovers soft alpha from a single opaque pink PNG.
- Godot must apply the agreed color-key or other approved reconstruction process while leaving source/delivered PNGs unchanged.
- Audit fully opaque images, precise key pixels and halo artifacts at intended runtime scale.

### 27.6 Style-dependent animation and composition

All moving or state-changing details identified in the approved mockup enter an animation inventory. Choose sprite frames, bone/transform rigs, shader effects, procedural motion or hybrids depending on appearance and motion constraints. In all cases, the design must retain full required directional coverage, parent/child attachment correctness and synchronized animated anchor transforms.

Use key poses as needed; determine frame counts and update rates from the active animation profile, not from a universal fixed number. For authored sprite sheets, assemble frames deterministically and generate a measured JSON atlas from final image geometry.

### 27.7 Universal mockup blueprint and coverage audit

An approved mockup becomes a **detailed** production blueprint. Every meaningful visible item should have:
- persistent region/element ID and approved mockup source region;
- directly observed visual characteristics versus inferred properties;
- geometry/shape, material, texture, color, lighting and scale relationships;
- owning layer, asset/module ID, anchors and relationships;
- static or animated classification, applicable directions/actions/states and suitable implementation approach;
- output asset IDs and acceptance checks.

A completeness audit must report missing detail, inferred geometry, rejected/in-scope animation candidates, unresolved technical assumptions and any deliberate omissions. Do not silently simplify detailed scenes.

### 27.8 AI-generated visual consistency

Use the approved mockup crop and the exact locked master as visual conditioning wherever supported. Establish directional or state masters before generating derivative frames. Prefer controlled key poses and deterministic component transforms where the motion can be represented correctly. Preserve unchanged visual regions; validate against actual references. Never treat a plausible but independently generated pose as an automatically accepted continuation.

### 27.9 Universal Godot export contracts

The importer must choose filter, compression, mipmap, rendering material, shader, layout, z-order, component hierarchy and animation method according to **both** style and asset profile.

Examples: nearest for approved pixel art, linear when approved for painted sprites, appropriately scaled vector rasterizations, frame sequences for authored illustrated motion. Test final rendering at target zoom and UI scale.

All generated multi-frame PNGs require matching measured atlas JSON. Standalone PNGs require metadata where needed, not an invented multi-frame atlas.

### 27.10 Style-aware tests and version control

Maintain automated universal checks for image dimensions, atlas rectangles, exact pink mask pixels, per-frame alignment, provenance, nested animated attachments, and Godot import. Add style-appropriate checks for pixel density, stroke integrity, gradient banding, antialiasing/matte halos, texture fidelity, responsive UI readability, visual coherence, and camera zoom.

Record style ID/version and asset profile ID/version for every output. Changes to artistic treatment after mockup approval require a mockup revision and renewed approval.

### 27.11 Skill architecture

Provide one master orchestrator and selectively loaded specialized skills:
- mockup composition/decomposition and coverage validation;
- scene and surface analysis;
- structural geometry and component analysis;
- screen-space UI analysis;
- animation-state and attachment analysis;
- reference-controlled visual generation;
- style-specific cleanup;
- deterministic sheet/atlas assembly;
- final Godot validation.

Skills read the canonical core and selected art/asset profiles rather than copying policy blocks that can drift apart.

### 27.12 Final v7.0 precedence

1. Explicit user-approved exceptions for the current request.
2. Active target game's world/geometry profile.
3. Approved art-style and asset profiles.
4. Universal v7.0 core.
5. Older historical versions only where not contradicted.

**No style profile may silently cancel the global exact opaque pink, mockup approval, measured atlas, or validation requirements.**

---

## 28. Canonical production gate

1. Establish game profile, current world geometry, and art-style profile.
2. Generate reviewable mockup(s); obtain explicit approval.
3. Lock accepted references and extract a comprehensive mockup blueprint.
4. Perform completeness audit, inventory static assets and every real-world animation candidate.
5. Generate reference-conditioned, measured native-scale master art and obtain any required master signoff.
6. Generate approved directional masters and modular component masters; preserve identity and correct attachments.
7. Plan key poses/states, animate separate components and moving attachment tracks, maintaining directional completeness.
8. Clean up artwork according to the art-style profile; enforce exact opaque pink masking.
9. Assemble frames deterministically; export individual PNGs and measured per-sheet JSON atlases.
10. Generate optional Godot scenes/resources and verify masking, layering, states, world scale, interactivity and nested attachments.
11. Run universal plus style-specific regression and quality gates.
12. Record approved versions/provenance and deliver individual files without ZIP archives.

**The approved mockup is the visual source of truth, the game profile is the geometry source of truth, and the measured PNG/atlas pair is the sprite-export source of truth.**



---

## 29. Operational art-style profiles — v7.1

Art-style profiles are selected **per game and visual layer** before mockup generation. They define render rules but never change the universal masking, approval, attachment, sheet/atlas, or file-delivery contracts. The following initial templates are editable profiles, not hardcoded object classes.

| Profile | Edge/render policy | Palette/material policy | Review criteria | Godot default to validate |
|---|---|---|---|---|
| `pixel_art` | Deliberate pixel clusters, sharp edges; avoid unintended resampling | Controlled pixel-scale highlights, readable clusters | Pixel-scale consistency at native resolution, no halo pixels | Nearest; integer viewport scaling when appropriate |
| `painted_2d` | Intentional smooth edges, brushed gradients | Consistent brushwork, lighting and material detail | Edge matte, color continuity, texture fidelity | Linear sampling where appropriate; test zoom/mipmaps |
| `illustrated_2d` | Consistent linework, controlled antialiasing | Stable line weight and shape language | Silhouette, stroke consistency, pose clarity | Style-specific filter and compression |
| `vector_flat` | Shape/stroke geometry is authoritative; rasterize deterministically | Flat or controlled graduated fills | Path continuity, stroke ratios, export-scale readability | Rasterize at intended source scale, then validate |
| `rendered_2d` | Approved camera/lighting render-to-sprite | Consistent 3D proxy and shading | Stable view angles, geometry, rigged pose and projected size | Appropriate import filtering and frame resources |
| `custom` | Declared explicitly by art director | Defined by approved mockup/style guide | Tests defined in custom profile | Validated per profile |

Every profile must specify `profile_id`, `version`, `reference_ids`, `render_resolution`, `edge_policy`, `palette_policy`, `lighting_policy`, `scaling_policy`, `filtering_policy`, `animation_treatment`, and `acceptance_tests`. Missing fields are explicitly marked `unknown`, not silently assigned incompatible defaults.

## 30. Canonical mockup blueprint handoff

After visual approval but **before any production sprite generation**, create a machine-readable blueprint. The blueprint must provide full traceability from mockup region to asset output. Suggested JSON contract (illustrative identifiers; actual element and geometry records must be measured or explicitly labeled as inferred):

```json
{
  "schema_version": "1.0",
  "game_id": "game_id",
  "mockup": {
    "id": "mockup_id",
    "revision": 1,
    "approval": "approved",
    "reference_image": "approved_mockup.png",
    "reference_hash": "sha256-of-approved-file",
    "native_resolution_px": [1024, 768]
  },
  "style_profile": {"id": "pixel_art", "version": "1.0"},
  "world_profile": {"id": "world_profile_id", "version": "1.0"},
  "elements": [
    {
      "id": "element_001",
      "reference_region_px": [0, 0, 100, 100],
      "visibility": "directly_observed",
      "geometry": {"measurement_status": "pending_measurement"},
      "materials": [],
      "surface_details": [],
      "relationships": [],
      "animation_candidates": [],
      "expected_asset_ids": [],
      "coverage_status": "pending"
    }
  ],
  "unresolved_assumptions": [],
  "coverage_audit": {"status": "pending", "unaccounted_regions": []}
}
```

A mockup decomposition must inventory meaningful **small detail as well as large objects**: boundaries, joins, trims, textures, repeated motifs, light sources, environmental materials, interactive regions, and possible motion. Regions should not be omitted merely because the object is decorative. For a visible detail that is intentionally not a separate asset, assign it to a parent material/layer or report an explicit exclusion rationale.

Every inferred hidden dimension or behavior must be labeled `inferred`, with evidence, confidence, and review status. The blueprint must not claim an inferred object feature was directly visible.

### Blueprint readiness gate

A blueprint is ready only when: (1) the mockup revision is explicitly approved, (2) each meaningful visible region has an owner, (3) all visible objects and materials have production assignments, (4) motion/state candidates are inventoried, (5) directional and attachment needs are documented, (6) world scale/projection is consistent, and (7) unresolved assumptions are flagged rather than silently filled.

## 31. Reference-controlled AI generation contract

For every production asset, record:

- The immutable approved mockup ID/revision and the relevant crop/region.
- The approved locked art master ID/hash and the direction master IDs where applicable.
- The active style and asset profiles with version numbers.
- Intended physical dimensions and source native scale when the asset occupies the world.
- A list of **immutable features** (geometry, component identity, static pixels, colors or other properties) that must not drift across views/actions.
- Permitted differences (pose, active state, orientation, component transform, light state, or approved visual changes).
- Generation tool/model version, prompt/configuration identifier, source references, seed if exposed, and manual cleanup history.

When reference-conditioned generation is supported, use the actual reference artwork or cropped master. If the generator cannot condition on images, identify that limitation and require stronger manual/visual review. Do not assume identical text prompts produce matching geometry.

### Key-pose workflow

Plan start/end and meaningful intermediate poses for applicable motions, including cycle closure for loops. Confirm mechanical or visual constraints before filling in-betweens. Preserve unchanged regions. Prefer deterministic transforms for rigid, correctly projected movements and authored frames when the visual shape must change (such as perspective-dependent articulation). Frame counts are determined by the animation profile.

## 32. Deterministic frame, atlas and attachment contract

1. Create or edit individual frames using the locked master and key poses.
2. Clean frames according to the active style; exact opaque `#FF00FF` in every unused region, all PNG alpha channels 255.
3. Determine maximum **projected** frame extents, including state transitions, directional changes, nested component movement, attachments, and safe padding.
4. Place frames programmatically into cells with a documented rectangle origin, row/column order, trim convention, and stable pivots. Do not rely on an AI image's apparent grid to establish pixel coordinates.
5. After PNG export, measure actual sheet dimensions and frame regions and emit matching **per-sheet** JSON atlases. Reject any rectangle outside the exported image.
6. For each modular part, include parent/child IDs, parent-local attachment in world units, **measured per-direction image anchors**, per-direction and per-frame pivots, trim offsets, rest transforms, animated attachment tracks, coordinate spaces and draw/occlusion order.
7. For nested motion, preserve animation time and direction coherently while composing transforms throughout the hierarchy, including simultaneous parent/child motion.
8. For every supported parent facing, provide compatible moving-component artwork or a validated direction-independent method that reproduces correct appearance. Never silently borrow an incorrect facing.
9. Output original sprite sheets in exact opaque pink only, not alpha-transparent derivatives, unless explicitly requested.

## 33. Quality gates: objective checks versus visual acceptance

**Automated structural checks:** PNG mode and mask, dimensions, boundaries, sheet frame count and rectangles, atlas completeness, unique IDs, correct direction coverage, anchor schema, parent-child graph validity, no missing referenced files, provenance, hashes, and no ZIP delivery.

**Automated pixel/motion checks:** unexpected modifications to locked static regions; repeated frames in actions requiring motion; clipping; pivot drift; loop boundary discontinuity; direction-dependent anchor jumps; full nested transform attachment error at relevant sampled times; palette/style-specific edge defects.

**Visual checks:** similarity to approved mockup and locked master; complete micro-detail coverage; coherent texture/material treatment; native-scale readability; expected movement and occlusion; correct world-size relationships; scene composition at intended camera distance. Automated scores must not be treated as proof of artistic fidelity.

**Godot checks:** runtime masking and painterly-edge treatment where applicable; atlas import and SpriteFrames/AnimationPlayer correctness; world geometry, collision/selection, dynamic lighting and occlusion, nested attachments and active direction changes; memory and camera-zoom behavior. Do not claim an in-engine test passed unless that test was actually run and recorded.

An asset with failed required checks is `needs_revision`, never `game_ready`. A passed schema check is not evidence that Godot integration or visual review succeeded.

## 34. Versioned delivery and governance

The canonical deliverable remains one **master specification**, with art-style profiles and machine-readable asset blueprints created per actual project/request. Do not create competing policy documents by default.

At production time, the asset package must include individually linked approved source artwork, each PNG sprite sheet with its matching atlas JSON, any required component/animation state metadata, and an honest test report. No ZIP archives. Retain mockup/revision references and provenance for later regeneration.

**v7.1 extension:** The seven AI-specific practices—reference-conditioned generation, controlled directional masters, key-pose animation, style-aware cleanup, deterministic sheet assembly, animation regression testing, and generation provenance—are mandatory where applicable. They operate across all art styles; pixel-only filtering and palette rules apply only to the pixel-art profile.

---

# GAME ARTS v7.2 — UNIVERSAL MULTI-SCOPE MOCKUP ANALYSIS

## 29. Mockup scope classification (mandatory)

A mockup may describe an **entire world**, a **scene/level**, an **individual asset or character**, a **UI screen or user flow**, or a **mixed composition**. The agent MUST classify scope before attempting decomposition. A mockup is not presumed to be a scene or a sprite sheet.

Supported scope codes are `world`, `scene`, `asset`, `character`, `ui_screen`, `ui_flow`, and `mixed`. These are processing modes, not a closed set of game-asset types; custom scope definitions may extend the schema.

The output must identify:
- `mockup_id`, `mockup_revision`, source image(s), approval state and approved visual reference.
- `scope`, `subscopes`, game and art profiles, source dimensions, and evidence provenance.
- Visible regions and their relationships; levels of abstraction and confidence.
- What is directly visible versus inferred, specified by the user, or unknown.
- Scene/asset dependencies and intended production granularity.
- A detailed animation candidate inventory, including ambient motion and independent component animation where meaningful.
- Explicit uncovered areas and intentionally excluded details with reasons.

**Approval prerequisite:** creation of final production art still requires explicit approval of the mockup revision. An analysis preview before approval must be labeled provisional.

## 30. Scope-dependent decomposition strategies

### 30.1 Whole-world or world-map mockup

Treat the input as a **world planning reference**, not a single huge sprite image. Identify:
- Regions, zones, biome/material boundaries, road/path/utility networks, landmarks and spatial hierarchy.
- Grid/world coordinate convention, terrain composition, boundary/adjacency constraints, repeated modular assets, world scale and density.
- Global palette, lighting/season/time assumptions, foreground/background organization and level of detail.
- Which areas require nested scene mockups before production.
- World streaming/chunking, runtime placement and logical layers where relevant.
- Tile/transition inventories and shared materials; do not infer exact terrain assets solely from a low-detail map.
- Ambient animation candidates and environment-state variants.

**Decomposition recursion:** `world → regions → scenes → assets → components → animations`. Use nested blueprints with parent references. Avoid fabricating subpixel/architectural details hidden by the scale of a world map.

### 30.2 Scene or level mockup

Capture complete composition and usable detail:
- Camera, framing, world projection, layout, paths, surfaces, terrain transitions, boundaries and entrances.
- Structures, vegetation, props, effects, lighting, signs and all meaningful small details.
- Material/texture samples, pattern repeats, relative scale, object spacing, elevation and occlusion.
- Layering, modular/repeated pieces, tile adjacency and interaction flows.
- Dynamic or state-changing elements including ambient animation candidates.
- Asset IDs, dependencies and production assignment for all meaningful visual regions.

Separate **scene-wide context** from individual reusable assets. Validate reconstruction against the approved scene mockup.

### 30.3 Individual asset mockup

Capture silhouette, dimensions, topology, surfaces/materials, palette, projection, required directions, states and composition of fixed and movable parts. Identify all visible features and physical/visual attachment points. Require locked reference-conditioned master art, controlled directional views and component animation where applicable.

### 30.4 Character / agent mockup

Capture identity, proportions, silhouette, distinctive features, costume/surface layers, palette, facial/expressive or mechanism states as applicable, equipment and nested attachments, ground/feet pivot, collision approximation and gameplay action requirements. Plan directional turnaround and key poses from the approved design. Never independently redraw identity across frames. The word “character” does not by itself imply an organic or living entity.

### 30.5 UI screen mockup

Capture screen and viewport sizes, responsive layout rules, hierarchy, components, alignment, padding/spacing, typography, iconography, accessibility/readability, theme tokens, interaction states, navigation and animation candidates. Distinguish **raster art exports** from controls/text that should be rendered natively in the UI framework. UI uses screen-space units, not the world terrain scale. Generate UI state/art atlases only when actually necessary.

### 30.6 UI flow or multi-screen mockup

Capture each screen as a nested `ui_screen` blueprint plus screen-to-screen transitions, interactive states, navigation, overlays, loading/error/empty states and shared components. Do not merge multiple screens into one arbitrary sprite atlas.

### 30.7 Mixed mockup

Classify regions independently and dispatch each to the correct specialist analyzer. Preserve common visual constraints and record cross-region relationships, e.g. a scene with a screen-space HUD. One parent blueprint references child blueprints rather than flattening all content to one coordinate system.

## 31. Universal blueprint and evidence contract

Every analyzer contributes to a single compatible blueprint schema. Each element requires as applicable:
- Stable `element_id`, `scope`, `parent_id`, `source_region` / polygon and source reference.
- `observed_details`: visible silhouette, geometry, palette, material, texture, features, edge/pattern repetition.
- `relationships`: parent/child, spatial, structural, tile adjacency, occlusion and navigation.
- `coordinate_system`: image pixels, viewport, world meters or component-local; no silent mixing.
- `dimensions`: measured only when truly known; otherwise estimated with explicit uncertainty.
- `asset_strategy`: standalone, shared material, tileset, authored sprite, vector source, engine UI, shader/procedural or composition.
- `motion_candidates`: any potentially movable/state-changing detail, including minor ambient components, with states, actions and recommended implementation.
- `confidence` plus `evidence_status`: `observed`, `user_specified`, `inferred`, or `unknown`.
- `outputs`, dependencies, approvals, and acceptance checks.

Create separate nested blueprints when a world or large scene cannot reasonably be described at a single level of detail. Track each blueprint's `parent_blueprint_id` and `child_blueprint_ids`.

A **coverage audit** must associate every meaningful visible region/detail with an asset, layer, texture, interface component, animation candidate, deliberate exclusion, or unresolved question. Do not silently drop minor visible details.

## 32. Animated-component completeness and representation

Every real-world visibly movable, state-changing, illuminated, cycling, or deforming feature is an **animation candidate** by default, not necessarily a mandate to generate redundant image frames. The blueprint must record the proposed states and technique.

Use the most faithful approach: separate sprite frames, authored key poses, transform rigs, shaders, procedural motion or hybrids. When a profile explicitly requires a directional sprite sheet, provide that sheet and measured matching JSON. Preserve complete directional coverage for every visible moving component when its parent requires those directions. Anchors may animate as a function of direction, parent action, state and normalized time; nested children must inherit compounded transforms.

Static/animated decisions, proposed omissions and alternatives must be reviewable. A production asset may be declared complete only when its required movement and states are implemented or deliberately waived by the approved profile/user.

## 33. Style-aware analysis and technical export

Different mockup scopes may use different coordinate spaces, but each art-style profile controls drawing technique, texture handling, color treatment, edge quality, antialiasing and scaling. Do not apply pixel-art constraints to painted/vector styles.

Every **delivered Game Arts PNG**, including applicable mockup previews and sprite sheets, uses the exact opaque `#FF00FF` color in unused pixels. No alpha-transparent PNG derivatives without explicit approval. For soft edges, maintain coverage information in an appropriate authoring intermediary or separate metadata and test halo-free color-key rendering in Godot.

The active geometry profile remains the approved **orthogonal square world map**: 16×16 world-meter terrain tiles, initially 256×256-pixel ground tiles, nominal 16 px/m, 1 m default snap and continuous world coordinates. Do not resurrect the deprecated 256×128 diamond projection.

Every final sprite sheet has its own measured JSON atlas; an overview mockup does not itself require an atlas unless exported as an actual sprite sheet. Individual files are delivered without ZIP archives.

## 34. Specialist skill routing and validation gates

The universal mockup orchestrator reads the approved reference and selects specialized analyzers based on **scope and visible evidence**, not a hardcoded list of expected objects:
- World-scale spatial/topology analyst.
- Scene and surface/detail analyst.
- Asset, geometry and component analyst.
- Character/agent design analyst.
- UI screen/flow analyst.
- Motion/state and animated-attachment analyst.
- Style/material fidelity analyst.
- Blueprint completeness and provenance validator.

A specialist receives only the relevant approved mockup region plus the master and active profiles. Specialists return compatible element records to one parent blueprint. Conflicting interpretations require explicit reconciliation; never silently overwrite an observed detail.

**Required gates:** mockup approval → scope identification → detailed decomposition → evidence/coverage audit → blueprint review for material inferences → locked master → controlled production → deterministic atlas/metadata → Godot assembled validation → individual delivery.

## 35. Acceptance criteria for the v7.2 analyzer

Reject or mark incomplete any blueprint with:
- Unclassified mockup scope or wrong coordinate system.
- Missing source reference / approval status.
- Meaningful visible elements silently omitted.
- Inferences presented as observed facts.
- No animation inventory where moving/stateful elements are present.
- Missing sub-blueprints for necessary world/scene/asset drill-down.
- Missing source-to-production traceability.
- Unsatisfied inherited masking, world-scale, atlas, attachment or Godot requirements.

The analyzer may return `needs_mockup_detail` if image resolution cannot support reliable extraction; it must not hallucinate fine geometry. The approved composition remains authoritative until the user explicitly approves material changes.

**Final v7.2 principle:** `Identify mockup scope → analyze every meaningful visible detail at that scope → descend into nested blueprints as needed → plan static and animated production assets → validate reconstruction against the approved mockup.`\n
---

# Game Arts v7.3 — Asset and Mockup Lifecycle

**Status:** Mandatory. This is a universal lifecycle policy for every Game Arts project and every supported 2D visual style. Preserve all existing v7.2 mockup-first, decomposition, scale, animation, attachments, opaque #FF00FF PNG, atlas, validation and no-ZIP requirements.

## Lifecycle storage

Use these directories inside the **actual game repository**, never the shared GameArtsSkills repository:

```text
.gamearts/
  project.json
  instructions/
  outputs/
    mockups/
      generated/
      approved/
      revoked/
    assets/
      generated/
      approved/
      revoked/
    manifests/
      assets.json
      mockups.json
```

The top-level split distinguishes review/composition mockups from reusable production art. These are **distinct but linked lifecycles**. Optional deeper directories may be determined dynamically by scene, region, art style or asset family; do not hardcode particular asset types. Do not use a single undifferentiated `generated` folder that mixes all drafts.

### Mockup lifecycle (mandatory prerequisite)

- New visual concepts are stored in `outputs/mockups/generated/`. Each revision is a separate immutable candidate, not an overwrite of an earlier image.
- The user must explicitly approve a specific mockup revision before it is promoted to `outputs/mockups/approved/`.
- Rejected and superseded mockups move to `outputs/mockups/revoked/`, retaining metadata, preview and rejection/supersession reasons.
- An approved mockup has a stable `mockup_id`, revision, source path, approval record, content hash if available, and optional linked blueprint.
- Approved mockups are the **visual reference source of truth**. Production generation must link to the correct approved mockup revision; if there is no approved reference for new art, final production must not begin.
- If the accepted concept is modified materially, a new mockup revision requires fresh approval. Previously derived assets remain traceable to their original mockup; affected production assets must be reviewed or regenerated and not silently relinked.

### Asset lifecycle

- New final-candidate sprite PNGs, component images, sheets, JSON atlases, metadata, previews and validation reports are stored together under `outputs/assets/generated/`.
- Only explicitly approved, validated asset revisions move into `outputs/assets/approved/`.
- Rejected, withdrawn and superseded revisions move into `outputs/assets/revoked/` with reasons and replacement references.
- Each revision is treated as a coherent **bundle**: all its PNGs, per-sheet measured JSON atlases, component/attachment/state metadata and required dependent files change lifecycle status together. Do not approve just the PNG or leave the atlas behind.
- Only active approved asset revisions may be used as authoritative input for new production or runtime scene assembly; revoked assets may be consulted for historical diagnosis but never chosen silently.
- Assets may share an approved mockup or depend on additional explicitly approved mockups. Preserve many-to-one and one-to-many links in metadata.

### Descriptive names and revision identity

Use sanitized, descriptive, game-related basenames. Never use `image1`, `final2`, or similarly vague names for approved art. Recommended pattern:

```text
<game-slug>_<descriptive-content>[_<state-or-action>][_<direction>]_vNNN.png
<same-basename>.atlas.json
```

For approved mockups, include scope and content:

```text
<game-slug>_<scope>_<descriptive-content>_mockup_vNNN.png
```

A logical `asset_id` or `mockup_id` remains stable across descriptive filename changes and subsequent revisions. Paths must be portable, unique and sanitized. Maintain the actual image filename referenced in companion atlas JSON.

### Required traceability contracts

Each production asset revision metadata must reference:
- `asset_id`, `asset_revision`, `status`, `descriptive_title`, `game_id`.
- `source_mockups`: one or more `{mockup_id, revision, approved_reference_path, source_region?, hash?}` references.
- The approved mockup blueprint element IDs from which its geometry, texture, details, parts and animation candidates were extracted.
- `master_art_reference`, applicable art/asset profile IDs, provenance and validation outcome.
- Its PNG/atlas/component filenames plus content hashes when possible.
- `approved_at`, `revoked_at`, `reason`, `supersedes`, `replaced_by` when applicable.

The mockup manifest records source references, scope, approval, revision, detailed blueprint, derived asset IDs, and status. The asset manifest records current approved revision by stable asset ID. Both manifests must be kept consistent after any change.

### Safe lifecycle operations

1. **Generate:** Export to the relevant `generated` folder and record the candidate. Technical validation does **not** imply user approval.
2. **Approve mockup:** Confirm user approval, move the complete mockup revision and associated blueprint/references to `mockups/approved`, validate paths and update the mockup manifest.
3. **Generate asset:** Only after mockup approval, generate and validate an asset bundle in `assets/generated`, keeping links to the approved mockup.
4. **Approve asset:** On explicit approval of this exact revision, stage the complete bundle in `assets/approved`, validate copies/hashes/atlas references, atomically update manifest pointers where possible, then remove the generated copy.
5. **Supersede/revoke:** Preserve the complete old bundle under the appropriate `revoked` folder with an audit record, never silently delete it. Update affected active pointers and dependent references.
6. **Restore:** Requires deliberate reapproval and validation; moving a folder alone must not silently reactivate the files.
7. **Failure handling:** If any move/verification fails, do not claim success. Keep the old source intact and mark the transition incomplete; recover to a consistent state. Prevent overwrites and concurrent edits to the same asset revision.

### Claude/Codex behavior

- Read project settings and active custom instructions as usual.
- Detect the relevant approved mockup revision before production.
- When the user says “approve this mockup,” “reject this sprite,” “replace this art,” “show approved artwork,” etc., invoke the lifecycle skill to handle all files and manifests.
- Explain statuses simply. Users must **never** need to manually move files or edit JSON.
- The three states apply to both mockups and production assets; mockup approval is distinct from final asset approval.
- In Godot, prefer explicit manifest references to active approved revisions; do not indiscriminately glob folders for runtime assets.
- Keep exact opaque #FF00FF masking in every PNG including mockups; measured JSON atlas per sprite sheet, complete moving/directional attachments, and no ZIP delivery remain mandatory.

**Hard rule:** `mockups/generated → mockups/approved → assets/generated → assets/approved`, with any rejected or replaced revision retained in its corresponding `revoked` folder and with traceable source-approval links.


---

# Game Arts v7.4 — Automatic, Invisible Project Experience

**Status:** Mandatory universal usability policy. The framework must be powerful internally and simple for nontechnical users.

## Automatic behavior in Claude Code and Codex

- Once Game Arts instructions/skills are installed in a game project, the user should simply open that project and ask for artwork normally. Do not require special invocation phrases, manual skills selection, technical commands or setup rituals.
- The project's existing `AGENTS.md` or `CLAUDE.md` acts as the lightweight automatic entry point in tools that honor these instructions. Specialized skills and full reference files are loaded only when relevant, to avoid wasting session context.
- At the start of a relevant game-art task, quietly locate the target game and read applicable settings from `.gamearts/project.json`, active `.gamearts/instructions/*.md`, and relevant approved mockup/asset manifests. Do **not** automatically open or load every image, atlas, reference and entire skill document.
- Apply saved choices without asking the user to repeat them. Do not assume external assistants keep private in-memory state between sessions: persistence comes from accessible project files.
- If settings are missing, work with reasonable approved defaults for early discussion or mockups. Run the friendly conversational setup only when essential decisions are required for correct production or the user requests configuration. Do not block every art request on a questionnaire.
- Existing approved mockups and assets must be discovered when relevant, using manifest references. Do not resubmit approved work for approval unless the user materially changes it.
- Do not interrupt the user with folder names, schema jargon, setup mechanics or validation internals unless asked, or unless they must make a consequential decision.
- Obtain explicit approval where required (especially accepting a new mockup, approving production art, and materially changing accepted artwork). Never infer approval from silence.
- The agent handles descriptive naming, generated/approved/revoked file movement, matching PNG/JSON atlas bundles, linking exact approved mockup revisions, custom instructions, validation records and error recovery using accessible project tools. Do not ask the user to manually organize files.
- Report outcomes plainly: what was produced or changed, whether saved, what needs approval and what could not be verified. Never claim actions occurred if tools did not complete them.

## User-first interaction standard

- Default to short, conversational messages with one meaningful question at a time.
- Offer sensible defaults and a simple “use recommended settings” path when choice is required.
- Use everyday language such as **create**, **approve**, **change**, **show** and **restore**.
- Never force scripts, configuration-file editing, git operations or special agent commands on ordinary users.
- Keep specialist routing, schemas, validators, and installation detail behind the interface. Advanced options are available on request.
- One-off asset requests must not silently become persistent custom rules; save project-wide preferences only when the user's intent is clear.
- The standard applies to all Game Arts 2D styles, mockup scopes, and asset categories without hardcoding models or classes.

## Reliable loading, not excessive loading

An agent cannot promise that every platform reads the full framework automatically. Project-root instructions and skill discovery provide the supported automatic path **when the external tool is configured to load them**. A concise project entry point must always indicate where the current master, project settings, scoped custom rules, lifecycle manifests and specialist skills live.

**Expected user workflow:** Open game project → ask for art → receive mockup or production result → approve when necessary. Everything else should be automatic wherever tools permit.

All earlier mandatory requirements are retained: detailed mockup decomposition, approved references, shared world geometry, asset-relative scaling, animated nested attachments, full direction coverage when required, exact opaque `#FF00FF` PNG masking, measured atlas per sprite sheet, honest Godot validation, descriptive revisioned files, generated/approved/revoked storage, and no ZIP.


---

# Game Arts v7.5 — Integrated Wizard, Visual Mockups and Production Workflow

**Mandatory behavior:** All previously approved features are connected into one natural in-chat experience inside Claude Code or Codex. Automatic skill awareness must not bypass the setup wizard, actual mockup generation, approval, detailed analysis, animation, lifecycle storage, or validation.

## End-user contract
The user opens their game project and requests any game art in ordinary language. The agent quietly reads available project settings, active scoped custom instructions and relevant approved references, and routes work to the appropriate skills. Users do not manually choose skills, create folder hierarchies, use Python, or edit JSON. Only ask questions that materially affect the result; show recommended defaults for genuine choices.

### First-use and configuration
- If the user requests game configuration, invoke the conversational setup wizard automatically and save confirmed answers in the **target game** `.gamearts/project.json`.
- When no config exists but the user merely requests a mockup or brainstorm, proceed with grounded defaults rather than demanding a full configuration wizard. Ask for an essential missing detail only.
- If later work requires a setting that has not been specified and cannot be reasonably inferred from approved references, ask one simple question; store the preference after explicit user intent.
- If project settings already exist, load them rather than repeating the wizard.

### New game-art design
1. Locate relevant approved mockups/assets. If the requested design is already approved and unchanged, reuse that exact reference.
2. Otherwise invoke `game-arts-mockup-creator` to generate an **actual visual mockup** using an available image/design tool. Categorize world/scene/asset/character/UI/mixed scope, inherit the game style and saved instructions, and show it in the conversation.
3. Save the candidate in `.gamearts/outputs/mockups/generated/`, update metadata and the mockup manifest, then ask for **approve or revise**. A text prompt is not an actual mockup; never claim generation without completed rendering.
4. On approval, invoke `game-arts-lifecycle` to promote the precise revision to `mockups/approved/`. On rejection/replacement, retain it in `mockups/revoked/`.
5. Run `mockup-analyzer` and extract meaningful visible geometry, relative dimensions, textures, surface transitions, small objects, UI details, scene relationships and ambient/interactive animation candidates. Use nested blueprints where necessary. Never ignore scene micro-details or invent unavailable detail.

### Production from an approved mockup
6. Lock reference-conditioned masters and choose the active art and asset profiles. Build separate components and complete matching directions where required; plan key poses and moving attachment anchors when applicable.
7. Generate final assets, animation art and state/attachment metadata in `assets/generated/` using descriptive, game-related versioned filenames.
8. Assemble sprite sheets deterministically; measure actual PNG frame bounds; generate matching JSON atlases and validate pixels, pivots, links and animation.
9. Reconstruct and validate against the approved mockup and in Godot when supported. Report any incomplete validation truthfully.
10. Show the generated production art for explicit approval. On approval and applicable validation, promote the complete PNG/atlas/metadata bundle to `assets/approved/`. Reject/supersede to `assets/revoked/` and keep exact approved mockup links.

### Conversational management
- “Show my settings” → show existing selections, not a new wizard.
- “Set up Game Arts for my game” → short, conversational configuration wizard.
- “Add an instruction for this game” → save a custom scoped rule in `.gamearts/instructions/`.
- “Create a mockup” → actually render a reviewable mockup when tools permit, then request approval.
- “Make the mockup more detailed” → create and review a new revision.
- “Generate the sprites from that approved mockup” → use the locked approved reference; do not restart concept approval.
- “Show approved/rejected artwork” → query lifecycle manifests and show the result simply.

### Mandatory safeguards
Retain exact opaque #FF00FF backgrounds for PNGs, one measured JSON atlas per actual sprite sheet, all required direction-aware nested and animated attachments, universal/art/asset profile consistency, world-space scale, individual deliverables, no ZIP archives, source provenance, and truthful tool/test status. The configured world grid remains orthogonal square where that game profile is selected.

**No new technical term or command is required of the user. The entire workflow is connected and automatically routed behind the scenes.**


---

## External and user-supplied mockup intake (v7.5 amendment)

Game Arts supports **both agent-generated mockups and user-provided mockups made outside the framework**. A user does not need to regenerate an external design in Claude or Codex.

When a user uploads, links to, imports or identifies an existing mockup:

1. Identify the **target game**, source artwork, visual scope, art style and whether the user has explicitly approved the exact version.
2. Preserve the original source file by default. **Copy/import** it into the game's managed mockup storage; never remove or alter the external original without express user authorization. If the file is only visible as a chat attachment or an inaccessible external URL, first obtain a legitimately accessible copy; don't claim import was completed when the agent cannot read/write the bytes.
3. Use descriptive game-related names, a stable mockup ID, new managed revision, source provenance, and file hash when possible. Do not reencode or modify original image pixels without an approved transformation. Validate its file type, content, dimensions and integrity.
4. If **explicitly already approved** by the user, import the candidate directly to `.gamearts/outputs/mockups/approved/` and record the approval source in `manifests/mockups.json`. That direct import **counts as mockup approval**; do not ask the user to approve the same version again.
5. If approval is unclear or not given, import into `.gamearts/outputs/mockups/generated/`, present a preview and ask simply whether to approve or revise. Do not silently promote the external file.
6. For rejected/superseded externally supplied mockups, keep the **managed copy** in `mockups/revoked/`; leave the original external source untouched unless explicitly instructed otherwise.
7. After approval, apply the same mandatory **full-detail mockup analysis** as for agent-generated previews, including geometry, textures, small features, components, material treatment and all realistic motion/state candidates. Use nested world/scene/asset/UI blueprints as appropriate.
8. Production assets must reference the managed approved `mockup_id`, exact revision, approved path, source hash/URI when allowed, and applicable blueprint element IDs. The same naming, master-lock, 8-direction coverage where applicable, animated attachments, sprite+measured atlas, opaque #FF00FF, Godot validation and asset lifecycle rules still apply.
9. If a user-supplied *mockup* has transparency or a nonconforming background, preserve the unmodified external original as provenance and create a **separate compliant working/export copy** when needed and technically achievable; obtain clarification for destructive or appearance-changing conversions. Do not falsely claim exact opaque pink compliance until it is measured and verified.
10. An imported mockup is a **visual reference**, not automatically a finished sprite sheet or runtime asset. Production outputs still follow their own generated/approved/revoked lifecycle.

Everyday behavior:
- "Here is my mockup, use it" → import a managed copy under `mockups/generated/` unless explicit approval is stated, then show it for approval.
- "This mockup is already approved" → import under `mockups/approved/`, record approval and start detailed decomposition, without recreating the mockup.
- "Replace the current mockup with this external version" → register a new revision, confirm material changes as needed, retain the old managed revision in `mockups/revoked/` only after a successful transition.

**Rule:** Imported and agent-generated mockups enter the **same traceable mockup lifecycle**; source ownership and approval status remain explicit.


---

# Game Arts v7.6 — Executable Modular Moving-Part Bundles

The repository includes `scripts/build_component_bundle.py`, used internally by Claude/Codex to create real sprite-sheet PNGs, JSON atlases and a validated hierarchy bundle for *any* approved modular 2D asset. There is no hardcoded requirement for a particular object class, moving part, direction count or animation frame count.

## Production contract
- First approve mockup and lock directional/component master artwork.
- Every component declares an ID, optional parent ID, named parent attachment and appropriate source frames in every direction required by the asset profile. Each frame includes explicitly measured pivot and named anchor pixels.
- Each component receives an individual actual PNG sheet and measured atlas JSON per required direction through the existing deterministic atlas builder. Every unused pixel in exported sheets stays exact fully opaque #FF00FF.
- Parent-local mounting is calculated from measured parent frame anchors and pivots. Animated mount tracks and child motion tracks are separate and support position, rotation, scale and normalized time; components form validated non-cyclic nested hierarchies.
- The bundle records directional sheets/atlases and sample composed transform matrices; direction changes can be evaluated by selecting matching directional frames and preserving normalized motion phase.
- Validate complete directional coverage, named mounts on each parent source frame, nonzero scale, finite coordinates, valid track ordering and hierarchical relationships before publishing the bundle.
- Store all output files together in the game's `.gamearts/outputs/assets/generated/` with a meaningful asset revision ID and references to approved mockups. The user must still approve final art before promoting the complete bundle to `assets/approved/`.
- This executable builder consumes supplied, preapproved PNGs and verified anchor coordinates; **it does not automatically detect true physical mounting points**, generate missing art, provide collision/light updates or certify Godot runtime behavior. Actual composed Godot scene and art-fidelity checks remain separate mandatory gates.
- If output, runtime validation or artwork is missing, disclose that accurately. The agent executes tooling without asking the ordinary user to run commands or manually edit JSON.

See `docs/COMPONENT_ANIMATION.md` for the job schema, transformation convention and test scope.


---

# Game Arts v7.7 — Godot 4 Runtime Component Integration

**Scope:** All modular 2D artwork using the Game Arts component bundle contract. This section adds executable Godot runtime integration without changing the approved game geometry, art styles, mockup workflow, universal pink PNG masking, lifecycle or atlas requirements.

## Universal runtime scene
- Use the reusable `res://addons/gamearts/game_arts_component.tscn` scene and `game_arts_component.gd` script for JSON-based modular assemblies when appropriate. The scene references an actual `<asset>.bundle.json` exported by `build_component_bundle.py`, with per-direction real PNG and atlas resources.
- Render opaque `#FF00FF` source sheets using `chroma_key.gdshader`, which discards the chroma key **at runtime only**. Source and delivered PNGs retain exact RGB 255,0,255 and alpha 255 in unused areas.
- For each component, use its corresponding directional atlas texture region, frame pivot and parent named mount. Construct the hierarchy as nested `Node2D` objects so parent transforms propagate to children.
- For animated parent attachment points, evaluate parent-action, direction and normalized-time mount tracks separately from the child component's own motion. Compose parent mount, animated mount, rest and child-motion transforms in the correct documented order.
- Changing a facing direction selects all related directional frames, pivots, anchors and local transforms within a single pose update, preserving normalized animation progress. No child may borrow art from a missing direction.
- Keep technical build/geometry validation separate from actual visual confirmation. Do not call an asset `game-ready` until a real Godot scene is loaded and applicable direction/action, layering, animated attachment and masking tests pass.
- `scripts/generate_godot_scene.py` may create a native `.tscn` that references the bundle path within the game project, provided its Godot addon is installed. Refresh file references when moving bundles between generated and approved folders.
- Do not silently assume collision, navigation, light occlusion, per-frame duration playback, perspective-correct deformations or physically inferred hinges are automatically implemented by this runtime. These remain explicit future integration requirements and validation gates.

## Developer regression contract
- Preserve the executable component bundle and atlas builder tests.
- Check native scene file generation, invalid/missing bundle refusal and nonoverwriting behavior.
- Add actual headless Godot loading, animation, chroma-key render and screenshot tests before upgrading runtime-test status to passing. A Python-only test does not count as a Godot runtime test.
- All tools run internally from Claude or Codex where available. No user-facing script invocation is required.

**Status:** Runtime loader and scene generator published. Actual Godot headless/editor execution remains unverified until run in the target engine.


## Permanent asset view and direction classification

**Before generating artwork, classify the asset by gameplay behavior and use the game-approved art style and projection consistently.** Never generate additional angles solely because the framework can support them.

| Asset class | Default views | Moving components |
|---|---|---|
| Static structure or fixed building | **One** locked, approved world-facing view | Separate frame-based or transform-animated parts as applicable; the static master does not rotate |
| Fixed machinery or permanently installed industrial equipment | **One** locked, approved world-facing view | Animate arms, linkages, valves, flame, doors, etc. independently as appropriate |
| Mobile object, vehicle or free-facing actor | **Eight** coherent directions (S, SW, W, NW, N, NE, E, SE) when gameplay supports directional movement or facing | Correct direction-specific components and applicable actions; preserve model identity and physical scale across views |
| UI icon, portrait or presentation graphic | **One** UI-optimized view unless UI behavior requires otherwise | UI-specific states/effects; don't reuse world camera assumptions |

A fixed asset may explicitly require a **limited rotation set** for placement or an interactive turning assembly; then use only its actual approved orientation set (e.g., 2 or 4) without forcing eight. Conversely, a mobile asset whose gameplay supports free directional travel uses the full eight-direction package and synchronized moving attachments. A fixed installation's independently rotating arm or turret is not grounds for rotating its entire base or rebuilding all eight static views.

For every asset, record `asset_class`, `view_policy`, `directions`, `approved_view_reference`, `rotation_requirements`, and independently animated `components` in its production blueprint/manifest. A valid single-view bundle must include exactly that one declared direction for all relevant components; validators must derive coverage from the declared profile, **not demand eight directions from a structure**. Only generate directions verified necessary for gameplay.

**Appearance lock:** Across any genuinely required directions, keep structure/model identity, geometry, materials, wall/door/window layout, proportions, scale, palette, component attachment logic and pixel density consistent. A different angle is not permission to redesign the object. Do not include labels, grids, diagrams, or example JSON inside actual production sprite PNG sheets. Measured metadata lives in separate JSON files.

**Oilfield Days defaults:** workshop, cabins, warehouses, fuel farm, separators, pumpjacks and flare stacks use a single approved top-down-oblique world angle (with independent door/linkage/flame animation); freely moving trucks, forklifts and mobile construction equipment use eight direction masters and applicable action sheets; fleet thumbnails, build-menu icons and dispatch portraits are separate UI presentation resources.

**Repository maintenance rule:** Update the current existing canonical master standard **in place** and update existing README, skills, instructions, validator contracts and documentation as needed. **Do not create another version-numbered master document or duplicate guidance file for routine changes.** Preserve previous sections and amend the current file rather than producing a parallel version.


**Consolidated mockup scope principle:** `Identify mockup scope → analyze every meaningful visible detail at that scope → descend into nested blueprints as needed → plan static and animated production assets → validate reconstruction against the approved mockup.`

---

## Mandatory reference-controlled image prompting — permanent framework contract

This section governs **all prompts submitted to image generation or image editing tools**, not merely user-facing explanations. Prompt quality is a production gate. The model must not substitute an attractive generic illustration for a faithful asset built from the approved mockup.

### Preflight: construct a verified prompt packet

For each generation/edit, resolve the following from the game project and exact approved mockup/blueprint revision:

1. **Visual source**: actual image reference(s), source file path or image ID supported by the tool, mockup ID/revision, selected crop/region and component identity. **Attach/pass the actual source image to the image tool whenever the tool supports conditioning; mentioning a mockup in text is not equivalent.** A screenshot containing several assets should be cropped/isolated to the correct region for reference. Do not claim the tool received an image if it did not.
2. **Target classification**: static_structure / fixed_machinery / mobile_directional / ui_presentation / environment / prop / effect; state whether it is a master, edit, layer, key pose, reference concept or production export.
3. **Style lock**: approved art style, exact gameplay camera/projection, palette/materials, line weight, texture density, light/shading and pixels-per-meter policy, plus immovable world-space geometry (Oilfield Days: top-down elevated 3/4 oblique, orthographic; not isometric).
4. **Identity lock**: observed features and spatial relationships that **must remain unchanged**. List distinguishing roof shape, building footprint, openings, machinery attachments, side materials, windows, proportions, and anchors. Do not invent reference details not actually visible; label unknowns and obtain approval before locking them.
5. **Change contract**: enumerate precisely what may change, and state that everything else must remain identical. For component motion, source artwork and parent body geometry must remain fixed.
6. **Directional policy**: static structures/fixed equipment = **one** approved world-facing view by default; freely moving directional objects = **eight** matching views (S, SW, W, NW / N, NE, E, SE) where gameplay needs them; UI display = separate presentation style; limited rotation only where declared. Direction means rotation of the SAME object, not redesign.
7. **Export constraints**: single isolated asset/component per production image unless explicitly building a verified sheet, measured native resolution, exact solid opaque #FF00FF background (RGB 255,0,255, alpha 255), no text/labels/panels/grid lines/borders/mock JSON, no gradient/pink halos or baked-in unrelated objects, no arbitrary perspective transforms or resampling.
8. **Tool capability contract**: image generator for art/key poses, image editor for source-conditioned revisions, deterministic pixel/layer processing for repeatable animation/assembly, actual atlas generator for JSON. If image conditioning, precise segmentation, or deterministic editing is not available, **stop that step and disclose**, rather than silently replace with freehand whole-image regeneration.

A prompt packet may be serialized internally in the game project's production blueprint but does not require manual user form entry. The agent composes prompts silently from approved references and scoped custom rules.

### Universal image-generation prompt skeleton (fill bracketed fields with verified data)

> **TASK:** [one exact output: static master / component art / controlled edit / single key pose / concept mockup].  
> **AUTHORITATIVE REFERENCES:** Use attached [approved mockup revision] and [cropped target region]; preserve [locked master ID] when supplied. Do not replace these with a generic art-style interpretation.  
> **CLASS + VIEW POLICY:** [asset class], [one fixed oblique world view | one exact mobile direction | one UI portrait direction | explicitly limited rotation].  
> **CAMERA:** [approved camera description]. **Never isometric unless the selected approved game art style explicitly IS isometric.** No camera-angle drift between master, layers or poses.  
> **IDENTITY LOCK:** [observed invariant geometry, proportions, palette, material, attachments, perspective and distinguishable small details]. Preserve location of every unchanged pixel/element when editing source pixels.  
> **ALLOWED CHANGE:** [only explicit layer / component / state / pose change]. **UNALLOWED:** new extensions, alternate roof, relocated door/window, altered depth, added props, different structure identity, alternate camera.  
> **COMPOSITION:** one isolated subject [or exact bounded component] in native-size-compatible framing; entire silhouette visible, stable anchor and ground contact, clear buffer around bounds.  
> **OUTPUT:** standalone art on solid #FF00FF, completely opaque, no captions, diagrams, invented coordinates, contact-sheet panels, UI or multiple angles unless the task explicitly asks for an approved multi-view *review* layout.  
> **QUALITY TARGET:** match reference silhouette and visual density first; high image appeal is secondary to fidelity. If important reference details are ambiguous, preserve observed content and surface uncertainty rather than inventing.

Treat this as **actual instructions to the image tool**, adapted to the tool's supported reference-image mechanism. Do not merely print the skeleton in chat and call that a generation.

### Task-specific prompt templates

**A. Static structure / building master (one approved angle):**

> Produce exactly ONE isolated [building] using the attached, cropped approved [mockup ID/revision] as the authority. Match its **elevated top-down 3/4 oblique orthographic** camera and [approved style]; not isometric, not frontal, not architectural rendering. Lock the same roof pitch/outline, wall proportions, door bay and window positions, cladding, material tones, ground footprint and distinguishing details. Preserve only details visible in the reference; missing unseen features require explicit design review. Base is fixed and does not rotate; no eight-view sheet. Moving doors and lights will be separate later. Solid opaque #FF00FF background; no labels, illustrated captions, animation strip or contact sheet.

**B. Fixed machinery master (one approved angle, modular):**

> Render one fixed [machine] base from [approved mockup crop]. Preserve mechanical footprint/supports/gear location and oblique camera. Identify stationary housing versus pivoting beam, crank, rod, turret, valve or flame; **do not draw separate motion poses or composite six whole-machine redraws**. Export the fixed base and separately approved components later, maintaining mounting landmarks. Same #FF00FF isolation requirements.

**C. Mobile asset locked master, single requested direction:**

> Render [direction] of [locked vehicle/equipment identity] based on attached approved design and existing directional master. Keep physical width/length/height, wheelbase, axles, cab body, doors, windows, cargo bed, color and mounting geometry consistent. Only rotate the **same** object to [direction] under the approved world camera; do not reinterpret shape or introduce another model. One direction only in this generation. Preserve standard world-scale pixels-per-meter and ground pivot. Repeat until all required directions are visually approved before creating action-specific animations.

**D. Separate moving part / layer extraction:**

> Starting with supplied **locked master**, isolate only [component] while preserving correct [direction/state] geometry and original scale. Provide component with its real hinge/pivot/attachment neighborhood intact. Do not repaint the static parent, redraw an alternate building, invent hidden geometry or turn this into a scene-wide sheet. If the hidden portion is not present in the reference, request an additional approved source/key pose rather than claiming precise extraction.

**E. Single animation key pose (controlled):**

> Edit only [component] from approved [component master] to [pose/state at normalized time]. Keep master camera, color, outline, lighting, texture resolution, attachment identity and base pixels unchanged. Return **one pose**, not an animation chart. Parent remains pixel-identical. Preserve declared pivot/hinge; do not move it to fit a visually pleasing composition. Generate necessary unseen component art only with explicit approved reference. Assemble/interpolate subsequent frames deterministically when transforms suffice.

**F. UI presentation graphic or icon:**

> Use attached approved UI screen and associated world-asset identity as visual references. Produce one [UI icon/portrait/frame] at its approved screen-space presentation view and hierarchy, not a 3/4 world sprite unless the reference actually uses it. Match UI palette, outline and spacing; keep text and dynamic values separate for Godot UI except deliberately decorative lettering. No world-view directional package.

**G. Terrain, roads and modular environment:**

> Follow approved orthogonal square-grid coordinates and texture/profile scale; create precisely one [tile/overlay/prop] serving [edge/transition/variant]. Preserve natural variation and boundary-matching requirements. No isometric diamond tile, raised sidewall, terrain slab thickness or baked shadows unless explicitly required. Keep terrain and independent features in separate layers/assets.

**H. Effects, particles and screen feedback:**

> Generate only [effect component/key pose] with the approved style and localized attachment bounds, not a full scene. Specify loop or state timing. Keep parent base unchanged, and use shader/tween/procedural effects rather than repeated raster art where that is accurate and more stable.

**I. Source-conditioned correction / failed output repair:**

> EDIT the provided output **against the attached original approved mockup crop**. Restore [specific mismatch: camera, roof outline, static pixels, hinge, proportions]. Change *only* those mismatched features. Do not add artwork or regenerate another interpretation. If the tool cannot perform a locality-preserving edit, reject and return to master/source stage.

### Staged image workflow — must NOT collapse into one prompt

1. Reference crop & evidence extraction → 2. One master candidate only → 3. Compare and explicitly approve master → 4. Independent visible components → 5. Approved key poses as needed → 6. Deterministic transforms and assembly → 7. Real PNG sheets and measured atlas JSON → 8. automated+visual validation → 9. separate final production approval.
Never prompt a generative image model to create the full structure + six redraws + detachable components + printed JSON in one shot. It produces an *illustration of a sprite sheet*, not a verified sprite sheet.

For animation, compare a shared unchanged-pixel mask against the approved static master and reject changed static regions. Reject inconsistent perspective, mismatched directions, missing/shifted hinge anchors, clipping, repeated frames where meaningful motion is required, invalid #FF00FF, or printed metadata on the PNG. The validator must distinguish **artistic reference-consistency review** from **pixel/atlas script checks**; neither alone proves a Godot-ready asset.

### Mandatory response to failed prompt validation

Do not deliver an invalid image as completed game art. Report the specific failure, classify candidate as rejected/needs-revision, preserve the prior approved master, and revise the **prompt packet or source constraints** before using image generation again. Repeating the same broad prompt is prohibited. Never silently promote a review image to an approved asset.


## Mandatory saved-settings resolution for EVERY image prompt

**The selected project's actual settings are authoritative inputs, not examples.** Before composing **each image-generation or image-edit call**, load the target game's `.gamearts/project.json`, applicable active `.gamearts/instructions/*.md`, approved mockup/asset manifests, art-style reference, and asset-specific profile/locked master if one exists. Read and resolve values; do not merely mention the settings files in a prompt.

Resolve the effective values **in this order** (lower-priority sources cannot silently override higher-priority constraints):
1. Framework's nonnegotiable output/safety invariants (exact opaque #FF00FF, honesty, approval/measurement).
2. Explicit user request for **this output** and already approved image/master identity (if a change conflicts with approved identity, request revised approval instead of silently replacing).
3. Applicable active game-specific custom instructions and asset/scene-specific approved profiles.
4. The **selected** project settings in `.gamearts/project.json`, including `art_style.id`, optional `art_style.reference`, `world.object_camera`, grid/scale `world.*`, `directions`, `animation.preferred_method`, and `export.*`.
5. Framework defaults **only for genuinely absent settings**. Never present a fallback as an explicitly selected style.

**Prompt packet must carry resolved actual values:** `game_id`, `settings_source`, `art_style_id`, actual style reference/crop, `camera`, visual medium, scale, art-specific detail and outlining, chosen directional policy, animation technique, background/export rule, locked identity, permitted modification, and provenance. Apply medium-appropriate rendering: crisp deliberate clusters for pixel art; controlled natural brushwork for painted art; smooth edge policy for vector/illustrated art; rendered-source constraints for 3D-to-2D. **Never hardcode pixel art, Oilfield Days colors, top-down oblique, 8 directions, or isometric exclusions across all projects.** The special Oilfield Days camera/style applies only when its actual selected game profile or approved image calls for it.

**Mismatch handling:** If `project.json` requests one style/viewpoint while an approved mockup requires another, flag the conflict, preserve both sources and use the explicitly approved asset reference for the existing asset until the user approves a change. If no approved style exists and style selection is essential, use the short conversational project-settings wizard; otherwise form a clearly identified provisional concept from the profile defaults. A prompt must not silently invent nonexistent project settings.

**Pre-call check:** compare resolved packet to the specific image tool prompt. Assert the *same* selected style, approved camera, reference attachments, view policy, geometry/scale rules, and correct isolated output target appear as actual instructions. Do not submit an unrelated generic image prompt. After generation, compare output to the resolved packet and mark mismatches rejected or unverified.

**Important:** Project-wide settings describe a default. Component-specific approved constraints and actual visible source artwork can narrow them, but the model may not secretly switch artistic style or camera to improve aesthetics. The user should not need to restate saved selections or run configuration commands.


---

## Executable approved-reference crop and conditioning gate

**Preflight is mandatory for production artwork derived from approved images.** An image-generation prompt mentioning a reference is not evidence that the actual approved image was used. Use the executable helper at **scripts/prepare_reference_crop.py** (or verified equivalent tool integration), not a generic text-only reinterpretation.

### Source preparation and image-tool attachment
1. Resolve selected game settings (.gamearts/project.json), active applicable custom instructions, mockup and asset manifests, and the exact approved visual source and its SHA256.
2. Confirm the target mockup's ID, revision, explicitly approved state, source file inside .gamearts/outputs/mockups/approved/ and matching record in .gamearts/outputs/manifests/mockups.json. Import previously approved outside mockups through the lifecycle before production cropping; do not bypass approval or claim an import was saved when it wasn't.
3. Identify and measure an actual object region rectangle (x,y,width,height) inside the source image, with minimal context padding. Save this as the selected region and lock the observed perspective/identity. **Do not invent coordinates or swap another asset's crop.**
4. The agent prepares an internal reference job using the approved mockup record, selected asset class, bounding rectangle, identity constraints and scoped custom rules; the helper creates an actual pixel-preserving PNG crop, reference.packet.json with the source/crop/settings hashes and selected style/camera/directions, and reference.prompt.txt containing resolved selected project settings. The screenshot crop is a *reference*, so preserve original source colors: do **not** recolor it chroma pink. Production PNG outputs still must have fully opaque exact #FF00FF backgrounds.
5. **Pass the actual crop as an image input** to the image tool if it supports reference conditioning. A file path or textual phrase in the prompt alone is insufficient. If source-conditioned image input is not available, stop the production stage and disclose the limitation. Do not quietly generate an unrelated generic image.
6. After a real image-tool call, record an invocation receipt containing actual tool invocation ID, attached reference path and SHA256, generated candidate PNG path and SHA256, and whether image input was attached. The helper's verify command checks file hashes, source/manifest/settings changes, declared input attachment, PNG opacity and pink key corners. **Agent-written receipts are not host/provider-side cryptographic evidence**; mark conditioning agent-reported and require actual visual review.
7. Compare the candidate against the very same prepared crop for camera, silhouette, roof, openings, material/color/style, proportions, ground contact and visible details. A passing source/hash check does not prove visual fidelity. Mismatched production artwork remains generated or rejected, not approved.
8. After the locked master is approved, independently build moving-component layers and approved poses; construct real sprite sheets and measured atlases deterministically.

### Internal reference-job fields
- asset_id: a descriptive versioned asset slug.
- asset_class: static_structure, fixed_machinery, mobile_directional, ui_presentation, terrain, prop, or effect.
- approved_mockup: object with id, revision, approval_status = approved, file under the game's approved mockups directory, sha256 from the actual file.
- region: object with id, rect = [x,y,width,height] measured in **source pixels**, optional padding_px.
- identity_lock and applicable_custom_instructions: lists of observed details and resolved user rules.
- approved_camera/directions/rotation_policy: optional approved asset-specific overrides, subject to conflict checking.

The source manifest must contain an approved record matching the ID, revision, path and hash. The helper intentionally refuses to fabricate image references or approve a candidate. It cannot prove the provider consumed a referenced image, compare art fidelity by itself, infer physical hinges or certify engine readiness.

### Universal view behavior
Selected project art style/camera are mandatory inputs. Fixed structures and installed machinery use one approved view unless explicit placement rotations are approved. Mobile freely facing assets require eight coherent direction variants when their game profile calls for them, but the image model must generate one controlled directional master at a time. UI portraits are independent of world-camera packages. Never hardcode one game's oblique style or a generic isometric viewpoint into another project's prompts.

**No additional master document:** Update this existing canonical standard and its specialist skills in place.


### Reference-crop installation and asset-lifecycle integration (all projects)

The executable image-reference gate is a **built-in step of the current skills and lifecycle**, not a standalone workflow, new master document, new image-type directory, or manual process.

- **Package:** Distribute `scripts/prepare_reference_crop.py`, existing asset/sheet builders, schemas, the single master, and both Claude/Codex skill trees together. Pillow is a required helper dependency. When missing, the agent checks/installs dependencies using permitted tools or reports the blocker; it does not silently skip reference conditioning. Installation notes belong in the existing README_INSTALL.md.
- **Input:** The current `mockup-analyzer` selects the source-pixel region and returns `source_region_px=[x,y,width,height]` and the observed identity constraints, while the existing mockup lifecycle supplies a truthful, matching approved ID, revision, managed path and SHA256. Those fields are represented in the current blueprint schema; no new source-of-truth file is needed.
- **Output location:** Reference crop, `reference.packet.json`, `reference.prompt.txt`, and optional image invocation receipt live under the **existing** `.gamearts/outputs/assets/generated/<asset-revision>/reference/` folder. Candidate sprite images and measured atlases are separate siblings in the same asset bundle. Supporting reference files do not become independent lifecycle objects.
- **Prompt routing:** Resolve **actual** selected game settings and asset class: fixed structures and machinery get one approved world view; mobile free-facing assets get the selected directional set; UI portraits use optional `art_style.ui_camera` or approved UI presentation reference (never inherit world object camera automatically); terrain uses optional `world.ground_camera` or ground-grid depiction. Character, prop and effect view requirements follow their approved asset profiles. Respect game-specific active instructions and never hardcode an unrelated game's art style.
- **Generation gate:** Pass the actual crop into a reference-capable image/edit model as an image input. Do not claim tool support or attachment if it was not observed. The reference-image receipt is agent-reported evidence, not host/provider attestation; visual review of the candidate against the same approved crop is still compulsory. A visually unfaithful master is rejected, not followed by component animation.
- **Availability:** Any user installing the complete framework into their game project receives this behavior automatically for production from approved mockups; it does not require special prompt phrases, manual crop jobs, new setup screens, or new folders. Pure first-time mockup creation and non-image tasks are unaffected.

**Maintenance:** Update this same canonical master document, the existing skills, and the existing lifecycle/installation guides in place. Never create a parallel versioned master or duplicative image-type workflow solely for crop conditioning.


## Automatically keep local Claude Code and Codex framework installations current

**Permanent maintenance policy:** Every framework change must update both `.claude/skills/` and `.agents/skills/` and the single existing canonical master, validators, schemas, scripts and related documentation. Do not assume updating GitHub also changed anybody's personal computer.

### One-time opt-in local installation
The complete framework includes `scripts/sync_local_agents.py`. When a user says **"Enable automatic Game Arts updates for Claude and Codex"** in a locally connected agent, the agent should:
1. Locate the user's actual game workspace(s), existing Claude/Codex skill directories and a trusted checkout of this exact GameArtsSkills repository.
2. Inspect current configuration and obtain the normal explicit trust/approval for installing project-local lifecycle hooks. Do not hide that the hooks execute local code and can fetch updated code.
3. Run the updater's `bootstrap` mode **internally**, with the trusted repo as `--source`, each game as `--game-root`, and `--adopt-existing` only when the user authorizes updating previously installed framework-path files. That flag backs up files before replacing them. Never overwrite `.gamearts/project.json`, personal `.gamearts/instructions/`, `.gamearts/outputs/`, source assets or unrelated tools.
4. Merge one Game Arts `SessionStart` hook into existing `.claude/settings.json` and `.codex/hooks.json`, retaining all unrelated settings/hooks. Codex project hooks are subject to its built-in trust review; Claude hooks also require applicable local approval. Do not claim activation until those checks and an actual sync have completed.
5. Verify both project-local skill trees and installation state at `.gamearts/system/agent-sync-state.json`. Report any skipped local edits.

### Automatic update behavior
On each subsequent local **Claude Code or Codex session startup/resume**, each trusted hook runs the same local updater. It fetches the latest `main` revision from the configured `fahadTheTechIdea/GameArtsSkills` repository and updates both agent skill trees, the master standard, scripts, docs, schemas and Godot integration resources as one managed source set. It tracks installed file hashes. Files edited locally are **not silently overwritten**, and unrelated project data never enters its managed list. Existing `AGENTS.md` and `CLAUDE.md` contents are preserved; the updater refreshes only its marked Game Arts guidance block.

Network loss, an unavailable Git executable, no hook trust, installation conflict or inaccessible local filesystem mean that synchronization has **not** succeeded. Do not report that a remote GitHub commit directly updated an offline computer. When both agents are closed, a server-side GitHub commit cannot immediately push to their local installations; the updated framework is applied at their **next trusted SessionStart**, not instantaneously while offline. For an immediate refresh during an open session, a locally authorized agent may invoke the updater's `update` operation explicitly.

**Security:** This is an opt-in updater that fetches executable framework scripts from a trusted remote branch. Review/trust the source and hooks; follow workspace policies. Never install local hooks on another user's device without their action or connected file access.

### Developer validation
The existing test suite checks project data preservation, managed-file hashes, conflict handling, one-time backup adoption, hook merging/idempotence and file safety; the existing CI workflow watches `scripts/sync_local_agents.py`. A committed test suite is not a passing test run, and GitHub cannot attest to a user's individual local installation.


---

## Permanent universal parent-artwork cleanup and separation gate

**Applies to ALL selected art styles and ALL composite assets**: pixel art, painted, illustrated, vector, rendered-to-2D, custom, and future profiles. It applies equally to buildings, vehicles, machinery, characters, scene props, UI assemblies, modular effects and any parent artwork containing detachable elements. Do not misclassify a removable *workbench*, *screw*, *spanner*, *cabinet*, or interchangeable tool as fixed architecture merely because it appears in a reference screenshot. An object need not have its own animation to deserve a separate editable/movable sprite.

### Mandatory inventory BEFORE master generation

From each approved mockup, classify every visible element by **physical/gameplay ownership**:
- **Permanently baked static parent**: inseparable walls, roof, foundation, permanent shell, structural backdrop, fixed floor/cavity.
- **Independently movable**: objects/components that move as a unit relative to the parent.
- **Removable/repositionable**: independently placeable or relocatable props and furniture, even if not currently animated.
- **Interactive**: any object whose transform, state or independently rendered appearance can change through gameplay.
- **Replaceable**: optional, upgradable, detachable, damaged/swappable or independently selectable hardware.
- **Animated components**: mechanisms, lights, doors, wheels, cables, boom segments, rotors, flames and similar stateful subparts.
An object can satisfy multiple categories. **Every independently movable, removable, interactive, replaceable or animated element must be omitted from the final static parent image AND exported independently**, not merely duplicated as a second sprite.

When an original screenshot includes these elements, produce and approve a **clean background/foundation plate** revealing the wall, floor or mechanical mount behind them. Do not erase an object and leave a transparent hole, invented detail, or another copy of the item in the parent. Use real original/reference material and explicit review for otherwise occluded details. Nested parent/child artwork receives the same cleanup rule recursively.

### Image-generation instructions (derived from selected game settings)

For the **clean static parent**, the actual image-tool prompt must name the selected style, approved camera/projection, fixed or directional view policy, real attached approved source crop and **complete excluded-object inventory**:

> Generate only the [asset]'s permanent base/shell. Preserve the locked [selected project style, camera, physical scale, silhouette, materials and permanent structure]. **REMOVE from the parent image** every identified independent element: [observed removable props, tools, furniture, cabinets, animated mechanisms, doors, wheels, etc.]. Preserve/reconstruct the **approved clean background** where those objects previously appeared. Do not leave original object shapes, shadows, duplicated painted parts, or empty holes. No separate components inside the parent's PNG. Create each excluded object as a separate sprite/approved component in later individual operations; do not redraw unrelated static pixels. Maintain the game's exact opaque #FF00FF export requirement.

The list is **derived dynamically from the specific approved blueprint**, never hardcoded to the illustrative objects above. This is mandatory across art profiles; do not substitute a generic "pixel-art cleanup" instruction in vector or painted projects.

### Required verifiable technical proof

The production package must contain a parent-cleanup evidence manifest for every relevant parent, approved direction and rasterized parent frame:
- original composite image before detaching the items (same raster geometry as candidate),
- actual final **clean parent** image used to build that frame,
- a distinct **reviewed/approved clean background plate** showing what must remain behind each removed object,
- **binary removal/ownership masks** identifying actual pixel regions assigned to each detached component,
- independent nonempty opaque-pink component sprite PNGs and an inventory of IDs/classifications, including separately packaged props,
- immutable source references and hashes, matching real atlas source-frame hashes where applicable.

The new **scripts/validate_parent_cleanup.py** implements an exact raster comparison **independent of the visual art medium**. It requires the cleaned parent to:
1. have **no unchanged copy** of each declared item inside its removal mask (source must change),
2. match the reviewed clean plate in those pixels,
3. preserve the original parent pixels **outside** all declared removal masks,
4. include nonempty detached sprite art and unique nonoverlapping ownership masks,
5. retain consistent dimensions, full opacity and auditable source/component hashes.

Raster-mask evidence may be produced by a layered vector/painted/3D-to-2D authoring workflow without changing its visual style. **Exact pixel comparison is only valid when source and cleaned exports have aligned pixels.** If the art was independently repainted, rescaled, antialiased differently or the clean plate is not independently reviewed, this checker must not report a technical pass; obtain a genuinely aligned layered export and/or separately validated evidence. Never lower the fidelity gate merely because the medium is not pixel art. Binary masks are a technical ownership map; they do not force pixelated visible edges in painterly/vector final artwork.

### Production and approval enforcement

- The existing **scripts/build_component_bundle.py** may create a *generated candidate* without the parent cleanup proof, but must mark the cleanup status **pending** and must never declare the bundle approved or game-ready.
- When manifests are supplied, package the cleanup evidence into the **same asset candidate bundle** and run the technical gate before publishing any clean-proof status. In multi-direction/multi-frame assets, evidence must cover every relevant parent frame/direction (and recursively nested parents), with source-parent hash tied to the actual frame in its atlas.
- **scripts/validate_component_bundle.py --approval-gate** checks the mandatory cleanup coverage. Missing clean-parent proof, omitted inventory IDs, mismatched atlases, leftover objects or unreviewed plates fail the gate. Static single-master assets with separately exported props must use **scripts/validate_parent_cleanup.py** even when no moving-component bundle is produced. No user-facing Python steps; the agent runs tools internally.
- **Approval is blocked** until the blueprint's full detachable-object inventory is accounted for, every separated object's absence from the parent is verified, the cleaned plate/background is visually reviewed, and normal scale, camera, style, masking and atlas checks pass. A technical pixel-check cannot automatically discover an omitted object; visual inventory audit remains an independent requirement.
- Keep evidence and removed components with the existing **assets/generated / approved / revoked** bundle lifecycle. Do not introduce a new top-level directory, duplicate master document or special UI ceremony. Never deliver only an extra "props sheet" while leaving the identical props baked into the structure.
- On validation failure, **reject or revise the candidate static master**; do not patch the evidence/mask to conceal duplicated art. Only then proceed with independent animation and atlas generation.

**Illustrative Oilfield Days case (not a universal art-style setting):** Clean maintenance-workshop base retains approved roof, walls, open bay, floor and permanent structural features, but excludes the workbench, spanners, screws, independent tool chests and other separable equipment. Each removed item becomes its own correctly styled asset. If a garage door moves independently, it too is not baked into the locked static wall/background. Freely moving vehicles likewise cannot have wheels/doors duplicated in both chassis and separate moving-component sprites.


## Executable reject / revoke lifecycle guard — mandatory

The lifecycle exclusion rule is now implemented by `scripts/gamearts_asset_lifecycle.py` and tested by `tests/test_gamearts_asset_lifecycle.py`.

- Every Game Arts workflow must **resolve exact ID/revision through the lifecycle manifest**, rather than selecting the most recent PNG or retaining an older rejected file as an implicit reference. For new production, only exact **approved** mockups and approved assets are eligible references. For continuing a generated candidate, the record must be non-rejected `generated`.
- An explicit user rejection must **stop work on the rejected revision immediately**, record the reason, copy a manifest backup, move its complete file bundle from `generated` or `approved` into `revoked`, and atomically replace/verify manifest pointers. Use the helper internally and honor its errors; do not claim a transition that did not finish.
- Files preserved in `revoked` are for audit/possible separately authorized restoration only. **Never use revoked artwork as a source, reference, animation frame, or generated continuation.** The next generated revision remains independent/pending until explicitly approved.
- An existing record with `visual_review: rejected` or `approval: rejected` is ineligible even if a buggy producer left its physical files under `generated`. The agent must reconcile that inconsistency before proceeding.
- Approved source mockups are hash-checked before selection; candidates with physical paths contradicting manifest lifecycle status are blocked.
- User-facing commands are conversational (“Reject this version”, “Continue with current generated candidate”); agent executes the checker internally. Existing asset lifecycle storage and all visual style policies are unchanged. No new master document is created.
