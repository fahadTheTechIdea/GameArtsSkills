# Game Arts — Integrated Everyday Workflow

**User experience:** Open a game in Claude Code or Codex and ask normally. Game Arts uses its saved configuration, creates visual mockups, asks for explicit visual approval, analyzes the approved artwork, creates production assets and manages approval automatically. The user doesn't have to choose skills or run commands.

## What happens for each request

| User asks | What agent does |
|---|---|
| "Set up my game art" | Short conversational wizard; save approved defaults to `.gamearts/project.json`. |
| "Create a world/scene/character/UI mockup" | Generate a real preview using available tools, save generated candidate and show it for approval. |
| "Generate this sprite" with no approved visual | Make a suitable mockup first; ask approval before final sprite production. |
| "Approve" or "Change..." | Promote that exact mockup revision or generate a new revision; update manifest. |
| "Make the detailed assets" | Analyze the approved mockup into visible surfaces, textures, objects, actions, and separate animation candidates; preserve its reference IDs. |
| "Animate this" | Reuse locked masters, choose animation method, generate moving component/directional frames and attachment metadata. |
| "Approve the final art" | Verify technical quality and user approval, promote the complete PNG+atlas+metadata bundle. |
| "Show my settings/rules/approved sprites" | Read project files, show a short human-friendly result, and ask no redundant questions. |
| "Always do this for my game" | Save an active scoped custom instruction in the game project. |

## Invisible preflight

When a visual task starts, the orchestrator silently:
1. Resolves the target game repository.
2. Reads existing project settings and active relevant custom instructions.
3. Finds the relevant approved mockup/master/asset IDs from manifests when any exist.
4. Classifies the requested task and calls the correct specialist skill(s).
5. Uses only the necessary references, not every skill and image.

**Missing optional configuration must not prevent an initial visual mockup.** Ask for essential art decisions only; when the user requests game configuration use the conversational setup wizard. Avoid imposing a setup questionnaire on normal art requests.

## Mockup-to-asset lifecycle

```text
Open game → ask for art
   ↓
Generate real visual mockup (mockups/generated)
   ↓
Show preview → approve / revise / reject
   ↓
Approved mockup (mockups/approved)
   ↓
Detailed evidence-grounded blueprint
   ↓
Reference-conditioned masters, components, animation
   ↓
Measured sheets + JSON, Godot checks (assets/generated)
   ↓
Show result → approve / revise / reject
   ↓
Approved production asset (assets/approved)
```

Revoked/replaced mockups and assets move to their own revoked folders. Production asset bundles link to the exact approved mockup revision and blueprint elements. All generated files use descriptive game-related names.

## Hard rules

- Do not claim a picture was generated unless an image-capable tool created it.
- Do not approve a draft merely because it looks polished.
- Do not bypass new-mockup approval before final asset production.
- Do not skip detailed extraction of small mockup content.
- Exact opaque #FF00FF background for every exported PNG's unused areas.
- Measured per-sheet atlas JSON, accurate animated attachments, proper directional coverage and honest Godot testing.
- No ZIP-only deliverables.
- Do not demand user-run commands, manual file moving, manual JSON editing or repeated approvals for already accepted material.

## Bring your own mockup

**Bring your own mockup:** Upload or point the agent to artwork you created elsewhere. Game Arts imports a managed copy into the mockup lifecycle, preserves your original, and uses the approved version as its production reference—no unnecessary recreation.

When the user supplies an existing external mockup, **import a copy rather than generating a replacement**. Respect explicit prior approval; if not approved, ask for approval of that actual revision. Keep source provenance and a traceable managed reference. Do not claim an import succeeded unless file access and write operations were completed. Follow the v7.5 external mockup intake rules and require detailed decomposition before final art production.


## Prompting and production-image quality gates

When an approved mockup is the reference, create a **source-conditioned prompt packet** using its actual image or accurately isolated region, approved revision, camera projection, style, identity invariants, output type, exact allowed changes and artifact constraints. See **Mandatory reference-controlled image prompting** in `GAME_ARTS_MASTER_STANDARD_v7.7.md`. If a tool supports an attached reference image, pass it; merely saying "match the mockup" is insufficient.

For static buildings/fixed machinery, generate **one fixed camera master first**, with separate moving components only after the master has been visually checked and approved. For freely moving objects with directional gameplay, generate and approve a coherent eight-view locked master prior to separate action animations. For UI illustration, use independent UI-appropriate art/view rules. Do not ask image generation to produce a complete annotated animation sheet, companion JSON or mechanically accurate attachment measurements; assemble verified sheets and metadata with the executable tools.

