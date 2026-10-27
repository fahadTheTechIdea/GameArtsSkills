# Lifecycle formats and records

The rules for the generated, approved and revoked lifecycles of mockups and assets are in the master standard (*Asset and mockup lifecycle*, *External and user-supplied mockups*); the operations an agent runs are listed in the `game-arts-lifecycle` skill. This page shows the records. You never edit them by hand.

```text
.gamearts/outputs/
  mockups/{generated,approved,revoked}/     assets/{generated,approved,revoked}/
  manifests/{mockups.json,assets.json}
```
An approved mockup is a visual reference, **not** an approved sprite or atlas: it must first be decomposed into a blueprint, and every production asset records the exact approved mockup revision it came from. One approved scene can feed many assets; one complex asset can draw on several mockups.

Names are descriptive and game-related, for example `gamea_scene_market-street_mockup_v001.png`, `gamea_market-street-lamp_idle_e_v002.png` and `gamea_market-street-lamp_idle_e_v002.atlas.json`. `mockup_id` and `asset_id` stay stable; `vNNN` is the artifact revision.

## Mockup metadata and record
Metadata (`<image-stem>.metadata.json`, [`schemas/gamearts-mockup-metadata.schema.json`](../schemas/gamearts-mockup-metadata.schema.json)) is the generation record:
```json
{
  "schema_version": "1.0", "mockup_id": "market-street", "revision": "v001", "scope": "scene", "status": "generated",
  "file": ".gamearts/outputs/mockups/generated/gamea_scene_market-street_mockup_v001.png", "sha256": "<image sha256>",
  "prompt": "<the actual image-tool prompt>", "prompt_origin": "agent_brief", "imagegen_prompt_captured": true,
  "tool_mode": "built_in_image_gen", "created_at_utc": "2026-10-23T12:00:00Z",
  "storyboard_scene_id": "arrival",
  "provenance": {"provider": "...", "model": "...", "seed": 1234},
  "rights": {"status": "owned", "notes": ""}
}
```
The agent does not write this file for a picture an image tool just made: `register-generated --image <the tool's PNG> --prompt-file <the prompt actually sent>` names the file, hashes it, writes this record and registers it, using the game's saved image generator. `tool_mode` is `built_in_image_gen`, `cli_image_gen`, `connected_tool` (which also needs `tool_name`) or `external_import`; `register` refuses a generated mockup whose tool differs from the game's `image_generation` setting (an import is always accepted). A mockup made outside Game Arts is brought in with `import-mockup`, which writes this record for you (`tool_mode` `external_import`, `prompt_origin` `external_provider`, a prompt that says no generation prompt exists, the original file's name, hash and format under `source_references`) and never changes the original. `scope` is one of `world`, `scene`, `asset`, `character`, `ui_screen`, `ui_flow`, `mixed`; `tool_mode` one of `built_in_image_gen`, `cli_image_gen`, `external_import`; `storyboard_scene_id`, `provenance` and `rights` are optional. The metadata file stays the generation record: its own `status` stays `generated` for good, and the manifest owns the lifecycle status. `register` copies the record into [`mockups.json`](../schemas/gamearts-mockups-manifest.schema.json), which owns the lifecycle `status` and stores the canonical material-settings hash, artifact hashes and, after approval, the approval reference and time.

## Asset record
```json
{
  "asset_id": "workshop", "revision": "v001", "status": "approved",
  "bundle_path": ".gamearts/outputs/assets/approved/workshop_v001",
  "files": ["workshop_v001_sheet.png", "workshop_v001_sheet.atlas.json", "cleanup/workshop/cleanup.json"],
  "source_mockups": [{"mockup_id": "market-street", "revision": "v001", "reference_sha256": "<approved mockup sha256>"}],
  "approval": "user_granted", "visual_review": "approved", "approval_reference": "<user's approving message>",
  "technical_validation": {"status": "passed", "bundle_gate": "not_applicable", "atlases": ["workshop_v001_sheet.atlas.json"], "issues": []},
  "engine_validation": "not_tested",
  "visual_review_protocol": "review_packet",
  "visual_reviews": [{"packet": "visual_review/visual_review.packet.json", "decision": "visual_review/decision.json"}],
  "artifact_hashes": {"workshop_v001_sheet.png": "<sha256>"}
}
```
Contract: [`schemas/gamearts-assets-manifest.schema.json`](../schemas/gamearts-assets-manifest.schema.json). `files` and `visual_reviews` paths are relative to the bundle (nested folders allowed, nothing may escape it), so they stay valid when the bundle moves from generated to approved or revoked. `visual_reviews` is required for composite assets (the earlier spelling `review_packet_v1` in the protocol field is still read). `artifact_hashes` is written at approval, so a later change to any file blocks reuse. Revoked records carry `revocation_reason`, `revoked_at_utc` and optionally `replaced_by`; restored ones carry `restored_from`.

## Engine-ready copies are derived, not approved
For an approved asset, `export-runtime` writes copies of its sheets in which the key colour is real transparency, into `.gamearts/outputs/runtime/<asset id>/<revision>/` with a `runtime.export.json` that lists every file with its hash and the hash of the file it came from. The record gains `derived_exports: [{"kind": "runtime", "path": "...", "manifest_sha256": "...", "status": "derived"}]`. They live outside the status folders on purpose: they are never approved, never a source for new art, `reconcile-assets` checks them (a changed or stale copy is reported), and revoking the asset deletes them. A game whose engine profile asks for them gets them when the asset is approved; the result says whether that worked, and a failure never undoes the approval.

## Reference crops stay in the asset candidate
Source conditioning creates no new lifecycle: the crop (`reference/<asset>_reference_crop.png`), `reference/reference.packet.json`, `reference/reference.prompt.txt` and, after a real image-tool call, a receipt live in the candidate's `reference/` folder, tied to the asset, the source mockup hash and the measured region. A crop keeps the original screenshot colours (it is reference content, not a key-colour sprite) and a passing receipt never approves anything.

## Checks that gate approval
Technical (`approve` runs them; `audit` re-checks files, hashes, source links and contradictory fields): a real sheet atlas, exact key colour on every sheet, the bundle approval gate and the parent-cleanup proof for composite assets. Visual: the review packet and the user's hash-bound decision. Engine: never claimed by approval; the game project reports `engine_validation`. Previously approved art is not revoked because a later gate is stricter; `audit` labels such records legacy.
