#!/usr/bin/env python3
"""Single owner of the shipped preset data: style presets (presets/styles) and engine profiles (presets/engines).

Both are validated data. Every file is checked against its contract each time it is loaded, so a broken preset fails loudly
instead of being skipped. A project copies a style preset's values at setup; an engine profile is read, never copied.

Agent use (the setup flow lists real options from the folders instead of hard-coding them):
  python scripts/gamearts_presets.py list --kind styles|engines [--world-kind KIND] [--camera PROFILE]
  python scripts/gamearts_presets.py show --kind styles|engines --id ID
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402

PRESETS = Path(__file__).resolve().parent.parent / "presets"
GENERIC = "generic"
KINDS = ("styles", "engines")
# Framework concepts an engine profile may map. A concept is added here in the same change as the feature it names, so a profile can
# never describe something the framework does not have.
CONCEPTS = (
    "atlas_frame_rect", "frame_pivot", "frame_anchor", "frame_duration", "direction_set",
    "texture_filter_pixel", "texture_filter_smooth", "key_colour_removal",
    "grid_hex_pointy", "grid_hex_flat", "grid_isometric", "parallax_layer", "screen_base_resolution",
    "animation_tag_range", "animation_tag_loop", "animation_tag_repeat_count", "animation_tag_reverse", "animation_tag_pingpong",
    "nine_slice", "ui_state_set", "interpolation_nearest", "interpolation_linear", "interpolation_cubic", "easing_named_curves",
    "blend_normal", "blend_additive", "blend_subtractive", "blend_multiply", "blend_screen", "blend_premultiplied",
    "tileset_wang_corner", "tileset_wang_edge", "tileset_blob", "tileset_dual_grid", "tile_neighbour_labels", "runtime_transparency",
)
BACKED_BY = ("documented", "observed")  # a `native` claim needs a source of one of these kinds


def _check_engine_profile(profile):
    """Internal consistency of one engine profile: known concepts, resolvable sources, no unbacked `native` claim."""
    sources = {}
    for source in profile["sources"]:
        if source["id"] in sources:
            raise ValueError(f"source id {source['id']!r} appears twice")
        if source["basis"] in ("documented", "claimed") and not source.get("url"):
            raise ValueError(f"source {source['id']!r} is {source['basis']} but has no url")
        if source["basis"] == "observed" and not source.get("evidence"):
            raise ValueError(f"source {source['id']!r} is observed but states no evidence")
        sources[source["id"]] = source
    seen = set()
    for item in profile["concept_map"]:
        concept = item["concept"]
        if concept not in CONCEPTS:
            raise ValueError(f"concept {concept!r} is not a framework concept ({', '.join(CONCEPTS)})")
        if concept in seen:
            raise ValueError(f"concept {concept!r} is mapped twice")
        seen.add(concept)
        source = sources.get(item["source"])
        if source is None:
            raise ValueError(f"concept {concept!r} cites unknown source {item['source']!r}")
        if item["support"] == "native" and source["basis"] not in BACKED_BY:
            raise ValueError(f"concept {concept!r} is claimed native but its source {source['id']!r} is only {source['basis']}")
    for item in profile["import_guidance"]:
        if item.get("source") is not None and item["source"] not in sources:
            raise ValueError(f"guidance {item['topic']!r} cites unknown source {item['source']!r}")


def _load_folder(kind, folder, check):
    """Load every `*.json` of one preset folder. `check` validates one file's data (its contract and any rules beyond it)."""
    base = Path(folder) if folder is not None else PRESETS / kind
    found = {}
    if not base.is_dir():
        return found
    for path in sorted(base.glob("*.json")):
        try:
            data = common.read_json(path)
            check(data)
            if data["id"] != path.stem:
                raise ValueError(f"id {data['id']!r} must equal the file name {path.stem!r}")
        except ValueError as exc:
            raise ValueError(f"{kind}/{path.name}: {exc}") from exc
        found[data["id"]] = data
    return found


def style_presets(folder=None):
    return _load_folder("styles", folder, lambda data: common.validate_schema(data, "gamearts-style-preset"))


