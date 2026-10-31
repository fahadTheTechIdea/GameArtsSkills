#!/usr/bin/env python3
"""Prompt packets for directional sprite art, built from the game's saved camera, directions and style. Writes nothing; submitting the prompt is the agent's step.

  turnaround   the ONE approved model sheet (every facing, in a fixed arrangement) that every later prompt names a figure of
  plan         which facings to draw and which to mirror, and which one to draw first
  build        one strip/grid for ONE facing: references in order, what shows and what must not, the layout, scale and ground line in numbers
  inbetween    the in-between poses of an approved set of keyposes (a cycle is made as keyposes first, then in-betweens)
  repair       the edit that corrects only a wrong facing against the turnaround, with the angle in degrees
  respace      the edit that corrects only the spacing of a strip (clipped or crowded figures), never the poses
  fix          the edit that changes only the items named and keeps every other pixel

This is how the football project whose directional sprites come out right does it (master, *Reference-controlled image prompting*, "Consistent figures
and one view angle"): one approved turnaround is the identity and angle authority and is attached to every prompt with the exact figure named; one
generation per facing with the approved neutral picture of that facing as the camera authority; the action sheet lends its timeline only; the facing is
described by what shows and what must not; the camera is repeated in every prompt and edit and never moves; the canvas is one the image tool really
returns (it ignores other sizes), with the neutral height and ground line in numbers and as percentages; a wrong facing or crowded spacing is repaired by
a limited edit, never by asking again from scratch. A person judges every picture: nothing here measures whether a facing is right.
The settings must be owner-confirmed. A facing outside the game's directions, a camera without facing words (`custom`) and a missing or foreign picture are refused.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import gamearts_common as common

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
# Sizes image tools were seen to return (the football project's records and this framework's own runs); a tool does not honour another size, so the cell is derived from one of these.
CANVASES = {"3:2": (1536, 1024), "3:1": (2172, 724), "1:1": (1254, 1254)}
MAX_ROW = 6               # figures per row that came back whole; a one-row strip of eight came back clipped and needed a spacing pass
NEUTRAL_HEIGHT_FRACTION = 0.70
GROUND_LINE_FRACTION = 0.89
GUTTER_FRACTION = 0.12    # the empty gap asked for beside every figure, as a share of the cell's width
TURNAROUND_ORDER = ("E", "NE", "N", "NW", "W", "SW", "S", "SE")    # counter-clockwise from east, four to a row
TURNAROUND_COLUMNS = 4
ORDINALS = ("first", "second", "third", "fourth")
MIRRORS = {"W": "E", "NW": "NE", "SW": "SE"}
PILOT_ORDER = ("E", "S", "SE", "NE", "N")

# What shows and what must not, per facing and per KIND of subject. The camera does not move; the subject turns about its vertical axis.
# A human is described by its features, as the football project does ("only back of head, jersey and heels, never a frontal chest").
HUMAN_FACINGS = {
    "S": "SOUTH, straight TOWARD the viewer, DIRECT FRONT view: the whole face and front of the body show, shoulders square to the camera, centred and symmetric, both knees and toes toward the viewer. Do NOT turn left or right; no side profile, no back.",
    "N": "NORTH, directly AWAY from the viewer, STRAIGHT REAR view: show ONLY the back of the head, the back of the body and the heels. NO face, cheek or front of the chest in any pose. Shoulders square to the camera, both feet pointing straight away.",
    "E": "EAST, facing screen RIGHT in a pure SIDE view (profile): the whole body in profile, both feet pointing screen right, shoulders in line with the view. Do not turn toward the viewer.",
    "W": "WEST, facing screen LEFT in a pure SIDE view (profile): the whole body in profile, both feet pointing screen left, shoulders in line with the view. Do not turn toward the viewer.",
    "SE": "SOUTHEAST, toward the viewer and toward SCREEN RIGHT, THREE-QUARTER FRONT view, turned about 45 degrees from the viewer. The broad front of the face and front of the body show, turned partly to screen right, with a visible side of the head and both shoulders; the far side somewhat narrower. Both feet point diagonally toward the lower right. The centre of the face points diagonally toward the lower right, NOT horizontally to the right. Do NOT show the back. Not a profile, not a direct front view.",
    "SW": "SOUTHWEST, toward the viewer and toward SCREEN LEFT, THREE-QUARTER FRONT view, turned about 45 degrees from the viewer. The broad front of the face and front of the body show, turned partly to screen left, with a visible side of the head and both shoulders; the far side somewhat narrower. Both feet point diagonally toward the lower left. The centre of the face points diagonally toward the lower left, NOT horizontally to the left. Do NOT show the back. Not a profile, not a direct front view.",
    "NE": "NORTHEAST, away from the viewer and toward SCREEN RIGHT, THREE-QUARTER REAR view. Show mainly the back of the body and the back of the head, with only a little of the side of the cheek and ear on screen right. Both feet point diagonally away to the right. Never show a frontal chest or the full face in any frame.",
    "NW": "NORTHWEST, away from the viewer and toward SCREEN LEFT, THREE-QUARTER REAR view. Show mainly the back of the body and the back of the head, with only a little of the side of the cheek and ear on screen left. Both feet point diagonally away to the left. Never show a frontal chest or the full face in any frame.",
}
HUMAN_SIDE_FACINGS = {
    "E": "EAST, facing screen RIGHT, a pure SIDE view (profile): the whole body in profile, both feet pointing screen right.",
    "W": "WEST, facing screen LEFT, a pure SIDE view (profile): the whole body in profile, both feet pointing screen left.",
}
# Animals, vehicles and buildings have a front, a rear and sides, each with parts of its own.
PARTS = {
    "animal": {"front": "its FRONT (the face, the chest and both front legs)", "rear": "its REAR (the tail, the hindquarters, the back of the head and the ears)",
               "side": "its whole body in profile (the head, the torso, the tail and the legs on the near side), the head toward screen {dir}", "top": "Its back shows from the elevated camera."},
    "vehicle": {"front": "its FRONT (the grille, the headlights, the windscreen and the bonnet)", "rear": "its REAR (the rear lights, the rear doors or tailgate, the rear bumper and the rear wheels)",
                "side": "its SIDE (the doors, the side windows and both wheels on that side) flat to the camera, the front toward screen {dir}", "top": "Its roof shows from the elevated camera."},
    "building": {"front": "its main FRONT facade with the entrance", "rear": "its BACK wall",
                 "side": "one SIDE wall flat to the camera, the front facade at the {dir} end of it", "top": "Its roof shows from the elevated camera."},
}


def _faced(parts, elevated=True):
    """The eight facings of a subject with a front, a rear and sides."""
    top = parts["top"] if elevated else "No top surface shows."
    front, rear = parts["front"], parts["rear"]
    start_front, start_rear = front[0].upper() + front[1:], rear[0].upper() + rear[1:]  # the diagonal facings begin a sentence with the part
    return {
        "S": f"SOUTH, straight TOWARD the viewer, DIRECT FRONT view: {front} faces the camera, flat and symmetrical. {top} Neither side shows. Do not turn it left or right.",
        "N": f"NORTH, straight AWAY from the viewer, STRAIGHT REAR view: only {rear} shows. {top} Its front is hidden and neither side shows. Do not turn it left or right.",
        "E": f"EAST, facing screen RIGHT, a pure SIDE view: {parts['side'].format(dir='RIGHT')}. {top} Its front and rear are not visible. Do not turn it toward the viewer.",
        "W": f"WEST, facing screen LEFT, a pure SIDE view: {parts['side'].format(dir='LEFT')}. {top} Its front and rear are not visible. Do not turn it toward the viewer.",
        "SE": f"SOUTHEAST, a three-quarter FRONT view: toward the viewer and screen RIGHT, turned about 45 degrees about its vertical axis. {start_front} shows on the screen-right part and its near side on the screen-left part; the far side and the rear are hidden. {top} Not a pure side view, not a direct front view.",
        "SW": f"SOUTHWEST, a three-quarter FRONT view: toward the viewer and screen LEFT, turned about 45 degrees about its vertical axis. {start_front} shows on the screen-left part and its near side on the screen-right part; the far side and the rear are hidden. {top} Not a pure side view, not a direct front view.",
        "NE": f"NORTHEAST, a three-quarter REAR view: away from the viewer and toward screen RIGHT. {start_rear} shows on the screen-left part and its near side on the screen-right part; its front is hidden. {top} Not a pure side view, not a direct rear view.",
        "NW": f"NORTHWEST, a three-quarter REAR view: away from the viewer and toward screen LEFT. {start_rear} shows on the screen-right part and its near side on the screen-left part; its front is hidden. {top} Not a pure side view, not a direct rear view.",
    }


def _structure(elevated=True):
    """A bridge, tower, fence, pipeline or derrick has no front: it has a long axis, and a facing is where that axis points."""
    top = "Its top surface shows from the elevated camera." if elevated else "No top surface shows."
    return {
        "S": f"SOUTH: its long axis points straight TOWARD the viewer, so one END face is flat to the camera and foreshortened, and neither long side shows. {top} Do not turn it.",
        "N": f"NORTH: its long axis points straight AWAY from the viewer, so the opposite END face is flat to the camera and foreshortened, and neither long side shows. {top} Do not turn it.",
        "E": f"EAST: its long axis runs left-right across the screen, one long SIDE flat to the camera and both end faces hidden; the end that carries its main mark is at the RIGHT. {top}",
        "W": f"WEST: its long axis runs left-right across the screen, one long SIDE flat to the camera and both end faces hidden; the end that carries its main mark is at the LEFT. {top}",
        "SE": f"SOUTHEAST: turned about 45 degrees, its long axis runs from the upper left (far end) to the lower right (near end): the near END face shows at the lower right and one long side on the left. {top}",
        "SW": f"SOUTHWEST: turned about 45 degrees, its long axis runs from the upper right (far end) to the lower left (near end): the near END face shows at the lower left and one long side on the right. {top}",
        "NE": f"NORTHEAST: turned about 45 degrees, its long axis runs from the lower left (near end) to the upper right (far end): the far END face shows and one long side on the right, the near end hidden. {top}",
        "NW": f"NORTHWEST: turned about 45 degrees, its long axis runs from the lower right (near end) to the upper left (far end): the far END face shows and one long side on the left, the near end hidden. {top}",
    }


def _plant(elevated=True):
    """A plant has no front: a facing is the side of the same plant that turns toward the viewer, its base planted on one point."""
    keep = "the SAME plant turned about its trunk or stem, its base planted on the same point; its branch and leaf masses show from that side as they would on a real plant; do not add, remove or move branches, leaves, fruit or flowers beyond that."
    top = " The top of the crown shows from the elevated camera." if elevated else ""
    where = {"S": "its chosen FRONT side faces the viewer", "N": "its BACK side faces the viewer", "E": "its right-hand side faces the viewer in profile", "W": "its left-hand side faces the viewer in profile",
             "SE": "its front-right side faces the viewer, turned about 45 degrees", "SW": "its front-left side faces the viewer, turned about 45 degrees",
             "NE": "its back-right side faces the viewer, turned about 45 degrees", "NW": "its back-left side faces the viewer, turned about 45 degrees"}
    names = {"S": "SOUTH", "N": "NORTH", "E": "EAST", "W": "WEST", "SE": "SOUTHEAST", "SW": "SOUTHWEST", "NE": "NORTHEAST", "NW": "NORTHWEST"}
    return {key: f"{names[key]}: {where[key]}; {keep}{top}" for key in where}


KINDS = ("human", "animal", "vehicle", "building", "structure", "plant")
HEAD_KINDS = ("human", "animal")   # a subject with a head is judged by its head width: a posed height changes when it crouches or jumps, a head does not
CROWN_PERCENT = 30                # the football project measures the widest run of art in the top 30% of the figure
KIND_WORDS = {"human": "a person or humanoid", "animal": "an animal", "vehicle": "a vehicle", "building": "a building", "structure": "a structure with a long axis (bridge, tower, fence, pipeline, derrick)", "plant": "a plant"}


def facings_for(kind, elevated=True):
    """The eight facings of a kind of subject: what shows and what must not, with the parts that kind really has."""
    if kind == "human":
        return HUMAN_FACINGS if elevated else HUMAN_SIDE_FACINGS
    if kind == "structure":
        return _structure(elevated)
    if kind == "plant":
        return _plant(elevated)
    if kind in PARTS:
        return _faced(PARTS[kind], elevated)
    raise ValueError(f"say what kind of subject this is: {', '.join(f'{name} ({words})' for name, words in KIND_WORDS.items())}")


SCREEN_DIRECTIONS = {"S": "the bottom of the screen", "SW": "the bottom-left of the screen", "W": "the left of the screen", "NW": "the top-left of the screen",
                     "N": "the top of the screen", "NE": "the top-right of the screen", "E": "the right of the screen", "SE": "the bottom-right of the screen"}
TOP_DOWN_FACINGS = {name: f"pointing toward {where}, seen from directly above: only its top surface shows, with its front marked by the direction it points; no side, front or rear faces."
                    for name, where in SCREEN_DIRECTIONS.items()}
OBLIQUE_CAMERA = ("THE CAMERA NEVER MOVES; only the subject turns. Elevated 3/4 top-down oblique orthographic: the same elevation for every facing, looking straight along the world's north axis, "
                  "so ground lines run horizontal and vertical on screen and vertical edges stay vertical. NEVER an isometric or diamond view: no 45-degree camera yaw, no two ground axes receding "
                  "diagonally, no 2:1 diamond ground. A diagonal facing is the subject rotated under this same camera, not a different camera.")
SIDE_CAMERA = "THE CAMERA NEVER MOVES. Side-view orthographic: level with the subject, no top faces, no perspective convergence, the same view for every figure."
ISOMETRIC_CAMERA = ("THE CAMERA NEVER MOVES; only the subject turns. Isometric 3/4 orthographic at the saved angle: the ground axes recede diagonally in a fixed diamond, the same elevation and the same "
                    "viewing direction for every facing, vertical edges stay vertical, no perspective convergence. A facing here is the direction the subject points on the SCREEN "
                    "(south points toward the bottom of the screen), not along a ground axis.")
TOP_DOWN_CAMERA = "THE CAMERA NEVER MOVES. Directly overhead orthographic: only top surfaces show, no side faces, no perspective convergence, the same height for every figure."
CAMERAS = {"orthogonal_3_4_oblique": (OBLIQUE_CAMERA, True), "side": (SIDE_CAMERA, False), "isometric_3_4": (ISOMETRIC_CAMERA, True), "top_down": (TOP_DOWN_CAMERA, None)}
LOOPS = ("neutral", "cycle", "none")
TURNS = {"toward-viewer": "toward the viewer", "away-from-viewer": "away from the viewer", "toward-screen-left": "toward screen left", "toward-screen-right": "toward screen right"}


class Game:
    """The saved settings every prompt is written from: camera wording, the facing table for the subject, the directions and the style."""

    def __init__(self, game_root, kind=None, facings_needed=True):
        if facings_needed and kind not in KINDS:
            raise ValueError(f"say what kind of subject this is, because each shows different parts from each facing: {', '.join(f'{name} ({words})' for name, words in KIND_WORDS.items())}")
        self.root = common.game_root(game_root)
        self.settings, _, _ = common.load_project_settings(self.root, require_confirmed=True)
        self.world = self.settings.get("world") or {}
        self.profile = self.world.get("camera_profile")
        if self.profile not in CAMERAS:
            raise ValueError(f"this game's camera ({self.profile!r}) has no facing words in this builder (it knows {', '.join(CAMERAS)}); write the facing text yourself from the approved turnaround")
        self.camera_rule, elevated = CAMERAS[self.profile]
        self.facings = (TOP_DOWN_FACINGS if elevated is None else facings_for(kind, elevated)) if facings_needed else {}
        if self.profile == "side":  # a side camera sees only the two sides
            self.facings = {name: text for name, text in self.facings.items() if name in ("E", "W")}
        self.directions = common.resolve_directions(self.settings)

    def facing(self, name):
        if name not in self.directions:
            raise ValueError(f"{name} is not one of this game's directions ({', '.join(self.directions) or 'none'}); change the setting or approve a limited profile first")
        if name not in self.facings:
            raise ValueError(f"a {self.profile} camera has no {name} facing here (it has {', '.join(self.facings)})")
        return self.facings[name]

    def camera(self):
        return f"{self.world.get('object_camera') or self.profile}. {self.camera_rule}"

    def style(self):
        style = self.settings.get("art_style") or {}
        if not style.get("id"):
            return None
        policy = " ".join(str(style[key]) for key in ("outline_policy", "shading_policy", "texture_policy", "pixel_density") if style.get(key))
        return f"STYLE (saved, do not change): {style['id']}. {policy}".strip()

    def reference(self, role, path):
        """{role, path, sha256, width, height} for a picture inside the game, or ValueError."""
        from PIL import Image
        full = common.safe_member(self.root, str(path), f"the {role} picture")
        if full.suffix.lower() not in IMAGE_SUFFIXES or not full.is_file():
            raise ValueError(f"the {role} picture {path!r} is not a picture file (png, jpg or webp) inside the game")
        try:
            with Image.open(full) as opened:
                width, height = opened.size
                opened.verify()
        except (OSError, ValueError, SyntaxError) as exc:
            raise ValueError(f"the {role} picture {path!r} cannot be read as a picture: {exc}") from exc
        return {"role": role, "path": Path(path).as_posix(), "sha256": common.sha256_file(full), "width": width, "height": height}


def _size(text, label):
    match = re.fullmatch(r"([1-9][0-9]{1,4})x([1-9][0-9]{1,4})", text or "")
    if not match:
        raise ValueError(f"{label} must be WIDTHxHEIGHT in pixels, such as 1536x1024")
    return int(match.group(1)), int(match.group(2))


def turnaround_rows(directions):
    """The arrangement `turnaround` asks for and `--turnaround-view auto` names: the game's facings, counter-clockwise from east, four to a row."""
    order = [name for name in TURNAROUND_ORDER if name in directions]
    return [order[start:start + TURNAROUND_COLUMNS] for start in range(0, len(order), TURNAROUND_COLUMNS)]


