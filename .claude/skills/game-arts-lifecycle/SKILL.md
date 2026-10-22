---
name: game-arts-lifecycle
description: Manage generated, approved, revoked Game Arts mockups and production assets; descriptive naming; explicit user approval, replacement, and revocation; cross-linked mockup and asset manifests. Use for generating, approving, rejecting, restoring, finding or replacing any visual Game Arts revision.
---

# Game Arts Mockup and Asset Lifecycle

## Essential rules
Use the active game repository, never the shared GameArtsSkills repository. Read the canonical v7.3 standard plus `.gamearts/project.json` and active custom instructions. Handle all file management using the agent's available project filesystem tools; **do not ask users to run commands, move files, or edit JSON**.

Store:
- `.gamearts/outputs/mockups/generated|approved|revoked/`
- `.gamearts/outputs/assets/generated|approved|revoked/`
- `.gamearts/outputs/manifests/mockups.json`
- `.gamearts/outputs/manifests/assets.json`

Each revision has a stable ID, descriptive game-related filename, monotonic version, manifest entry and explicit lifecycle state. Avoid guessing approval or using vague generated names.

## Mockup lifecycle
1. Export a new mockup revision to `mockups/generated` with its preliminary blueprint and metadata.
2. On **explicit approval**, identify the exact revision and move its complete approved mockup package to `mockups/approved`, then verify/update manifest references.
3. On rejection or supersession, move the revision to `mockups/revoked` with an audit reason. Do not erase historical artwork.
4. Any production asset must reference the **specific approved mockup revision(s)** and relevant blueprint element IDs. Never derive final production from an unapproved mockup.
5. Materially changed approved mockups require new approval; derived asset relationships must remain traceable.

## Asset lifecycle
1. Create sprite sheets, component PNGs, matching measured atlas JSON and metadata as a complete candidate package inside `assets/generated`.
2. Mark as approved **only on explicit approval** after appropriate validation. Move the **whole bundle** to `assets/approved`; validate asset/atlas image references and update active approved manifest pointers.
3. On rejection, replacement, or withdrawal, move the entire bundle to `assets/revoked` and record the reason and replacement.
4. Preserve the old approved revision until the replacement is confirmed complete. Never silently delete prior work, accidentally overwrite a revision, or leave its atlas behind.
5. Revoked assets must not be used as an active reference in Godot; restoring one requires reapproval and validation.

## Naming and metadata
Use `<game-slug>_<descriptive-content>[_action][_direction]_vNNN.png`, `<same>.atlas.json`, and `<game-slug>_<scope>_<descriptive-content>_mockup_vNNN.png`. Sanitize names and avoid category-specific hardcoding. Keep stable IDs separately from filenames. Asset manifests record `source_mockups` (IDs, exact revisions, paths, and image regions), blueprint element IDs, validation status, dependencies and file hashes when available.

## Safe transitions
Before moving, check file existence, expected status, destination collision and completeness. Stage/copy and verify all resources, update manifests as consistently as filesystem allows, then remove old locations. If interrupted, restore coherent references or mark the operation incomplete—**never claim a state transition that was not verified**. Explicitly report missing files or unavailable tools.

## User-friendly requests
- “Approve this mockup.”
- “Show the generated sprites.”
- “Approve this version.”
- “Reject this image because its scale is wrong.”
- “Replace the approved artwork.”
- “Show revoked versions.”
- “Restore the older version.”

Respond with concise human-friendly filenames and status rather than raw JSON. Ask only when identity or approval is genuinely ambiguous. Users should not need to know folder paths.

## Quality requirements
Universal exact opaque #FF00FF source PNG; JSON atlas measured from every actual sprite sheet; locked approved references, dynamic animated attachment hierarchies, directional coverage when applicable, and Godot validation remain mandatory. Approval decisions are separate from technical validation.

## Connected workflow
Mockup creator registers actual rendered previews as generated candidates; on explicit approval promote the exact revision, then hand off to mockup analyzer. Production art is registered separately as generated and requires its own approval. Keep both lifecycles and exact mockup-to-asset links distinct.


## User-supplied / externally generated mockups
A user may supply an existing mockup created outside Game Arts. **Do not regenerate it.** Import a managed **copy** into the target game's mockup lifecycle, preserving the original external source. If the user explicitly confirms this exact revision is already approved, register it directly under `.gamearts/outputs/mockups/approved/`; otherwise register it under `mockups/generated/` and show it for approval. Store source provenance, descriptive versioned filename, ID, hash when available and manifest record. Never claim the import was saved if the agent lacks source access or filesystem permissions. After approval, analyze all its visual details and use that locked reference for production. Any exported Game Arts PNG derivative must comply with exact opaque #FF00FF; preserve nonconforming original external files separately and do not silently alter source pixels.

## Everyday user commands (natural language)

Recognize the complete user-friendly command catalog in `docs/COMMANDS.md`, including: **set up / show / change game settings; add / show custom instructions; create world/scene/character/UI mockups; import an outside mockup; import an already approved mockup; revise / approve / reject mockups; generate production sprites, component animations, and measured atlases; approve / reject / restore assets; show generated/approved/revoked artwork; validate in Godot.** Do not require slash commands or special trigger keywords. Infer intent and invoke the correct skill(s), respecting exact revision identity. An already-approved imported mockup is not regenerated. Ask for approval only when a real new mockup or final asset needs it. Do not claim actions completed without successful tool execution.


## Approved-source crop provenance (integrated)

