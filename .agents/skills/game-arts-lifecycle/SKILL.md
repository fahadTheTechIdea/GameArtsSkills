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