def turnaround_view(directions, facing):
    rows = turnaround_rows(directions)
    for number, row in enumerate(rows):
        if facing in row:
            where = "the only row" if len(rows) == 1 else ("the top row" if number == 0 else "the bottom row" if number == len(rows) - 1 else f"row {number + 1}")
            return f"{where}, {ORDINALS[row.index(facing)]} figure"
    raise ValueError(f"{facing} is not on the turnaround of this game's directions")


def layout(frames, columns=None, canvas=None, neutral_height=None, ground_line=None):
    """The canvas, the grid and the numbers a prompt states. The canvas is one the image tool returns: a one-row strip of up to six uses the 3:1 size, a grid the 3:2 size."""
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < 1:
        raise ValueError("frames must be a whole number of at least 1")
    if columns is None:
        columns = next(count for count in range(min(frames, MAX_ROW), 0, -1) if frames % count == 0)
        if frames > 1 and columns < 2:
            raise ValueError(f"{frames} frames do not divide into rows of 2 to {MAX_ROW} figures; use a count such as 4, 6, 8, 12 or 18")
    if columns < 1 or frames % columns:
        raise ValueError(f"{frames} frames do not fit {columns} columns")
    rows = frames // columns
    warnings = []
    if canvas is None:
        canvas = CANVASES["3:1"] if rows == 1 else CANVASES["3:2"]
    elif canvas not in CANVASES.values():
        warnings.append(f"{canvas[0]}x{canvas[1]} is not a size an image tool was seen to return ({', '.join(f'{w}x{h}' for w, h in CANVASES.values())}); it will probably return another size, and the cut measures what comes back")
    if columns > MAX_ROW:
        warnings.append(f"{columns} figures in one row came back clipped at the edges in the football project and needed a separate spacing edit; rows of at most {MAX_ROW} are safer")
    cell_w, cell_h = canvas[0] // columns, canvas[1] // rows
    height = neutral_height or round(cell_h * NEUTRAL_HEIGHT_FRACTION)
    ground = ground_line or round(cell_h * GROUND_LINE_FRACTION)
    if not 0 < height < ground < cell_h:
        raise ValueError(f"the neutral height ({height}) must be above the ground line ({ground}), which must be inside the cell ({cell_h} px tall)")
    gutter = max(8, round(cell_w * GUTTER_FRACTION))
    return {"frames": frames, "columns": columns, "rows": rows, "canvas": list(canvas), "cell": [cell_w, cell_h], "neutral_height": height, "ground_line": ground, "gutter": gutter,
            "note": "image tools return their own sizes whatever is asked: the prompt's pixel numbers are also given as shares of the cell, and the cut measures the picture that comes back"}, warnings


