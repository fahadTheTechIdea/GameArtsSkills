#!/usr/bin/env python3
"""The plan card: what is about to happen, shown before the first picture is made.

  python scripts/gamearts_plan_card.py --game-root GAME --asset-class prop [--actions N] [--frames-per-action N] [--detachable-parts N]
                                       [--pictures N] [--mockup-approved]

It names the lane (quick, standard or full), how many pictures will be made, which approvals the owner will be asked for, and what the pictures may cost,
so the owner can say "that is too much" before anything is spent. The count is an estimate with a stated formula (one picture for each thing the lane
names; retries and revisions are not counted). Lanes:

  quick     one static asset or tile with no detachable parts: a mockup (unless an approved one covers it) and one master
  standard  a facing character, an animated asset, or a set of pictures: adds a master the owner approves, a master per other direction, a picture per frame
  full      anything with detachable parts: adds a master and a rebuilt area behind each part, and the review of the cut-out parts

The framework cannot know what a paid tool charges, so the card says who bills for the pictures and tells the owner to ask a connected tool for a quote;
it never states a price. Quick does not make a composite asset easier: the cleanup and review gates still decide whether it can be approved.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
from prepare_reference_crop import CLASSES, EITHER_CLASSES, SCREEN_CLASSES  # noqa: E402

SET_CLASSES = {"tileset", "icon_set", "portrait_set", "card_layer_set"}  # classes made of many pictures
LAYER_CLASSES = {"parallax_layer", "ui_presentation"}  # one picture, or a stack (layers, or a kit of controls and their states) when the owner says how many
COMPOSITE_CLASSES = {"static_structure", "fixed_machinery"}  # classes whose parts may open or move, so a Quick card states its assumption
LANE_TITLES = {"quick": "Quick", "standard": "Standard", "full": "Full"}


def _whole(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a whole number of 0 or more")
    return value


def _settings(root):
    """(settings, None), or (None, why) when the game has no readable settings. The reason is carried into the card, never dropped."""
    try:
        settings, _, _ = common.load_project_settings(root, require_confirmed=False)
        return settings, None
    except ValueError as exc:
        return None, str(exc)


def _credits(settings, problem):
    if settings is None:
        return "The image generator is not chosen yet (the game's settings could not be read: " + problem + "); who is billed depends on that tool, so ask the owner first."
    chosen = settings.get("image_generation")
    if not chosen:
        return "The image generator is not chosen yet; who is billed for the pictures depends on that tool, so ask the owner which one to use before the first picture."
    tool = chosen["tool"]
    if tool == "built_in_image_gen":
        return "The agent's own image tool: its pictures are covered by the agent's own plan or subscription, and this framework cannot see how much of it they use."
    if tool == "cli_image_gen":
        return "Codex's command-line image tool: each picture is billed to the account behind the OpenAI API key it uses, at that account's prices, which are not known here."
    if tool == "connected_tool":
        name = chosen.get("tool_name", "the connected tool")
        return f"{name} is a connected tool and may charge credits for each picture. Its price is its own and is not known here, so ask it for a quote before the first picture."
    return "You make the pictures yourself, so no tool is called; the count above is how many pictures you will need to supply."


def plan(game_root, asset_class, actions=None, frames_per_action=1, detachable_parts=0, pictures=None, mockup_approved=False, rig_by_transform=False):
    """The plan card for one piece of work, as a dict with `lane`, `why`, `image_calls`, `estimated_pictures`, `approvals`, `credits` and `message`."""
    if asset_class not in CLASSES:
        raise ValueError(f"Unknown asset class {asset_class!r}; use one of {', '.join(sorted(CLASSES))}")
    mobile = asset_class == "mobile_directional"
    actions = _whole(actions if actions is not None else (1 if mobile else 0), "actions")
    frames_per_action = _whole(frames_per_action, "frames per action")
    parts = _whole(detachable_parts, "detachable parts")
    if asset_class in SET_CLASSES and (pictures is None or _whole(pictures, "pictures") < 1):
        raise ValueError(f"A {asset_class} is a set of pictures: say how many pictures the set has")
    settings, problem = _settings(Path(game_root))
    if settings is not None and common.world_kind(settings) == "screen_space" and asset_class not in SCREEN_CLASSES | EITHER_CLASSES:
        raise ValueError(f"This game is screen_space (it has no ground world), so {asset_class} art does not apply; "
                         f"plan {', '.join(sorted(SCREEN_CLASSES | EITHER_CLASSES))} art, or change the game's world kind first")
    # A set of one picture is one static asset; a stack of layers is a set only when the owner says there is more than one.
    is_set = (asset_class in SET_CLASSES or asset_class in LAYER_CLASSES) and pictures is not None and _whole(pictures, "pictures") > 1
    animated = actions > 1 or (actions == 1 and frames_per_action > 1)
    if parts:
        lane, why = "full", f"it has {parts} detachable part(s), so each part is cut out and the area behind it is rebuilt and reviewed before approval"
    elif is_set:
        lane, why = "standard", f"it is a set of {pictures} pictures that must fit together"
    elif mobile or animated:
        lane, why = "standard", "it faces several ways or moves, so a master is approved first and the other views and frames follow it"
    else:
        lane, why = "quick", "it is one static asset with no detachable parts"
    calls = {} if mockup_approved else {"mockup": 1}
    if is_set:
        calls["pictures"] = pictures
    else:
        calls["master"] = 1
    if rig_by_transform and not parts:
        raise ValueError("A transform rig moves its detachable parts: say how many parts it has")
    if rig_by_transform:  # the motion is tracks on the cut-out parts, so no picture is drawn for a frame
        actions = 0
    if mobile:
        if settings is None:
            raise ValueError("A facing character is planned from the game's directions, which come from its saved settings: " + problem)
        directions = len(common.resolve_directions(settings))
        calls["directional_masters"] = directions - 1
        if actions:
            calls["frames"] = directions * actions * frames_per_action
    elif actions:
        calls["frames"] = actions * frames_per_action
    if parts:
        calls["parts"] = parts * 2  # a master for the part and the rebuilt area behind it
    total = sum(calls.values())
    noun = "set" if is_set else "asset"
    approvals = [] if mockup_approved else ["the mockup"]
    if lane in ("standard", "full") and not is_set:
        approvals.append("the master picture")
    if lane == "full":
        approvals.append("the cut-out parts and the areas behind them (review boards)")
    approvals.append(f"the finished {noun}")
    credits = _credits(settings, problem)
    breakdown = ", ".join(f"{count} {name.replace('_', ' ')}" for name, count in calls.items())
    message = (f"Plan: {LANE_TITLES[lane]} lane, because {why}. About {total} picture{'' if total == 1 else 's'} will be made ({breakdown}); that is an estimate, "
               f"and retries are not counted. You will be asked to approve {', then '.join(approvals)}. Credits: {credits}")
    if lane == "quick" and asset_class in COMPOSITE_CLASSES and not parts:
        message += " This assumes nothing on it opens or moves on its own; if a door, lamp or lid does, count those parts and plan the Full lane."
    return {"lane": lane, "why": why, "image_calls": calls, "estimated_pictures": total, "approvals": approvals, "credits": credits, "message": message}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--asset-class", required=True)
    parser.add_argument("--actions", type=int, help="How many actions (walk, attack ...) are animated; default 1 for a facing character, otherwise 0")
    parser.add_argument("--frames-per-action", type=int, default=1)
    parser.add_argument("--detachable-parts", type=int, default=0)
    parser.add_argument("--rig-by-transform", action="store_true", help="The parts move by transforms (a cut-out rig): its frames are not pictures")
    parser.add_argument("--pictures", type=int, help="How many pictures a set (tileset, icon set, portraits, card layers) has")
    parser.add_argument("--mockup-approved", action="store_true", help="An approved mockup already covers this asset")
    args = parser.parse_args()
    try:
        print(json.dumps(plan(args.game_root, args.asset_class, args.actions, args.frames_per_action, args.detachable_parts, args.pictures, args.mockup_approved, args.rig_by_transform),
                         indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
