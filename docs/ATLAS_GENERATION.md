# Automatic sprite-sheet and atlas generation

**Game Arts now has an actual sprite-sheet and JSON atlas builder** at [scripts/build_sheet_atlas.py](../scripts/build_sheet_atlas.py). Claude Code or Codex should run it internally whenever generating a multi-frame sprite sheet. The user should not need to run commands or manually create an atlas.

## Input: approved individual frames

The agent prepares a small private job file in the working game project after the approved mockup has been decomposed and the locked frame art created.

Example `frames.json` (illustrative; source images must exist):

```json
{
  "name": "game_asset_action_e_v001",
  "asset_id": "asset-001",
  "columns": 6,
  "padding": 2,
  "spacing": 0,
  "pixels_per_meter": 16,
  "source_mockups": [{"mockup_id":"scene-001","revision":"v001"}],
  "frames": [
    {"file":"frame0.png","direction":"E","action":"open","pivot":[14,27],"anchors":{"mount":[8,20]},"duration_ms":125},
    {"file":"frame1.png","direction":"E","action":"open","pivot":[14,27],"anchors":{"mount":[8,20]},"duration_ms":125}
  ]
}
```

The example has two frames (not six); actual counts, directions and image files are chosen by the approved asset profile.

A batch can contain all frames for a sheet and have an arbitrary column count. For a directional base sheet, use the approved direction order and suitable layout; for an action/direction animation sheet, use a horizontal row if the active profile requires it.

## Outputs

For one job, the tool creates **two individual files** together:

- `<descriptive-game-asset-name>.png`
- `<same-name>.atlas.json`

Both should be saved under `<game>/.gamearts/outputs/assets/generated/` (or an associated candidate bundle subfolder). Approval and promotion must be handled by the lifecycle skill, including all component resources.

The atlas includes real final canvas/cell dimensions, per-frame rects, source size and source pixel bounding boxes, frame-local pivot and provided attachment anchor coordinates, timing, source hashes and provenance references. Components may supply `parent_attachment` and `attachment_tracks` metadata.

**Do not mistake user-supplied anchor values for computer-vision measurements.** The builder accurately transforms supplied source-frame coordinates into atlas-cell coordinates; it does not infer the correct physical mount from an image. The agent must inspect and validate those anchors against the approved master.

## Validation limits

The builder rejects non-opaque source PNGs, invalid coordinate formats and pre-existing output names. It fills unused sheet space with exact opaque #FF00FF and never scales artwork to fit a category-sized frame.

A separate validator checks atlas rectangles and alpha; the builder's JSON does **not** certify the image's artistic quality, parent-child alignment, full directional coverage, or performance inside Godot. Those require specialist validation and real engine tests.

Run internal build and verification scripts automatically when capable; do not make the user type shell commands.

## Developer test

Install Pillow, then run `python -m unittest discover -s tests -v`. The tests use synthetic PNGs and check pivot alignment, frame geometry, mask opacity, anchor conversion, and rejection conditions.


## Lessons from real production extraction

Actual measured PNG and atlas rectangles prove sheet geometry, **not** that a detachable object was cleanly cut. A rectangle containing a workbench and its floor pixels can still have a mathematically correct atlas. For each new independent prop, require a separately reviewed sprite-local silhouette mask and run strict parent-cleanup checks before using the sprite as approved production artwork. Verify real pixel dimensions and hashes of the current revision, not frames from a rejected prior version. Keep the approved source mockup revision and original source hashes in provenance. Preserve inferred/retouched pixel notes (for occluded surfaces or JPEG edge fringes) and manual approval separately from engine testing.