def _sheet_rules(frame_layout, background, loop, paired_limbs, poses, kind):
    """The prompt lines that fix the layout, scale, ground line, loop behaviour, background and the list of poses."""
    frames, columns, rows = frame_layout["frames"], frame_layout["columns"], frame_layout["rows"]
    cell_w, cell_h = frame_layout["cell"]
    height, ground, gutter = frame_layout["neutral_height"], frame_layout["ground_line"], frame_layout["gutter"]
    canvas_w, canvas_h = frame_layout["canvas"]
    lines = [f"LAYOUT: EXACTLY {frames} complete figures, {'in ONE horizontal row' if rows == 1 else f'in {rows} rows of {columns}'}, in reading order. The canvas is {canvas_w}x{canvas_h} pixels: "
             f"equal invisible cells about {cell_w}x{cell_h}, each figure whole and centred in its own cell, with at least {gutter} pixels ({round(100 * gutter / cell_w)}% of the cell width) of completely empty background beside every figure through the full height. "
             "Nothing touches a neighbouring cell or the picture's edge; no clipped parts, stray dots or shared outlines.",
             f"SCALE: one scale for ALL figures. The neutral pose is about {height} pixels tall ({round(100 * height / cell_h)}% of the cell height) and its lowest planted point stands on the line {ground} pixels "
             f"({round(100 * ground / cell_h)}%) below the top of each cell. Never resize a figure between frames; a pose that lowers or lifts the subject does so without changing its size. "
             + ("Keep the head the same size in every frame, not the posed bounding box: a crouch or a jump changes the height of the pose, never the head." if kind in HEAD_KINDS
              else "Keep the whole subject the same size in every frame: its length, width and height do not change between frames.")]
    if loop == "neutral":
        lines.append("The FIRST and LAST figures are identical copies of the approved neutral pose of this facing, with the same registration and size, so the loop closes on it.")
    elif loop == "cycle":
        lines.append(f"This is ONE seamless cycle sampled at {frames} equally spaced successive phases: the last figure leads naturally into the first, and the end point is NOT duplicated, so the first and last figures differ.")
    if paired_limbs:
        lines.append("Alternate the leading leg and the opposite arm in successive phases; do not repeat one split-leg silhouette in every frame. The leg on the side toward the viewer is the NEAR leg and the other the FAR leg; "
                     "the far-side limbs are very slightly darker, never a different colour, so which leg leads is unmistakable. Passing poses are narrow (the legs close together), contact poses wide, flight phases brief. "
                     "Do not mirror whole figures.")
    if poses:
        lines.append("THE POSES, in reading order: " + " ".join(f"({number}) {text.strip()}" for number, text in enumerate(poses, 1)))
    lines.append("BACKGROUND: " + ("a solid pure #FF00FF background (that exact colour) with nothing else on it, no shadow and no gradient." if background == "key" else "genuine transparent alpha."))
    lines.append("NOT ALLOWED: text, labels, grid lines, props, ground, baked shadow, border, watermark, a second subject, a different design, a different camera.")
    return lines


