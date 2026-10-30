#!/usr/bin/env python3
"""Build the prompt packet for ONE facing of an animation strip, from the game's saved camera, directions and style.

  python scripts/gamearts_direction_prompt.py build --game-root GAME --facing E --frames 8 --action clap
         [--subject "a green tanker truck"] [--columns 8] [--cell 384x512] [--neutral-height PX] [--ground-line PX]
         [--turnaround PIC --turnaround-view "bottom row, third figure"] [--facing-reference PIC] [--timeline-reference PIC] [--background key|alpha] [--no-neutral-ends]

This is what the football project that gets its directional sprites right does by hand for every sheet (master, *Reference-controlled image prompting*,
"Consistent figures and one view angle"): one generation per facing; the approved turnaround is the identity and angle authority; the approved picture of
THIS facing is the exact camera/facing reference; the action sheet lends its timeline only; the facing is described by what shows and what must not; the
camera is the saved one and never moves, only the subject turns; the layout, the scale and the ground line are given in numbers; the first and last figure
are the neutral pose. The result is JSON: `prompt` (submit it as the actual instruction), `references` (attach these pictures in this order),
`warnings` (anchors that are missing), `layout`, and the `slice` command that cuts what the tool returns by measurement.
The settings must be owner-confirmed. A facing outside the game's directions, a camera this builder has no facing words for (it knows the oblique, the
side, the isometric and the top-down view) and a missing picture are refused, never guessed. It writes nothing. The prompt asks for a picture; whether the picture is right is the owner's judgement.

  python scripts/gamearts_direction_prompt.py repair --game-root GAME --facing SE --target STRIP --turnaround PIC --problem "too close to a side profile"
         --degrees 35 --turn toward-viewer [--turnaround-view "..."] [--frames N]
A wrong facing is repaired by an edit against the turnaround with the angle in degrees, not by asking again from scratch; only the facing may change.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import gamearts_common as common

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_CELL = (384, 512)
NEUTRAL_HEIGHT_FRACTION = 0.7
GROUND_LINE_FRACTION = 0.9
GUTTER_FRACTION = 0.12     # the empty gap asked for between neighbouring figures, as a share of the cell's width

# What shows and what must not, per facing. The camera does not move; the subject turns about its vertical axis. "Near side" is the side face that points toward the viewer.
OBLIQUE_FACINGS = {
    "S": "SOUTH, straight TOWARD the viewer: its FRONT face is flat to the camera and symmetrical, with its top surface visible from the elevated camera. Neither side face shows. Do not turn it left or right.",
    "N": "NORTH, straight AWAY from the viewer: only its REAR face and its top surface show. Its front is hidden. Neither side face shows. Do not turn it left or right.",
    "E": "EAST, facing screen RIGHT in a pure SIDE view: its side face is flat to the camera and its top surface shows from the elevated camera. Its front and rear faces are not visible. Do not turn it toward the viewer.",
    "W": "WEST, facing screen LEFT in a pure SIDE view: its side face is flat to the camera and its top surface shows from the elevated camera. Its front and rear faces are not visible. Do not turn it toward the viewer.",
    "SE": "SOUTHEAST, a three-quarter FRONT view: facing toward the viewer and screen RIGHT, turned about 45 degrees from the viewer about its vertical axis. Its front face shows on the screen-right part and its near side face on the screen-left part; the far side and the rear are hidden. Not a pure side view, not a straight front view.",
    "SW": "SOUTHWEST, a three-quarter FRONT view: facing toward the viewer and screen LEFT, turned about 45 degrees from the viewer about its vertical axis. Its front face shows on the screen-left part and its near side face on the screen-right part; the far side and the rear are hidden. Not a pure side view, not a straight front view.",
    "NE": "NORTHEAST, a three-quarter REAR view: facing away from the viewer and toward screen RIGHT. Its rear face shows on the screen-left part and its near side face on the screen-right part; its front is hidden. Not a pure side view, not a straight rear view.",
    "NW": "NORTHWEST, a three-quarter REAR view: facing away from the viewer and toward screen LEFT. Its rear face shows on the screen-right part and its near side face on the screen-left part; its front is hidden. Not a pure side view, not a straight rear view.",
}
OBLIQUE_CAMERA = ("THE CAMERA NEVER MOVES; only the subject turns. Elevated 3/4 top-down oblique orthographic: the same elevation for every facing, looking straight along the world's north axis, "
                  "so ground lines run horizontal and vertical on screen and vertical edges stay vertical. NEVER an isometric or diamond view: no 45-degree camera yaw, no two ground axes receding "
                  "diagonally, no 2:1 diamond ground. A diagonal facing is the subject rotated under this same camera, not a different camera.")
SIDE_FACINGS = {
    "E": "EAST, facing screen RIGHT, a pure SIDE view: its side face is flat to the camera; no top surface, no front or rear face visible.",
    "W": "WEST, facing screen LEFT, a pure SIDE view: its side face is flat to the camera; no top surface, no front or rear face visible.",
}
SIDE_CAMERA = "THE CAMERA NEVER MOVES. Side-view orthographic: level with the subject, no top faces, no perspective convergence, the same view for every figure."
# An isometric camera looks from the same side as the oblique one for the subject: a facing is the direction the subject points ON THE SCREEN, so the same words
# describe what shows; only the camera rule differs (the ground axes recede diagonally in the saved angle, and that never changes).
ISOMETRIC_CAMERA = ("THE CAMERA NEVER MOVES; only the subject turns. Isometric 3/4 orthographic at the saved angle: the ground axes recede diagonally in a fixed diamond, the same elevation and the same "
                    "viewing direction for every facing, vertical edges stay vertical, no perspective convergence. A facing here is the direction the subject points on the SCREEN "
                    "(south points toward the bottom of the screen), not along a ground axis.")
SCREEN_DIRECTIONS = {"S": "the bottom of the screen", "SW": "the bottom-left of the screen", "W": "the left of the screen", "NW": "the top-left of the screen",
                     "N": "the top of the screen", "NE": "the top-right of the screen", "E": "the right of the screen", "SE": "the bottom-right of the screen"}
TOP_DOWN_FACINGS = {name: f"pointing toward {where}, seen from directly above: only its top surface shows, with its front marked by the direction it points; no side, front or rear faces."
                    for name, where in SCREEN_DIRECTIONS.items()}
TOP_DOWN_CAMERA = "THE CAMERA NEVER MOVES. Directly overhead orthographic: only top surfaces show, no side faces, no perspective convergence, the same height for every figure."
CAMERAS = {"orthogonal_3_4_oblique": (OBLIQUE_FACINGS, OBLIQUE_CAMERA), "side": (SIDE_FACINGS, SIDE_CAMERA),
           "isometric_3_4": (OBLIQUE_FACINGS, ISOMETRIC_CAMERA), "top_down": (TOP_DOWN_FACINGS, TOP_DOWN_CAMERA)}
MIRRORS = {"W": "E", "NW": "NE", "SW": "SE"}


def _size(text, label):
    match = re.fullmatch(r"([1-9][0-9]{1,4})x([1-9][0-9]{1,4})", text or "")
    if not match:
        raise ValueError(f"{label} must be WIDTHxHEIGHT in pixels, such as 384x512")
    return int(match.group(1)), int(match.group(2))


def reference(root, role, path):
    """{role, path, sha256, width, height} for a picture inside the game, or ValueError."""
    from PIL import Image
    full = common.safe_member(root, str(path), f"the {role} picture")
    if full.suffix.lower() not in IMAGE_SUFFIXES or not full.is_file():
        raise ValueError(f"the {role} picture {path!r} is not a picture file (png, jpg or webp) inside the game")
    try:
        with Image.open(full) as opened:
            width, height = opened.size
            opened.verify()
    except (OSError, ValueError, SyntaxError) as exc:
        raise ValueError(f"the {role} picture {path!r} cannot be read as a picture: {exc}") from exc
    return {"role": role, "path": Path(path).as_posix(), "sha256": common.sha256_file(full), "width": width, "height": height}


def build(game_root, facing, frames, action, subject="the subject", columns=None, cell=DEFAULT_CELL, neutral_height=None, ground_line=None,
          turnaround=None, facing_reference=None, timeline_reference=None, background="key", neutral_ends=True, turnaround_view=None):
    root = common.game_root(game_root)
    settings, _, _ = common.load_project_settings(root, require_confirmed=True)
    world = settings.get("world") or {}
    profile = world.get("camera_profile")
    if profile not in CAMERAS:
        raise ValueError(f"this game's camera ({profile!r}) has no facing words in this builder (it knows {', '.join(CAMERAS)}); write the facing text yourself from the approved turnaround")
    facings, camera_rule = CAMERAS[profile]
    allowed = common.resolve_directions(settings)
    if facing not in allowed:
        raise ValueError(f"{facing} is not one of this game's directions ({', '.join(allowed) or 'none'}); change the setting or approve a limited profile first")
    if facing not in facings:
        raise ValueError(f"a {profile} camera has no {facing} facing here (it has {', '.join(facings)})")
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < 1:
        raise ValueError("frames must be a whole number of at least 1")
    columns = columns or frames
    if frames % columns:
        raise ValueError(f"{frames} frames do not fit {columns} columns")
    if background not in ("key", "alpha"):
        raise ValueError("background must be key (the exact #FF00FF) or alpha (true transparency)")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("name the action (idle, walk, clap ...)")
    rows = frames // columns
    cell_w, cell_h = cell
    height = neutral_height or round(cell_h * NEUTRAL_HEIGHT_FRACTION)
    ground = ground_line or round(cell_h * GROUND_LINE_FRACTION)
    if not 0 < height < ground < cell_h:
        raise ValueError(f"the neutral height ({height}) must be above the ground line ({ground}), which must be inside the cell ({cell_h} px tall)")
    refs = []
    for role, path in (("turnaround", turnaround), ("facing", facing_reference), ("timeline", timeline_reference)):
        if path:
            refs.append(reference(root, role, path))
    roles = {ref["role"]: number for number, ref in enumerate(refs, 1)}
    warnings = []
    if "turnaround" in roles and not (turnaround_view and turnaround_view.strip()):
        warnings.append("the turnaround's view is not named (--turnaround-view 'bottom row, third figure'): the tool has to guess which of its figures is this facing")
    if "turnaround" not in roles:
        warnings.append("no approved turnaround is attached: nothing but words fixes the figure's identity and the view angle; make and approve the turnaround first")
    if "facing" not in roles:
        warnings.append(f"no approved {facing} picture is attached: nothing but words fixes this facing's camera")
    if neutral_ends and "facing" not in roles:
        warnings.append("the first and last figures are asked to be the neutral pose, but no neutral picture of this facing is attached to copy")
    if facing in MIRRORS and MIRRORS[facing] in allowed:
        warnings.append(f"{facing} may be a mirror of an approved {MIRRORS[facing]} where the art stays correct (hair, light and marks that are not symmetrical need a drawn {facing})")
    lines = [f"Use case: identity-preserve. Create ONE animation strip of {subject} doing {action.strip()}, seen from ONE facing, for a 2D game."]
    if "turnaround" in roles:
        view = f" Match {turnaround_view.strip()} of it exactly." if turnaround_view and turnaround_view.strip() else " Match its figure for this facing exactly."
        lines.append(f"Input {roles['turnaround']} is the APPROVED turnaround: the authority for identity, anatomy, proportions and the viewing angle of every facing.{view}")
    if "facing" in roles:
        lines.append(f"Input {roles['facing']} is the approved neutral picture of THIS facing: the exact identity, anatomy and CAMERA/FACING reference. Keep its camera, elevation and proportions.")
    if "timeline" in roles:
        lines.append(f"Input {roles['timeline']} is ONLY the approved action timeline, spacing and colour reference. Do NOT inherit its camera or facing.")
    lines += [f"FACING FOR THIS ENTIRE SHEET: {facings[facing]}", f"CAMERA: {world.get('object_camera') or profile}. {camera_rule}"]
    style = settings.get("art_style") or {}
    if style.get("id"):
        policy = " ".join(str(style[key]) for key in ("outline_policy", "shading_policy", "texture_policy", "pixel_density") if style.get(key))
        lines.append(f"STYLE (saved, do not change): {style['id']}. {policy}".strip())
    lines.append("IDENTITY: one unchanged subject rotated about its vertical axis, NOT new interpretations. Keep every part, proportion, colour and mark of the approved design; do not add or remove details.")
    gutter = max(8, round(cell_w * GUTTER_FRACTION))
    lines.append(f"LAYOUT: EXACTLY {frames} complete figures, {'in ONE horizontal row' if rows == 1 else f'in {rows} rows of {columns}'}, in reading order. The canvas is {cell_w * columns}x{cell_h * rows} pixels: "
                 f"equal cells {cell_w}x{cell_h}, each figure whole and centred in its own cell, with at least {gutter} pixels of completely empty background on both sides of every figure through the full height. "
                 "Nothing touches a neighbouring cell or the picture's edge; no clipped parts, stray dots or shared outlines.")
    lines.append(f"SCALE: one scale for ALL figures. The neutral pose is about {height} pixels tall and its lowest planted point stands on the line {ground} pixels below the top of each cell. "
                 "Never resize a figure between frames; a pose that lowers or lifts the subject does so without changing its size.")
    if neutral_ends:
        lines.append("The FIRST and LAST figures are identical copies of the approved neutral pose of this facing, with the same registration and size, so the loop closes on it.")
    lines.append("BACKGROUND: " + ("a solid pure #FF00FF background (that exact colour) with nothing else on it, no shadow and no gradient." if background == "key" else "genuine transparent alpha."))
    lines.append("NOT ALLOWED: text, labels, grid lines, props, ground, baked shadow, border, watermark, a second subject, a different design, a different camera.")
    command = (f"python scripts/slice_generated_strip.py --source <the picture the tool returned> --frames {frames} --columns {columns} --out <new folder> --name <sheet name> "
               f"--direction {facing} --action {action.strip().replace(' ', '_')}" + (" --reference <the approved neutral picture of this facing>" if "facing" in roles else ""))
    return {"facing": facing, "camera_profile": profile, "prompt": "\n".join(lines), "references": refs, "warnings": warnings,
            "layout": {"frames": frames, "columns": columns, "rows": rows, "cell": [cell_w, cell_h], "canvas": [cell_w * columns, cell_h * rows], "neutral_height": height, "ground_line": ground, "gutter": gutter},
            "slice": command, "not_assessed": ["whether the picture the tool returns shows this facing and the approved figure: a person compares it with the turnaround"]}


TURNS = {"toward-viewer": "toward the viewer", "away-from-viewer": "away from the viewer", "toward-screen-left": "toward screen left", "toward-screen-right": "toward screen right"}


def repair(game_root, facing, target, turnaround, problem, degrees, turn, turnaround_view=None, frames=None):
    """The edit prompt that corrects ONLY the facing of a strip against the approved turnaround, with the angle in degrees. Judging the result is a person's job."""
    root = common.game_root(game_root)
    settings, _, _ = common.load_project_settings(root, require_confirmed=True)
    world = settings.get("world") or {}
    profile = world.get("camera_profile")
    if profile not in CAMERAS:
        raise ValueError(f"this game's camera ({profile!r}) has no facing words in this builder (it knows {', '.join(CAMERAS)})")
    facings, camera_rule = CAMERAS[profile]
    if facing not in common.resolve_directions(settings) or facing not in facings:
        raise ValueError(f"{facing} is not one of this game's directions with a {profile} camera")
    if not isinstance(degrees, int) or isinstance(degrees, bool) or not 1 <= degrees <= 90:
        raise ValueError("degrees must be a whole number from 1 to 90")
    if turn not in TURNS:
        raise ValueError(f"turn must be one of {', '.join(TURNS)}")
    if not isinstance(problem, str) or not problem.strip():
        raise ValueError("say what is wrong with the current facing (for example: too close to a right side profile)")
    refs = [reference(root, "edit-target", target), reference(root, "turnaround", turnaround)]
    view = f", matching {turnaround_view.strip()}" if turnaround_view and turnaround_view.strip() else ""
    count = f" all {frames}" if frames else " ALL"
    lines = ["Use case: precise-object-edit.",
             "Image 1 is the EDIT TARGET, the strip to correct. Image 2 is the approved turnaround and the required viewing-angle reference" + view + ".",
             f"Correct ONLY the facing/camera relationship for{count} figures in image 1. The current result is wrong: {problem.strip()}. It must be {facings[facing]}",
             f"Rotate each same subject about its vertical axis about {degrees} degrees {TURNS[turn]} from its present orientation, as a complete articulated body: every part follows the new facing, not just the front.",
             f"CAMERA, unchanged: {world.get('object_camera') or profile}. {camera_rule}",
             "Preserve identity, proportions, colours, shading style, camera elevation, one scale for every figure, the number of figures, their order, the layout and canvas size, the gutters between them, and the action of every figure. Change nothing else."]
    return {"facing": facing, "prompt": "\n".join(lines), "references": refs, "warnings": [],
            "not_assessed": ["whether the corrected picture now matches the turnaround: a person compares them; playback or measurement logs are not facing acceptance"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="op", required=True)
    one = sub.add_parser("build", help="The prompt packet for one facing")
    one.add_argument("--game-root", type=Path, required=True)
    one.add_argument("--facing", required=True, help="One of the game's directions: S, SW, W, NW, N, NE, E, SE")
    one.add_argument("--frames", type=int, required=True)
    one.add_argument("--action", required=True)
    one.add_argument("--subject", default="the subject", help="What is drawn, in the owner's words (a tanker truck, the hero)")
    one.add_argument("--columns", type=int)
    one.add_argument("--cell", default=f"{DEFAULT_CELL[0]}x{DEFAULT_CELL[1]}", help="One figure's cell, WIDTHxHEIGHT")
    one.add_argument("--neutral-height", type=int)
    one.add_argument("--ground-line", type=int)
    one.add_argument("--turnaround", help="The approved turnaround picture, inside the game")
    one.add_argument("--facing-reference", help="The approved neutral picture of this facing, inside the game")
    one.add_argument("--timeline-reference", help="The approved action sheet that lends the timeline only")
    one.add_argument("--background", choices=("key", "alpha"), default="key")
    one.add_argument("--turnaround-view", help="Which figure of the turnaround is this facing, in words: 'bottom row, third figure'")
    one.add_argument("--no-neutral-ends", action="store_true", help="The strip is not a loop that returns to the neutral pose")
    fix = sub.add_parser("repair", help="The edit prompt that corrects only the facing of a strip against the turnaround")
    fix.add_argument("--game-root", type=Path, required=True)
    fix.add_argument("--facing", required=True)
    fix.add_argument("--target", required=True, help="The strip to correct, inside the game")
    fix.add_argument("--turnaround", required=True, help="The approved turnaround, inside the game")
    fix.add_argument("--turnaround-view")
    fix.add_argument("--problem", required=True, help="What is wrong with the facing, in plain words")
    fix.add_argument("--degrees", type=int, required=True, help="How far to rotate the subject about its vertical axis, 1 to 90")
    fix.add_argument("--turn", required=True, choices=tuple(TURNS))
    fix.add_argument("--frames", type=int, help="How many figures the strip holds")
    args = parser.parse_args(argv)
    try:
        if args.op == "repair":
            print(json.dumps(repair(args.game_root, args.facing, args.target, args.turnaround, args.problem, args.degrees, args.turn, args.turnaround_view, args.frames), indent=2))
            return 0
        result = build(args.game_root, args.facing, args.frames, args.action, args.subject, args.columns, _size(args.cell, "--cell"), args.neutral_height, args.ground_line,
                       args.turnaround, args.facing_reference, args.timeline_reference, args.background, not args.no_neutral_ends, args.turnaround_view)
    except ValueError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