def _check_engine_file(data):
    common.validate_schema(data, "gamearts-engine-profile")
    _check_engine_profile(data)


def engine_profiles(folder=None):
    return _load_folder("engines", folder, _check_engine_file)


def resolve_engine_target(settings, folder=None):
    """The engine profile a project asks for. A project that names none gets `generic`; one that names a profile with no file still
    works exactly as before (the outputs are engine-neutral) and is told so. Never an error: the engine is a setting, not a gate."""
    target = settings.get("engine_target") or {}
    wanted = target.get("profile", GENERIC)
    result = {"profile": wanted, "defaulted": "engine_target" not in settings, "version_note": target.get("version_note")}
    try:
        profile = engine_profiles(folder).get(wanted)
    except ValueError as exc:  # a damaged profile file is reported to the caller; the engine setting never becomes a gate
        result.update(found=False, problem=str(exc), message="An installed engine profile is damaged; the generic guidance applies")
        return result
    result["found"] = profile is not None
    if profile is None:
        result["message"] = (f"No engine profile named {wanted!r} is installed; the framework's outputs are engine-neutral and "
                             "the generic guidance applies")
    else:
        result["title"] = profile["title"]
        result["documented_against"] = profile.get("documented_against")
        result["default_exports"] = list(profile.get("default_exports", []))
    return result


def integration_notes(settings, folder=None):
    """Import guidance that applies to this project's art style, from its engine profile (the generic one when none is installed)."""
    profiles = engine_profiles(folder)
    profile = profiles.get(settings.get("engine_target", {}).get("profile", GENERIC)) or profiles.get(GENERIC)
    if profile is None:
        return []
    family = "pixel_art" if settings["art_style"]["id"] == "pixel_art" else "smooth"
    return [{"topic": g["topic"], "text": g["text"]} for g in profile["import_guidance"] if g["applies_to"] in (family, "all")]


def resolve_style_preset(settings, folder=None):
    """The style preset a project started from, or None when it names none. A named preset with no file is reported, not an error."""
    wanted = settings["art_style"].get("preset")
    if wanted is None:
        return None
    try:
        preset = style_presets(folder).get(wanted)
    except ValueError as exc:  # a damaged preset file is reported to the caller, never skipped silently
        return {"preset": wanted, "found": False, "problem": str(exc),
                "message": "An installed style preset is damaged; the project keeps the policy values it already holds"}
    if preset is None:
        return {"preset": wanted, "found": False,
                "message": f"No style preset named {wanted!r} is installed; the project keeps the policy values it already holds"}
    return {"preset": wanted, "found": True, "title": preset["title"], "required_checks": preset["required_checks"],
            "check_parameters": preset.get("check_parameters", {}), "avoid": preset["avoid"],
            "soft_edges": preset["soft_edges"]}


def suits(entry, world_kind=None, camera=None):
    """Whether a style preset suits the given world kind and camera; an engine profile has neither and always passes."""
    if world_kind and world_kind not in entry.get("world_kinds", [world_kind]):
        return False
    return not camera or camera in entry.get("cameras", [camera])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "show"):
        item = sub.add_parser(name)
        item.add_argument("--kind", choices=KINDS, required=True)
        if name == "show":
            item.add_argument("--id", required=True)
        else:
            item.add_argument("--world-kind", choices=common.WORLD_KINDS, help="styles only: keep the looks that suit this kind of world")
            item.add_argument("--camera", help="styles only: keep the looks that suit this camera profile")
    args = parser.parse_args()
    try:
        loaded = (style_presets if args.kind == "styles" else engine_profiles)()
        if args.command == "list":
            if args.kind != "styles" and (args.world_kind or args.camera):
                raise ValueError("--world-kind and --camera filter style presets only")
            summary = "description" if args.kind == "styles" else "summary"
            result = [{"id": key, "title": value["title"], "summary": value[summary]} for key, value in loaded.items()
                      if suits(value, args.world_kind, args.camera)]
        else:
            if args.id not in loaded:
                raise ValueError(f"No {args.kind} entry named {args.id!r}; installed: {', '.join(loaded) or 'none'}")
            result = loaded[args.id]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