def _roles(game, turnaround_path, facing_reference, timeline_reference):
    refs = [game.reference(role, path) for role, path in (("turnaround", turnaround_path), ("facing", facing_reference), ("timeline", timeline_reference)) if path]
    return refs, {ref["role"]: number for number, ref in enumerate(refs, 1)}


def _view_name(game, facing, view_text):
    if view_text == "auto":
        return turnaround_view(game.directions, facing)
    return view_text.strip() if view_text and view_text.strip() else None


def build(game_root, facing, frames, action, subject="the subject", columns=None, canvas=None, neutral_height=None, ground_line=None, turnaround=None,
          facing_reference=None, timeline_reference=None, background="key", loop="neutral", turnaround_view_text=None, kind=None, poses=None, paired_limbs=False):
    game = Game(game_root, kind)
    facing_text = game.facing(facing)
    if loop not in LOOPS:
        raise ValueError(f"loop must be one of {', '.join(LOOPS)}")
    if background not in ("key", "alpha"):
        raise ValueError("background must be key (the exact #FF00FF) or alpha (true transparency)")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("name the action (idle, walk, clap ...)")
    frame_layout, warnings = layout(frames, columns, canvas, neutral_height, ground_line)
    if poses and len(poses) != frames:
        raise ValueError(f"{len(poses)} poses were given for {frames} frames; describe every frame or none")
    refs, roles = _roles(game, turnaround, facing_reference, timeline_reference)
    view = _view_name(game, facing, turnaround_view_text)
    if "turnaround" in roles and not view:
        warnings.append("the turnaround's view is not named (--turnaround-view auto, or in words such as 'bottom row, third figure'): the tool has to guess which of its figures is this facing")
    if "turnaround" not in roles:
        warnings.append("no approved turnaround is attached: nothing but words fixes the figure's identity and the view angle; make and approve the turnaround first (the `turnaround` command)")
    if "facing" not in roles:
        warnings.append(f"no approved {facing} picture is attached: nothing but words fixes this facing's camera")
    if loop == "neutral" and "facing" not in roles:
        warnings.append("the first and last figures are asked to be the neutral pose, but no neutral picture of this facing is attached to copy")
    if facing in MIRRORS and MIRRORS[facing] in game.directions:
        warnings.append(f"{facing} may be a mirror of an approved {MIRRORS[facing]} where the art stays correct (hair, light and marks that are not symmetrical need a drawn {facing})")
    lines = [f"Use case: identity-preserve. Create ONE animation strip of {subject} doing {action.strip()}, seen from ONE facing, for a 2D game."]
    if "turnaround" in roles:
        match = f" Match {view} of it exactly." if view else " Match its figure for this facing exactly."
        lines.append(f"Input {roles['turnaround']} is the APPROVED turnaround: the authority for identity, anatomy, proportions and the viewing angle of every facing.{match}")
    if "facing" in roles:
        lines.append(f"Input {roles['facing']} is the approved neutral picture of THIS facing: the exact identity, anatomy and CAMERA/FACING reference. Keep its camera, elevation and proportions.")
    if "timeline" in roles:
        lines.append(f"Input {roles['timeline']} is ONLY the approved action timeline, spacing and colour reference. Do NOT inherit its camera or facing.")
    lines += [f"FACING FOR THIS ENTIRE SHEET: {facing_text} Keep this facing throughout; an action must never turn into a different viewing direction.", f"CAMERA: {game.camera()}"]
    if game.style():
        lines.append(game.style())
    lines.append("IDENTITY: one unchanged subject rotated about its vertical axis, NOT new interpretations. Keep every part, proportion, colour and mark of the approved design; do not add or remove details.")
    lines += _sheet_rules(frame_layout, background, loop, paired_limbs, poses, kind)
    flags = (" --reference <the approved neutral picture of this facing> --neutral-ends" if "facing" in roles and loop == "neutral" else "") + (f" --crown {CROWN_PERCENT}" if kind in HEAD_KINDS else "")
    base = f"python scripts/slice_generated_strip.py --source <the picture the tool returned> --frames {frames} --columns {frame_layout['columns']}"
    command = f"{base} --out <new folder> --name <sheet name> --direction {facing} --action {action.strip().replace(' ', '_')}{flags}"
    return {"facing": facing, "camera_profile": game.profile, "prompt": "\n".join(lines), "references": refs, "warnings": warnings, "layout": frame_layout, "slice": command,
            "after_generation": _after_generation(f"{base} --check-only{flags}", view or "the figure of this facing", facing),
            "not_assessed": ["whether the picture the tool returns shows this facing and the approved figure: a person compares it with the turnaround"]
            + (["the head-width check was validated on an upright human; for an animal it measures the widest run in the top share of the figure, which may be its back and not its head"] if kind == "animal" else [])}


