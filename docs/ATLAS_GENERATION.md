# Sprite sheets and atlases

[`scripts/build_sheet_atlas.py`](../scripts/build_sheet_atlas.py) turns approved individual frame PNGs into one sprite-sheet PNG and its measured atlas JSON. The agent runs it internally; you never type a command. The rules (exact key colour, atlas contents, what the checks do and do not prove) are in the master standard: *Masking and PNG export policy* and *Sprite sheets, atlases and component bundles*.

## Job
The agent writes a small private job next to the real approved frames (contract: [`schemas/gamearts-frames-job.schema.json`](../schemas/gamearts-frames-job.schema.json)). Illustrative; frame counts, directions and files come from the asset's approved profile:

```json
{
  "name": "game_asset_action_e_v001",
  "asset_id": "asset-001",
  "columns": 2,
  "padding": 2,
  "spacing": 0,
  "pixels_per_meter": 16,
  "duration_ms": 125,
  "source_mockups": [{"mockup_id": "scene-001", "revision": "v001"}],
  "frames": [
    {"file": "frame0.png", "name": "open_0", "direction": "E", "action": "open", "pivot": [14, 27], "anchors": {"mount": [8, 20]}},
    {"file": "frame1.png", "name": "open_1", "direction": "E", "action": "open", "pivot": [14, 27], "anchors": {"mount": [8, 20]}, "duration_ms": 200}
  ]
}
```
- `file` is relative to the job's folder. `pivot` and `anchors` are integer pixels inside the source frame (default pivot: bottom centre). Anchors are **supplied** values transformed into cell coordinates, never measured from the picture; check them against the approved master.
- `duration_ms` per frame or as the job default (125 if neither). `name` must be unique.
- `allow_near_key` (art that legitimately uses colours very close to `#FF00FF`), `full_bleed` (terrain or full-panel UI that may be painted edge to edge) and, per frame, `allow_empty` (a deliberately blank frame) are explicit opt-ins; the default is strict.

## Optional: names for runs of frames, tighter sheets, interface kits, blending
All of these are off unless the job asks for them; a job without them builds exactly as before.
- `tags`: named runs of frames, `{"name": "walk", "from": 0, "to": 5, "direction": "forward"}`. `from` and `to` are frame numbers, both included; `direction` is `forward`, `reverse`, `pingpong` or `pingpong_reverse`; `repeat` is how many times the run plays, where 0 or absent repeats forever and 1 plays once. Tag names are unique and the frames must exist. These are Aseprite's frame tags, so another tool can read them.
- `trim: true` with `pack: "shelf"`: each cell holds only that frame's art joined with its pivot (so the pivot is never cut out) plus the padding, and the cells are placed in rows of similar height up to `max_width` (2048 by default). `columns` belongs to the default grid and is refused with a shelf; trim is refused without one, because a grid has equal cells. Frames keep their job order in the atlas; each trimmed frame records `trim` (the kept box in the source picture) and `trimmed`, and the atlas says `layout: "shelf"`.
- Interface kits: per frame, `nine_slice: [left, top, right, bottom]` (pixels of the whole source frame; the centre must stay at least one pixel wide in each direction, and a nine-slice frame is never trimmed), `control` and `state` (`normal`, `hover`, `pressed`, `disabled`, `focus`) for the frames that are states of one button or slider, and `set` for a family such as an icon set. The job lists each control once in `controls`, with the states it must have: `{"name": "button", "states": ["normal", "hover", "pressed", "disabled"]}`. Every declared state needs exactly one frame, the frames of a control share size and margins, every control declares `normal`, and the frames of one `set` share a size and a padding.
- `soft_alpha: true`: the frames are true-alpha pictures from a tool that can return alpha. Each is split into key-colour art and coverage, and the sheet is delivered with a companion `<name>.matte.png` of the same size (and an atlas `matte` entry with its hash). Only for looks with soft edges; hard-edged looks never get a matte. `python scripts/gamearts_matte.py split` does the same for one picture and `check` proves a pair agrees.
- `blend_mode`: `normal`, `additive`, `subtractive`, `multiply`, `screen` or `premultiplied`, for glow, shadow and light sheets. It is advice for the game project to use; nothing here applies it.

## Run
```text
python scripts/build_sheet_atlas.py <job.json> --output-dir <candidate-folder>
python scripts/validate_sheet_atlas.py <name>.png <name>.atlas.json
```
The builder refuses a non-opaque, empty or near-key-contaminated frame, an out-of-bounds pivot, duplicate names, an invalid job and an existing output name. It places frames on one canonical pivot per cell without scaling art to a category frame, fills every unused pixel with exact opaque `#FF00FF`, checks the finished sheet against the same policy, and writes both files or neither.

## Outputs (saved together in the candidate bundle under `.gamearts/outputs/assets/generated/`)
- `<name>.png`: the sheet.
- `<name>.atlas.json` ([`schemas/gamearts-atlas.schema.json`](../schemas/gamearts-atlas.schema.json)): image size, cell size, columns, rows, per frame the cell `rect` (exclusive, top-left origin), `source_size`, `source_ink_bounds` (measured art extent), offset in cell, `pivot`, `anchors`, `duration_ms`, source file and SHA256; plus `mask_color`, `parent_attachment` for component sheets, source mockups and a `validation` block (`engine_validation: "not_tested"`).

## Other tools and the engine
`python scripts/export_exchange.py --atlas <name>.atlas.json --format aseprite-array` (or `aseprite-hash`) writes the data file Aseprite writes beside a sheet, so tools that read it can cut the frames and play the tags. Some loaders find a tag's frames by their number, so `--frame-names index` names every frame "0", "1", "2" and so on instead of by its own name. `python scripts/export_runtime.py --bundle <folder> --output-dir <folder>` makes engine-ready copies with the key colour turned into real transparency; for an approved asset the lifecycle does this (`export-runtime`) and records it. Both are explained in the master standard (*Engine-neutral integration contract*). Tilesets are in [TILESETS.md](TILESETS.md).

## What the checks prove
`validate_sheet_atlas.py` checks the schema, PNG format and size, rectangles inside the image, pivots inside their cell, no overlapping frames, exact key outside the frames and near-key contamination. Exit status 0 is **mechanical correctness only**. Atlas rectangles say nothing about whether a prop was cut cleanly (a rectangle holding a workbench and its floor is a valid atlas); each independent prop also needs the cleanup and review gates ([Component animation](COMPONENT_ANIMATION.md), master *Parent-artwork cleanup and separation gate*). They do not certify artistic quality, alignment, directional coverage or engine behavior.

## Developer test
`python -m unittest discover -s tests -p "test_build_sheet_atlas.py" -v` and `python -m unittest discover -s tests -p "test_validate_sheet_atlas.py" -v` run the focused checks (Python 3, Pillow, `jsonschema`).
