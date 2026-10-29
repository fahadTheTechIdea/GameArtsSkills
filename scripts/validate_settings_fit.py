#!/usr/bin/env python3
"""Does finished art fit the game's saved settings? A bundle folder is read against what the game said about itself.

  python scripts/validate_settings_fit.py --game-root GAME --folder BUNDLE_FOLDER

Three facts of the game are compared with what the artwork records about itself:
  * directions: a component bundle that faces several ways must face the game's directions (`directions`);
  * tile size: a ground tileset must use the game's ground tile (`world.ground_tile_px`);
  * scale: a sheet that records its pixels per metre must match the game's (`world.pixels_per_meter`).
Each check reports `passed`, `mismatch` or `not_applicable` (with the reason). A mismatch is reported to the owner and never blocks approval on
its own: a half-size sub-tile or a deliberately scaled prop can be right, and the framework cannot tell. A bundle that faces fewer of the game's
directions passes when the asset records a limited profile the owner approved (`register-asset --limited-profile-ref`). Exit status 1 means a
mismatch was found, so a script can stop on it.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402


def _check(name, status, detail):
    return {"name": name, "status": status, "detail": detail}


def _size(value):
    return f"{value[0]}x{value[1]}"


def check_directions(folder, settings, limited_profile=None):
    """Each component bundle against the game's facing directions. A bundle with one view is a fixed object and has no facing to compare. A bundle
    that faces only some of the game's directions passes when `limited_profile` (the owner's recorded approval) is given; its check says so."""
    game = common.resolve_directions(settings)
    checks = []
    for path in sorted(Path(folder).glob("*.bundle.json")):
        faces = common.read_json(path).get("directions") or []
        if len(faces) < 2:
            checks.append(_check("directions", "not_applicable", f"{path.name}: one view, so a fixed object with no facing"))
        elif not game:
            checks.append(_check("directions", "mismatch", f"{path.name}: faces {', '.join(faces)}, but this game declares no facing directions"))
        elif set(faces) == set(game) and len(faces) == len(game):
            checks.append(_check("directions", "passed", f"{path.name}: faces the game's {len(game)} directions"))
        elif limited_profile and len(set(faces)) == len(faces) and set(faces) < set(game):
            checks.append({**_check("directions", "passed", f"{path.name}: faces {', '.join(faces)}, a limited profile of the game's {', '.join(game)}, "
                                                              f"approved by the owner: {limited_profile['approval_ref']}"), "limited_profile": True})
        else:
            checks.append(_check("directions", "mismatch", f"{path.name}: faces {', '.join(faces)}, but the game's directions are {', '.join(game)}; "
                                                              "fine for an approved limited profile, otherwise the set is incomplete or wrong"))
    return checks


def check_tile_size(folder, settings):
    """Each ground tileset against the game's ground tile. A tileset of objects (not full-bleed) may use any tile size."""
    ground = (settings.get("world") or {}).get("ground_tile_px")
    checks = []
    for path in sorted(Path(folder).glob("*.tileset.json")):
        tileset = common.read_json(path)
        if not ground:
            checks.append(_check("tile size", "not_applicable", f"{path.name}: the game states no ground tile size"))
        elif tileset.get("full_bleed", True) is False:
            checks.append(_check("tile size", "not_applicable", f"{path.name}: a tileset of objects may use any tile size"))
        elif list(tileset["tile_size"]) == list(ground):
            checks.append(_check("tile size", "passed", f"{path.name}: tiles are {_size(ground)}, the game's ground tile"))
        else:
            checks.append(_check("tile size", "mismatch", f"{path.name}: tiles are {_size(tileset['tile_size'])}, but the game's ground tile is {_size(ground)}"))
    return checks


def check_scale(folder, settings):
    """Each sheet that records its pixels per metre against the game's."""
    game = (settings.get("world") or {}).get("pixels_per_meter")
    checks = []
    for path in sorted(Path(folder).glob("*.atlas.json")):
        recorded = common.read_json(path).get("pixels_per_meter")
        if recorded is None or game is None:
            continue  # nothing recorded on one side: there is nothing to compare, and nothing to report
        if recorded == game:
            checks.append(_check("scale", "passed", f"{path.name}: {recorded} pixels per metre, the game's scale"))
        else:
            checks.append(_check("scale", "mismatch", f"{path.name}: records {recorded} pixels per metre, but the game's scale is {game}"))
    return checks


def fit_report(folder, settings, problem=None, limited_profile=None):
    """The settings part of the technical artwork gate for one bundle folder. Settings that cannot be read are reported as untested with the
    reason, never skipped silently. `status` is mismatch when any check found one, passed when something matched, otherwise not_applicable.
    `limited_profile` is the asset's recorded owner approval of a limited facing set, if it has one."""
    if settings is None:
        return {"status": "untested", "reason": problem or "no settings were supplied", "checks": []}
    checks = check_directions(folder, settings, limited_profile) + check_tile_size(folder, settings) + check_scale(folder, settings)
    states = {item["status"] for item in checks}
    status = "mismatch" if "mismatch" in states else "passed" if "passed" in states else "not_applicable"
    report = {"status": status, "checks": checks}
    if not checks:
        report["reason"] = "the folder holds no bundle, tileset or sheet that records a fact of the game's settings"
    return report


def announce(game_root, folder):
    """What a builder tells the owner after it has built into `folder` for a game: whether the new art fits the game's saved settings.
    Settings that cannot be read are said to be untested, with the reason; the build itself already succeeded and stays succeeded."""
    try:
        settings, _, _ = common.load_project_settings(game_root, require_confirmed=False)
    except (OSError, ValueError) as exc:
        print(f"SETTINGS FIT untested: {exc}")
        return
    report = fit_report(folder, settings)
    print(f"SETTINGS FIT {report['status']}")
    for item in report["checks"]:
        if item["status"] == "mismatch":
            print(f"  MISMATCH ({item['name']}) {item['detail']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--folder", type=Path, required=True, help="A bundle folder (a candidate or an approved asset)")
    args = parser.parse_args()
    try:
        settings, _, _ = common.load_project_settings(args.game_root, require_confirmed=False)
        report = fit_report(args.folder, settings)
    except (OSError, ValueError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["status"] == "mismatch" else 0


if __name__ == "__main__":
    raise SystemExit(main())