def _after_generation(check, view, facing):
    """What runs the moment an image tool returns a picture, without anyone asking: the measurements, then the list a person judges. The owner is shown a picture only with these results."""
    return {"when": "immediately after the image tool returns the picture and before it is shown to anyone; never wait to be asked", "run": check,
            "on_refusal": "a BLOCKED result is a failed generation: say so with the measurement and ask the tool again, or repair it (respace for crowded or clipped figures, repair for a wrong facing, fix for named items), keeping the failed picture as a rejected candidate",
            "review": "python scripts/gamearts_candidates.py review --game-root <game> --candidate-id <the id record printed> --reviewer agent --compared-with turnaround=<the approved turnaround> "
                      "--finding facing=<pass|fail>:<reason> --finding elevation=<pass|fail>:<reason> --finding identity=<pass|fail>:<reason> --finding motion=<pass|fail|not_applicable>:<reason>",
            "then_report": ["every measurement, match flag and warning above, as they are",
                            f"open the picture and the approved pictures as images and compare the picture with {view} of the turnaround: is it the {facing} facing (the visible parts and the hidden ones), is the camera elevation the same as the approved pictures, is it the same figure, do the poses move as asked; record the answer with its reasons using `review`, and explain every match flag",
                            "a failing finding rejects the picture; only a passing review lets it be selected, and the owner still approves the selected picture"]}


