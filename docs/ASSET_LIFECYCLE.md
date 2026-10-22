# Game Arts v7.3 — Visual Lifecycle and Mockup Links

Game Arts maintains **two connected three-state lifecycles** inside each game project:

```text
.gamearts/outputs/
  mockups/
    generated/
    approved/
    revoked/
  assets/
    generated/
    approved/
    revoked/
  manifests/
    mockups.json
    assets.json
```

## Why separate mockups?

A scene, world, character or UI mockup is a reviewable *visual reference*. An approved mockup is **not automatically an approved sprite/atlas**. The agent must first extract the mockup's geometry, textures, small details, reusable components and animation candidates. Every generated production asset records the exact approved mockup revision and relevant blueprint regions that inspired it.

Many sprites may come from one approved scene mockup. One complex production asset may derive from several approved mockup views. Both relationships are allowed.

## Easy commands inside Claude Code or Codex

Say **“Create a mockup”**, **“Approve this mockup”**, **“Generate sprites from the approved mockup”**, **“Show approved images”**, **“Reject this sprite”**, or **“Restore the previous artwork.”**

The agent creates/moves files and updates manifests within your **game repository**. No command-line tools or manual file renaming are needed.

## Naming

Use descriptive names matching the *actual game and content*, for example:

```text
gamea_scene_market-street_mockup_v001.png
gamea_market-street-lamp_idle_e_v002.png
gamea_market-street-lamp_idle_e_v002.atlas.json
```

These are examples only. The naming contract is generic and does not hardcode any class of game objects.

## Lifecycle guarantees

- **Generated:** created but awaiting user approval.
- **Approved:** user accepted this exact revision and necessary validation completed.
- **Revoked:** rejected, withdrawn or superseded; retained for audit, not active use.
- Matching PNGs, atlases and attachment metadata are moved as a complete bundle.
- Revocation reasons and replacement links are stored.
- A production asset's `source_mockups` reference the exact *approved* mockup revision and approved blueprint identifiers.
- Do not use revoked or unapproved images as active game assets.
- File changes and manifest pointers are verified before claiming a transition succeeded.
- All exported PNG unused pixels remain exact opaque #FF00FF.

See [master standard v7.3](../GAME_ARTS_MASTER_STANDARD_v7.7.md).

## Bring your own mockup

**Bring your own mockup:** Upload or point the agent to artwork you created elsewhere. Game Arts imports a managed copy into the mockup lifecycle, preserves your original, and uses the approved version as its production reference—no unnecessary recreation.

When the user supplies an existing external mockup, **import a copy rather than generating a replacement**. Respect explicit prior approval; if not approved, ask for approval of that actual revision. Keep source provenance and a traceable managed reference. Do not claim an import succeeded unless file access and write operations were completed. Follow the v7.5 external mockup intake rules and require detailed decomposition before final art production.

## Reference crops stay inside existing asset candidates

No new lifecycle or category-specific top-level image folders are created by source conditioning. The original approved mockup and its approved record stay under `mockups/approved/` and `manifests/mockups.json`. The **asset candidate** may contain `reference/<asset-id>_reference_crop.png`, `reference/reference.packet.json`, `reference/reference.prompt.txt` and, only after an actual image-tool call, a receipt describing what was attached. This support material remains tied to the generated asset's ID, revision, source mockup hash and measured source region. The candidate's actual PNG/sheet and atlas remain separate production files.

A registered approved mockup entry includes `mockup_id` (or `id`), `revision`, `status: approved`, `file` (managed path), and `sha256` of the approved source. The agent obtains these from actual files, never invents them. The reference helper validates this record before creating crops. If a different manifest representation exists, the agent must adapt it consistently to the existing project rather than invent false approval metadata.

Reference crops can preserve arbitrary original screenshot colors; they are **not delivered chroma-key game sprites**. Newly exported production PNGs still require fully opaque #FF00FF unused pixels and their own approval. A generated crop or positive technical receipt cannot upgrade an asset to approved.


## Clean-parent approval gate (all artwork media)

Before promoting a generated asset to approved, verify the complete inventory of detachable/movable/removable/interactive/replaceable/animated parts. Every such item must be **absent from the static parent sprite**, independently exported, and accompanied by suitable parent-cleanup evidence. Store reviewed clean plate, original composite, cleaned parent, per-object binary removal masks and validation results inside the *existing* candidate bundle. No new lifecycle.

For a structure/scene with separate static props but no animation bundle, run `scripts/validate_parent_cleanup.py` internally and visually inspect the completed clean interior. For modular rigs, use `scripts/validate_component_bundle.py --approval-gate`, requiring evidence per parent/frame/direction and all detached inventory IDs. The plain bundle builder or non-approval geometry validation does **not** authorize promotion. Absent evidence means `generated / pending`, **never approved**. If declared objects remain painted inside the parent, reject the candidate despite having their own separate PNGs. The same rule applies to every project art style.


## Executable reject/ignore rule

Use `scripts/gamearts_asset_lifecycle.py` internally for exact-version selection and actual rejected-to-revoked transitions. The helper rejects `revoked` records, refuses selection of a `visual_review: rejected` record, checks source references are truly approved, validates source hash and physical lifecycle folder, backs up the manifest, moves full bundles, and records explicit rejection reasons. A record marked `needs_revision` but rejected by the user must be physically transitioned to `revoked`; it is not an active generated asset. Other generated revisions stay pending until separately approved. The agent must never use a rejected asset as an active art reference or resume its animation work. A GitHub code change does not itself update a user's local project until synchronized.


## Post-approval consistency audit (no stale pending fields)

In the real Oilfield Days workshop test, v002 was correctly moved to `approved/` but its internal blueprint retained `generated_needs_visual_review`, `production_approval: not_granted`, and a contradictory clean-plate flag. These are now an **explicit lifecycle failure**.

On explicit approval of the **exact revision**, capture user-approved scope and reconstruction caveats, promote the complete original bundle and update **all** its internal approval fields consistently (manifest, blueprint, clean-plate, visual QA, validated file references). Back up prior metadata. Run the existing `scripts/gamearts_asset_lifecycle.py audit --game-root <game> --id <asset_id>` internally; its selection gate blocks reusable approved art until contradictory status fields or missing approved source files are reconciled. It does not pretend to test Godot.

Newly produced assets with independently detached props must have a separately reviewed **sprite-local silhouette mask** in their cleanup evidence; use `validate_parent_cleanup.py --strict-props` or `validate_component_bundle.py --approval-gate`. A previously user-approved asset with accepted caveats is **not automatically revoked** just because future verification becomes stricter. Keep independent version histories: v001 revoked, v002 approved with its real limitations.
