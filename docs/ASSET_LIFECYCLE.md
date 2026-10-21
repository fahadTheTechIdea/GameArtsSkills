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

See [master standard v7.3](../GAME_ARTS_MASTER_STANDARD_v7.4.md).