def turnaround(game_root, subject, master=None, kind=None, background="key"):
    """The prompt for the one approved model sheet: every facing of the game, four to a row, in the order `--turnaround-view auto` names."""
    game = Game(game_root, kind)
    rows = turnaround_rows(game.directions)
    for name in (name for row in rows for name in row):
        game.facing(name)
    if background not in ("key", "alpha"):
        raise ValueError("background must be key (the exact #FF00FF) or alpha (true transparency)")
    refs = [game.reference("identity", master)] if master else []
    canvas = CANVASES["3:2"] if len(rows) > 1 else CANVASES["3:1"]
    columns = max(len(row) for row in rows)
    cell_w, cell_h = canvas[0] // columns, canvas[1] // len(rows)
    height, ground = round(cell_h * NEUTRAL_HEIGHT_FRACTION), round(cell_h * GROUND_LINE_FRACTION)
    lines = [f"Use case: identity-preserve. Create ONE approved TURNAROUND sheet of {subject} for a 2D game: the SAME unchanged subject seen from {sum(len(r) for r in rows)} facings, one figure per cell, {len(rows)} row(s) of up to {columns}, "
             f"in reading order on a {canvas[0]}x{canvas[1]} canvas (equal invisible cells about {cell_w}x{cell_h})."]
    if refs:
        lines.append("Input 1 is the APPROVED design of the subject: the authority for identity, anatomy, proportions, colours and materials. Do not redesign it.")
    for number, row in enumerate(rows):
        for place, name in enumerate(row):
            lines.append(f"{'TOP' if number == 0 else 'BOTTOM' if number == len(rows) - 1 else 'ROW ' + str(number + 1)} ROW, {ORDINALS[place].upper()} FIGURE: {game.facings[name]}")
    lines += [f"CAMERA: {game.camera()}"]
    if game.style():
        lines.append(game.style())
    lines += ["IDENTITY: one unchanged subject rotated about its vertical axis, NOT new interpretations, in the same neutral standing pose in every cell.",
              f"SCALE: one scale for ALL figures: the neutral pose is about {height} pixels tall ({round(100 * height / cell_h)}% of the cell height), its lowest planted point on the line {ground} pixels below the top of each cell, "
              f"every figure whole and centred with at least {max(8, round(cell_w * GUTTER_FRACTION))} pixels of empty background beside it.",
              "BACKGROUND: " + ("a solid pure #FF00FF background (that exact colour) with nothing else on it, no shadow and no gradient." if background == "key" else "genuine transparent alpha."),
              "NOT ALLOWED: text, labels, grid lines, props, ground, baked shadow, border, watermark, a second subject, a different design, a different camera."]
    arrangement = [[turnaround_view(game.directions, name) for name in row] for row in rows]
    return {"prompt": "\n".join(lines), "references": refs, "rows": rows, "views": {name: turnaround_view(game.directions, name) for row in rows for name in row}, "arrangement": arrangement,
            "warnings": [] if refs else ["no approved design picture is attached: the turnaround is drawn from words alone; approve a mockup of the subject first"],
            "next": "have the owner compare every figure with the facing words, approve the sheet, then attach it (--turnaround, --turnaround-view auto) to every later prompt",
            "not_assessed": ["whether each figure shows its facing and the same subject: a person compares them"]}


def plan(game_root):
    """Which facings to draw, which to mirror, and which to draw first so one picture can be judged before the rest are asked for."""
    game = Game(game_root, facings_needed=False)
    drawn, mirrored = [], {}
    for name in game.directions:
        if name in MIRRORS and MIRRORS[name] in game.directions:
            mirrored[name] = MIRRORS[name]
        else:
            drawn.append(name)
    pilot = next((name for name in PILOT_ORDER if name in drawn), drawn[0])
    others = ", ".join(name for name in drawn if name != pilot) or "nothing else"
    mirrors = ", ".join(f"{m} from {s}" for m, s in mirrored.items()) or "nothing"
    return {"draw": drawn, "mirror": mirrored, "pilot": pilot, "turnaround": turnaround_rows(game.directions),
            "steps": ["make and approve the turnaround (turnaround)",
                      f"draw the {pilot} strip first with the other pictures attached (build), have the owner compare it with the turnaround, and fix it before the others",
                      f"then draw {others}",
                      f"mirror {mirrors} only where the art stays correct; a mirrored picture flips hair parts, light and marks"],
            "not_assessed": ["whether mirroring is acceptable for this subject: the owner judges"]}


def inbetween(game_root, facing, keyposes, keyframes, action, subject="the subject", turnaround=None, turnaround_view_text=None, kind=None, background="key", paired_limbs=False):
    """The prompt that inserts one in-between pose after every approved keypose, the loop seam included: a cycle is made as keyposes first, then in-betweens."""
    game = Game(game_root, kind)
    facing_text = game.facing(facing)
    if not isinstance(keyframes, int) or isinstance(keyframes, bool) or keyframes < 2:
        raise ValueError("keyframes must be a whole number of at least 2")
    frame_layout, warnings = layout(keyframes * 2)
    refs = [game.reference("keyposes", keyposes)] + ([game.reference("turnaround", turnaround)] if turnaround else [])
    view = _view_name(game, facing, turnaround_view_text)
    lines = [f"Use case: identity-preserve. Sprite animation in-betweens of {subject} doing {action.strip()}.",
             f"Input 1 contains {keyframes} APPROVED keyposes of one cycle, in reading order. Produce {keyframes * 2} sequential frames by inserting ONE pose between each adjacent pair of keyposes, INCLUDING between the last keypose and the first (the loop seam)."]
    if turnaround:
        lines.append("Input 2 is the approved turnaround, the authority for identity and angle." + (f" Match {view}." if view else ""))
    for number in range(1, keyframes * 2 + 1):
        if number % 2:
            lines.append(f"Frame {number} = input keypose {(number + 1) // 2}, unchanged.")
        else:
            lines.append(f"Frame {number} = the pose halfway between keypose {number // 2} and keypose {number // 2 % keyframes + 1}, articulated from the same figure.")
    lines += ["The keyposes (odd frames) keep their DIFFERENT poses exactly: do not replace a keypose by a generic one. The cycle has no duplicated endpoint.",
              f"FACING FOR THIS ENTIRE SHEET: {facing_text}", f"CAMERA: {game.camera()}"]
    if game.style():
        lines.append(game.style())
    lines += _sheet_rules(frame_layout, background, "none", paired_limbs, None, kind)
    flags = f" --crown {CROWN_PERCENT}" if kind in HEAD_KINDS else ""
    check = f"python scripts/slice_generated_strip.py --source <the picture the tool returned> --frames {keyframes * 2} --columns {frame_layout['columns']} --check-only{flags}"
    return {"facing": facing, "prompt": "\n".join(lines), "references": refs, "warnings": warnings, "layout": frame_layout,
            "after_generation": _after_generation(check, view or "the figure of this facing", facing),
            "not_assessed": ["whether the in-betweens are smooth and keep the keyposes: a person plays and compares them"]}