Before advancing, compare style, silhouette, geometry, camera, materials, colors, perspective, moving-part mounts, static unchanged pixels and expected #FF00FF export. A deviation means reject/revise the candidate. Never claim image conditioning or technical verification unless performed.


## Actual prompt inheritance from project configuration

Before an image-generation tool call, the orchestrator resolves the current game's saved `art_style`, `world.object_camera`, reference imagery, visual detail rules, relevant instructions, asset profile/directions, animation preferences and chroma-pink export constraints. These are included as actual prompt instructions, with attached reference crops where supported. An agent must not substitute a generic art style or hardcoded perspective. Conflict or unknowns are surfaced and only essential missing choices are asked conversationally. After generation, compare output to resolved settings and approved visual references before advancing to master approval.

## Automatic reference crop after mockup approval — integrated stage

**Only when production is derived from an already approved visual**: the existing analyzer records the object/region and its exact source-pixel box; the existing lifecycle verifies its approved ID/revision, managed image path and source hash in `mockups.json`; the agent runs `scripts/prepare_reference_crop.py` internally to create a pixel-preserving reference crop, provenance packet and resolved style-aware prompt under the corresponding `assets/generated/<revision>/reference/` candidate subfolder. The crop is then passed as a real input image to a reference-capable tool; printing its file path in a prompt is not equivalent to attachment.

**User-created mockups** are first imported through the existing approved/generated lifecycle. **Brand-new concepts** are still generated through the existing mockup creator; do not demand a registered approved crop before producing the first *mockup*. A crop is required before reference-locked *production*, not before mockup brainstorming.

A recorded tool-call receipt with crop/image hashes supports traceability and basic file checks but does **not** prove the image provider conditioned on the crop or that the appearance matches. Review against the same crop and request approval of the master separately. Once locked, produce moving parts and real sprite/atlas files through existing specialist skills. If the framework helper, Pillow or image-conditioning access is absent, address availability internally or transparently report what could not be performed.

UI artwork inherits the chosen UI camera; terrain uses the approved ground camera/grid; world structures use the approved object camera. The selected game project's settings are read before every production image prompt. Do not introduce a parallel file lifecycle or hardcoded game-specific viewpoint.


## Framework auto-updates after one-time trusted enrollment

On a locally accessible game project, users may request **“Enable automatic updates for Game Arts in Claude and Codex.”** The agent detects current framework paths, runs the bundled updater bootstrap with permission and installs non-destructive `SessionStart` hooks for both clients. Existing game-specific `project.json`, custom instructions, approved mockups and assets remain untouched; colliding locally modified framework files are backed up only with permission or reported as conflicts.

On future starts/resumes either trusted agent checks the latest GameArtsSkills `main` commit, synchronizes both local agent skill trees plus framework scripts/master/docs, and reports failures. A remote GitHub edit alone cannot update a disconnected PC; the next trusted local session or an explicitly requested refresh is the update trigger. The user doesn't need to run update commands for routine use. See `README_INSTALL.md`.


## Mandatory separation-and-removal check for ALL asset styles

From the approved visual mockup, automatically inventory all independently movable, removable, interactive, replaceable and animated details—including small interior props and tools, not only obvious mechanical moving parts. Build a **clean static parent** with those items actually removed from its pixels; separately create each component as its own independently addressable artwork. Reconstruct the exposed wall/floor/background from reviewed source material and preserve the parent elsewhere. Do not treat an object as separated when its copy remains baked in the parent.

Before completing production: for each generated parent view/frame, run `scripts/validate_parent_cleanup.py` using the declared masks, cleaned parent, approved clean plate and detached sprites. For a multi-part animated bundle also run `scripts/validate_component_bundle.py --approval-gate`, which ties the cleaned parent to its atlas source hash and enforces direction/frame coverage. Missing proof means **not approved**. Separately review the completeness of the detachable inventory and correctness of exposed backgrounds; pixel checks can't identify an omitted asset. The same workflow applies to any selected medium (pixel art, illustrated, painted, vector, 3D-to-2D, custom). No user-run commands or new folders.


## Rejected versions are ignored

At the beginning of a task, the agent consults the actual lifecycle manifest through the bundled eligibility check. **Only an approved mockup/reference** can drive production; **only an eligible generated candidate** can be continued. Explicit rejection triggers immediate revocation of the exact version: move its whole bundle into `revoked/`, update its status and reason, verify manifest and files, and never use that revision again unless an explicit restoration/reapproval flow succeeds. Do not continue work on rejected artwork. Preserve other pending or approved versions independently.
