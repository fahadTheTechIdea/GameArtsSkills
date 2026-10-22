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