def repair(game_root, facing, target, turnaround, problem, degrees, turn, turnaround_view_text=None, frames=None, kind=None):
    """The edit prompt that corrects ONLY the facing of a strip against the approved turnaround, with the angle in degrees. Judging the result is a person's job."""
    game = Game(game_root, kind)
    facing_text = game.facing(facing)
    if not isinstance(degrees, int) or isinstance(degrees, bool) or not 1 <= degrees <= 90:
        raise ValueError("degrees must be a whole number from 1 to 90")
    if turn not in TURNS:
        raise ValueError(f"turn must be one of {', '.join(TURNS)}")
    if not isinstance(problem, str) or not problem.strip():
        raise ValueError("say what is wrong with the current facing (for example: too close to a right side profile)")
    refs = [game.reference("edit-target", target), game.reference("turnaround", turnaround)]
    view = _view_name(game, facing, turnaround_view_text)
    count = f" all {frames}" if frames else " ALL"
    lines = ["Use case: precise-object-edit.",
             "Image 1 is the EDIT TARGET, the strip to correct. Image 2 is the approved turnaround and the required viewing-angle reference" + (f", matching {view}" if view else "") + ".",
             f"Correct ONLY the facing/camera relationship for{count} figures in image 1. The current result is wrong: {problem.strip()}. It must be {facing_text}",
             f"Rotate each same subject about its vertical axis about {degrees} degrees {TURNS[turn]} from its present orientation, as a complete articulated body: every part follows the new facing, not just the front.",
             f"CAMERA, unchanged: {game.camera()}",
             "Preserve identity, proportions, colours, shading style, camera elevation, one scale for every figure, the number of figures, their order, the layout and canvas size, the gutters between them, and the action of every figure. Change nothing else."]
    return {"facing": facing, "prompt": "\n".join(lines), "references": refs, "warnings": [],
            "not_assessed": ["whether the corrected picture now matches the turnaround: a person compares them; playback or measurement logs are not facing acceptance"]}


def respace(game_root, target, frames, columns=None, percent=70, margin=18, baseline=None):
    """The edit prompt that corrects ONLY the spacing of a strip: every figure scaled by one factor, centred in its own column, no poses redrawn."""
    game = Game(game_root, facings_needed=False)
    if not isinstance(percent, int) or isinstance(percent, bool) or not 30 <= percent <= 95:
        raise ValueError("percent must be a whole number from 30 to 95")
    if not isinstance(margin, int) or isinstance(margin, bool) or margin < 1:
        raise ValueError("margin must be a whole number of pixels, at least 1")
    ref = game.reference("edit-target", target)
    frame_layout, _ = layout(frames, columns, (ref["width"], ref["height"]))
    column_width = ref["width"] / frame_layout["columns"]
    floor = (f" Keep every planted foot or base on the line y={baseline}, and keep the small relative lift of airborne frames." if baseline
             else " Keep every planted foot or base on one common baseline, and keep the small relative lift of airborne frames.")
    lines = ["Use case: precise-object-edit.",
             f"EDIT TARGET: the supplied strip of {frames} figures. Repair ONLY layout and cut-out spacing, preserving all {frames} corresponding poses, the anatomy, the scale RELATIONSHIPS between frames, the camera, the colours and the shading.",
             f"Keep the EXACT original {ref['width']}x{ref['height']} canvas and true alpha transparency. Divide it into {frame_layout['columns']} equal invisible columns of width {column_width:g}"
             + (f" and {frame_layout['rows']} rows" if frame_layout["rows"] > 1 else "") + f". Uniformly reduce EVERY whole figure to {percent}% of its present size (the same factor for all {frames}), then centre each figure horizontally in its OWN column.{floor}",
             f"Complete any part the tool clipped at the picture's edge using the same anatomy. Every visible part must be at least {margin} pixels from its cell's vertical borders, with no two figures touching.",
             "Do NOT scale individual limbs or heads, do not enlarge short poses, do not redesign any pose, do not change the sequence. One consistent scale in all cells. No text, grid, ground, shadow or extra objects.",
             f"CAMERA, unchanged: {game.camera()}"]
    return {"prompt": "\n".join(lines), "references": [ref], "warnings": [], "layout": frame_layout,
            "not_assessed": ["whether the spacing is now clean and nothing else moved: the cut refuses a figure that still touches the edge, and a person compares the poses"]}


def fix(game_root, target, changes, keep=None):
    """The edit prompt that changes ONLY the items named; every other pixel of the figures stays as close as it can."""
    game = Game(game_root, facings_needed=False)
    if not changes or any(not isinstance(item, str) or not item.strip() for item in changes):
        raise ValueError("name at least one thing to change, in words that say where (which frame, which part) and how")
    ref = game.reference("edit-target", target)
    lines = ["Use case: precise-object-edit.",
             f"EDIT TARGET: the supplied {ref['width']}x{ref['height']} sprite sheet. Preserve its exact identity, shapes and sizes, proportions, colours, shading, the fixed camera, every row and column count, and the canvas size. Preserve existing real transparency. This is a very limited repair, not regeneration or redesign.",
             "Change ONLY these items:"] + [f"{number}. {text.strip()}" for number, text in enumerate(changes, 1)]
    lines.append("Every other pixel belonging to the figures must stay as close as possible to the input."
                 + (f" In particular preserve {keep.strip()}." if keep and keep.strip() else " In particular preserve the neutral first and last poses and the identical size of every figure."))
    lines += [f"CAMERA, unchanged: {game.camera()}", "Keep every figure whole with no missing parts, no added ball, shadow, floor, grid or text, and true transparent (or exact key) background outside the silhouettes."]
    return {"prompt": "\n".join(lines), "references": [ref], "warnings": [],
            "not_assessed": ["whether only the named items changed: a person compares the result with the original"]}