During approval/import, record verifiable `mockup_id`, `revision`, `status: approved`, managed `file` and source `sha256` in the game's current `mockups.json`. On production requests, verify these records and use `scripts/prepare_reference_crop.py` to prepare the actual approved source crop **inside** the corresponding `assets/generated/<asset-revision>/reference/` directory. Keep the crop, prompt, packet and any truthful image-tool receipt with that candidate and link its provenance to the original mockup; do not create a new lifecycle or falsely mark the crop as approved artwork. The generated sprite/artwork and atlas must still receive their own approval. Reference crops preserve source colors; only new game-art PNG exports require pink masking.


## Enforce clean-parent gate BEFORE APPROVED transition

Production assets with ANY independently movable, removable, interactive, replaceable or animated child/prop **cannot be approved** simply because separate component PNGs exist. Check the analyzed complete `separation_inventory` and insist each separated object is **actually missing from the static parent artwork**. Keep candidate in `assets/generated` until this is verified.

For a standalone structure with separate props, internally run `scripts/validate_parent_cleanup.py` on the candidate's original composite, clean parent, independently approved clean plate, per-object masks and sprite evidence. For nested/directional sprite bundles invoke `scripts/validate_component_bundle.py --approval-gate` (plain geometric checks are insufficient), requiring proof for every parent view/frame plus declared detached inventory IDs, tied to the actual atlas source-frame hashes. Missing proof, residual original objects, unapproved clean plate, inaccurate fill, duplicated components, or inconsistent static parent geometry **blocks final approval**, even if a prior user likes the concept mockup.

Also require a **visual inventory completeness audit** because pixels alone cannot reveal undeclared objects. Never generate fake masks/clean backgrounds to game the gate; instead revise artwork with real approved references. Applies identically to any art style. Preserve evidence with the existing asset bundle during generated/approved/revoked transitions, no new top-level folders.


## Mandatory revoked/rejected asset exclusion (automatically enforced)

**Before EVERY reference lookup, generated-candidate continuation, image tool call or production operation**, use the existing lifecycle manifest and the executable `scripts/gamearts_asset_lifecycle.py` to select **only eligible records**. Production source mockups and source assets must be `approved`; the current in-progress revision must be `generated` and not `visual_review: rejected`. **Do not read/compose/regenerate from `revoked` candidates**, even if their files remain for history. A rejected/superseded candidate is not active merely because its former PNG path is still accessible.

**When the user explicitly rejects an image, asset, or revision**, route the precise ID/revision to `game-arts-lifecycle` and internally run the helper's `revoke` operation, with the recorded rejection reason. This validates bundle completeness, physically moves the entire managed version from generated/approved to `assets/revoked` (or `mockups/revoked`), backs up the manifest, updates its status/reason/path, and checks the transition. Never leave a clearly rejected candidate in `generated` with only a `visual_review: needs_revision` note, then silently reuse it. **Use exact revision identity** and do not mutate unrelated approved mockups or the next generated revision.

A different generated revision awaiting approval is **not automatically rejected** because an earlier revision was rejected. It stays in `generated`, never silently becomes `approved`. Do not continue toward final assets if a required master/clean plate has been rejected or remains unapproved.

The agent performs lifecycle actions using tools and verifies files; no user CLI or manual JSON required. If filesystem access is missing or errors occur, report the rejection intent and unsuccessful transition; do not claim that a revocation was persisted.


## Learned from approved workshop: reconcile every file after approval
Before treating any user-approved asset as reusable, run the bundled lifecycle audit against the actual approved asset. Match manifest status, blueprint status/production approval/clean-plate approval, validation visual-review status, physical folder and exact approved source mockup hashes. Inferred-but-accepted hidden geometry remains labeled inferred. If any file still says `generated_needs_visual_review`, `not_granted` or `pending_user_review`, reconcile it through the real user approval event with safe backups before selecting the asset again. Do not change `godot: not_tested` or scale calibration to passed. A clean mechanical/PNG check and a user visual approval are distinct gates. New production also uses reviewed local silhouettes rather than background-filled rectangular prop crops.


## Visual-review packet gate for NEW accepted composite assets

For newly produced art with removable/movable/interactive/replaceable/animated subparts, the agent must present the actual visual cleanup boards and obtain explicit user approval before `approved` status. Write an internal review decision only after a real user message approves the exact asset and specific inferred regions. Run `scripts/visual_review_cleanup.py verify` to check packet/source/board/mask hashes and completeness. Record `visual_review_protocol: "review_packet_v1"` and `visual_reviews: [{"packet":"<relative bundle path>","decision":"<relative bundle path>"}]` in the **existing assets.json record**. Store both files inside the same asset bundle; their relative links remain valid when moved to approved/revoked.

The existing `scripts/gamearts_asset_lifecycle.py audit` checks this protocol for all newly approved assets that declare it, and prevents reusable selection when the review is missing, points to the wrong asset/revision, or no longer matches the pixels. Do NOT add the protocol to historical approved artwork merely to force it through a new gate retroactively. A user approval record in JSON is **agent-reported**, not cryptographically host-attested; never synthesize consent. Preserve genuine remaining Godot/scale limitations and exact accepted inferred details.


## Finalize exact artwork acceptance through executable approval transition

For a **newly generated** asset that the user has explicitly approved, do not just move its folder and write optimistic JSON. Use `scripts/gamearts_asset_lifecycle.py approve` **internally**, supplying the exact generated asset ID and a truthful reference to the actual user approval message. For composite artwork, the helper requires the current source/blueprint's visual-review protocol and a valid packet/decision binding to the exact user-reviewed sprites, clean plate and uncertainty list. The helper reconciles blueprint/QA visual states, copies full bundle into approved, records final-art hashes, checks original source provenance and immediately runs the existing lifecycle `audit`. It attempts rollback if the audit fails. A local user-approved artwork is not automatically engine-tested; preserve `Godot: not_tested` and uncalibrated scale. Never fabricate a user decision or run the approval step before the user actually approves. Old approved artwork remains accepted unless explicitly revoked.