def _add_look(parser):
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--kind", choices=KINDS, required=True, help="What is drawn: " + "; ".join(f"{name} = {words}" for name, words in KIND_WORDS.items()) + ". Each shows different parts from each facing, so it is never guessed")
    parser.add_argument("--background", choices=("key", "alpha"), default="key")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="op", required=True)
    one = sub.add_parser("build", help="The prompt packet for one facing")
    _add_look(one)
    one.add_argument("--facing", required=True, help="One of the game's directions: S, SW, W, NW, N, NE, E, SE")
    one.add_argument("--frames", type=int, required=True)
    one.add_argument("--action", required=True)
    one.add_argument("--subject", default="the subject", help="What is drawn, in the owner's words (a tanker truck, the hero)")
    one.add_argument("--columns", type=int, help="Figures per row; by default the most that divides the frames, up to six")
    one.add_argument("--canvas", help=f"A size the tool returns ({', '.join(f'{w}x{h}' for w, h in CANVASES.values())}); by default the 3:1 size for one row and the 3:2 size for a grid")
    one.add_argument("--neutral-height", type=int)
    one.add_argument("--ground-line", type=int)
    one.add_argument("--turnaround", help="The approved turnaround picture, inside the game")
    one.add_argument("--turnaround-view", help="Which figure of the turnaround is this facing: 'auto' (the arrangement `turnaround` asks for) or words such as 'bottom row, third figure'")
    one.add_argument("--facing-reference", help="The approved neutral picture of this facing, inside the game")
    one.add_argument("--timeline-reference", help="The approved action sheet that lends the timeline only")
    one.add_argument("--loop", choices=LOOPS, default="neutral", help="neutral: first and last are the neutral pose; cycle: the last leads into the first, no duplicated endpoint; none")
    one.add_argument("--pose", action="append", help="What one frame shows, in order, repeated once per frame (for example 'CONTACT: near leg forward')")
    one.add_argument("--paired-limbs", action="store_true", help="A walker or runner: alternate the leading leg, near and far limbs")
    mid = sub.add_parser("inbetween", help="The in-between poses of approved keyposes")
    _add_look(mid)
    mid.add_argument("--facing", required=True)
    mid.add_argument("--keyposes", required=True, help="The approved keypose picture, inside the game")
    mid.add_argument("--keyframes", type=int, required=True)
    mid.add_argument("--action", required=True)
    mid.add_argument("--subject", default="the subject")
    mid.add_argument("--turnaround")
    mid.add_argument("--turnaround-view")
    mid.add_argument("--paired-limbs", action="store_true")
    turn = sub.add_parser("turnaround", help="The prompt for the one approved model sheet")
    _add_look(turn)
    turn.add_argument("--subject", required=True)
    turn.add_argument("--master", help="The approved design picture of the subject, inside the game")
    sub.add_parser("plan", help="Which facings to draw, which to mirror, which first").add_argument("--game-root", type=Path, required=True)
    fix_facing = sub.add_parser("repair", help="The edit that corrects only a wrong facing against the turnaround")
    fix_facing.add_argument("--game-root", type=Path, required=True)
    fix_facing.add_argument("--kind", choices=KINDS, required=True)
    fix_facing.add_argument("--facing", required=True)
    fix_facing.add_argument("--target", required=True, help="The strip to correct, inside the game")
    fix_facing.add_argument("--turnaround", required=True, help="The approved turnaround, inside the game")
    fix_facing.add_argument("--turnaround-view")
    fix_facing.add_argument("--problem", required=True, help="What is wrong with the facing, in plain words")
    fix_facing.add_argument("--degrees", type=int, required=True, help="How far to rotate the subject about its vertical axis, 1 to 90")
    fix_facing.add_argument("--turn", required=True, choices=tuple(TURNS))
    fix_facing.add_argument("--frames", type=int, help="How many figures the strip holds")
    spacing = sub.add_parser("respace", help="The edit that corrects only the spacing of a strip")
    spacing.add_argument("--game-root", type=Path, required=True)
    spacing.add_argument("--target", required=True)
    spacing.add_argument("--frames", type=int, required=True)
    spacing.add_argument("--columns", type=int)
    spacing.add_argument("--percent", type=int, default=70, help="Scale every figure to this share of its present size")
    spacing.add_argument("--margin", type=int, default=18, help="Pixels every part must keep from its cell's borders")
    spacing.add_argument("--baseline", type=int, help="The pixel row the planted feet stand on")
    items = sub.add_parser("fix", help="The edit that changes only the items named")
    items.add_argument("--game-root", type=Path, required=True)
    items.add_argument("--target", required=True)
    items.add_argument("--change", action="append", required=True, help="One thing to change, saying where and how; repeat for each")
    items.add_argument("--keep", help="What must stay exactly as it is, beyond everything not named")
    args = parser.parse_args(argv)
    try:
        if args.op == "build":
            canvas = _size(args.canvas, "--canvas") if args.canvas else None
            result = build(args.game_root, args.facing, args.frames, args.action, args.subject, args.columns, canvas, args.neutral_height, args.ground_line, args.turnaround,
                           args.facing_reference, args.timeline_reference, args.background, args.loop, args.turnaround_view, args.kind, args.pose, args.paired_limbs)
        elif args.op == "inbetween":
            result = inbetween(args.game_root, args.facing, args.keyposes, args.keyframes, args.action, args.subject, args.turnaround, args.turnaround_view, args.kind, args.background, args.paired_limbs)
        elif args.op == "turnaround":
            result = turnaround(args.game_root, args.subject, args.master, args.kind, args.background)
        elif args.op == "plan":
            result = plan(args.game_root)
        elif args.op == "repair":
            result = repair(args.game_root, args.facing, args.target, args.turnaround, args.problem, args.degrees, args.turn, args.turnaround_view, args.frames, args.kind)
        elif args.op == "respace":
            result = respace(args.game_root, args.target, args.frames, args.columns, args.percent, args.margin, args.baseline)
        else:
            result = fix(args.game_root, args.target, args.change, args.keep)
    except ValueError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
