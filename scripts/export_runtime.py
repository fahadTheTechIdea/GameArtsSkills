#!/usr/bin/env python3
"""Derive engine-ready copies of delivered sheets: the key colour becomes real transparency.

  python scripts/export_runtime.py --bundle FOLDER --output-dir DIR            # every sheet and atlas of a bundle (and its bundle / tileset files)
  python scripts/export_runtime.py --sheet S.png --atlas S.atlas.json --output-dir DIR
  python scripts/export_runtime.py --verify DIR --source FOLDER                # check an export against the art it came from

Delivered sheets keep every unused pixel at the exact key colour #FF00FF so they can be checked, but an engine wants real transparency. This writes,
for each sheet, an RGBA PNG of the same size and name in which every pixel that is exactly the key colour is fully transparent (RGBA 0, 0, 0, 0)
and every other pixel keeps its colour at alpha 255, plus the atlas with identical rectangles, pivots, anchors, durations and tags and a `runtime`
block recording the hashes of the sheet and atlas it came from. Bundle and tileset files are copied unchanged (their atlas names still resolve).
`runtime.export.json` lists every file with its hash and its source's hash.

The result is a derived copy: it is never approved, never a source for new art, and putting the key colour back under it reproduces the delivered
sheet exactly (`--verify` proves it, and also finds a source that changed since). The framework does not blur or bleed colour into the transparent
border; an engine's own alpha-border option does that on import. Soft (fractional) alpha is not produced: a sheet has none to carry.
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import validate_sheet_atlas as sheet_validator  # noqa: E402

MANIFEST = "runtime.export.json"
RULE = "Pixels that are exactly #FF00FF become fully transparent (RGBA 0, 0, 0, 0); every other pixel keeps its colour at alpha 255."
COPIED_SUFFIXES = (".bundle.json", ".tileset.json")  # unchanged: they name atlases, and the atlases keep their names


def to_runtime_image(sheet):
    """The sheet as RGBA with every exact-key pixel fully transparent and black underneath, every other pixel unchanged at alpha 255."""
    from PIL import Image
    rgba = sheet.convert("RGBA")
    art = common.nonkey_mask(rgba)
    runtime = Image.composite(rgba.convert("RGB"), Image.new("RGB", rgba.size, (0, 0, 0)), art).convert("RGBA")
    runtime.putalpha(art)
    return runtime


def over_key(runtime):
    """A runtime sheet laid over the key colour: the delivered sheet it was made from, exactly."""
    from PIL import Image
    return Image.alpha_composite(Image.new("RGBA", runtime.size, common.KEY_RGBA), runtime.convert("RGBA"))


def _record(path, base, role, source=None, source_base=None):
    entry = {"path": path.relative_to(base).as_posix(), "role": role, "sha256": common.sha256_file(path)}
    if source is not None:
        entry["source_path"] = source.relative_to(source_base).as_posix()
        entry["source_sha256"] = common.sha256_file(source)
    return entry


def _export(pairs, copies, source_folder, output_dir):
    """Write the runtime files for the given (sheet, atlas) pairs and copied files into a new folder; returns the manifest."""
    from PIL import Image
    source_folder, output_dir = Path(source_folder).resolve(), Path(output_dir).resolve()
    if output_dir == source_folder or common.inside(output_dir, source_folder) or common.inside(source_folder, output_dir):
        raise ValueError("The output folder must be separate from the art it is made from")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"{output_dir.name} already exists and is not empty; a runtime export never overwrites files")
    problems = []
    for sheet, atlas in pairs:
        problems += [f"{atlas.name}: {issue}" for issue in sheet_validator.validate(sheet, atlas)]
    if problems:
        raise ValueError("cannot export art that fails its own checks: " + "; ".join(problems[:3]))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".gamearts-runtime-", dir=str(output_dir.parent)))
    try:
        files = []
        for sheet, atlas in pairs:
            atlas_data = common.read_json(atlas)
            with Image.open(sheet) as opened:
                runtime = to_runtime_image(opened)
            target_sheet = stage / sheet.name
            runtime.save(target_sheet, format="PNG")
            atlas_data["background_alpha"] = 0
            atlas_data["runtime"] = {"derived": True, "rule": RULE, "source_sheet": sheet.name,
                                     "source_sheet_sha256": common.sha256_file(sheet), "source_atlas_sha256": common.sha256_file(atlas)}
            common.validate_schema(atlas_data, "gamearts-atlas")
            target_atlas = stage / atlas.name
            common.atomic_write_json(target_atlas, atlas_data)
            files += [_record(target_sheet, stage, "sheet", sheet, source_folder), _record(target_atlas, stage, "atlas", atlas, source_folder)]
        for copy in copies:
            shutil.copyfile(copy, stage / copy.name)
            files.append(_record(stage / copy.name, stage, "copied", copy, source_folder))
        manifest = {"schema_version": "1.0", "kind": "runtime", "rule": RULE, "files": sorted(files, key=lambda item: item["path"])}
        common.validate_schema(manifest, "gamearts-runtime-export")
        common.atomic_write_json(stage / MANIFEST, manifest)
        if output_dir.exists():
            output_dir.rmdir()  # empty: checked above
        common.replace_file(stage, output_dir)
    except BaseException:
        shutil.rmtree(stage)  # a half-built export is never left behind; a failure to clean up is itself raised, with the cause chained
        raise
    return manifest


def export_bundle(source_folder, output_dir):
    """Runtime copies of every sheet of a bundle folder (and its bundle and tileset files). Returns the manifest written beside them."""
    source_folder = Path(source_folder).resolve()
    atlases = sorted(source_folder.glob("*.atlas.json"))
    if not atlases:
        raise ValueError("The folder has no <name>.atlas.json, so there is no sheet to export")
    pairs = [(source_folder / common.read_json(atlas)["image"], atlas) for atlas in atlases]
    copies = sorted(p for p in source_folder.iterdir() if p.is_file() and p.name.endswith(COPIED_SUFFIXES))
    return _export(pairs, copies, source_folder, output_dir)


def export_sheet(sheet_path, atlas_path, output_dir):
    """Runtime copy of one sheet and its atlas."""
    sheet_path, atlas_path = Path(sheet_path).resolve(), Path(atlas_path).resolve()
    return _export([(sheet_path, atlas_path)], [], sheet_path.parent, output_dir)


def verify_export(export_dir, source_folder):
    """Everything wrong with a runtime export, measured against the art it came from; an empty list means it is sound and current."""
    from PIL import Image
    export_dir, source_folder = Path(export_dir), Path(source_folder)
    try:
        manifest = common.read_json(export_dir / MANIFEST)
        common.validate_schema(manifest, "gamearts-runtime-export")
    except (OSError, ValueError) as exc:  # a missing, unreadable or malformed manifest is the finding, not a crash
        return [f"runtime export manifest: {exc}"]
    issues, listed = [], {MANIFEST}
    for entry in manifest["files"]:
        listed.add(entry["path"])
        target, source = export_dir / entry["path"], source_folder / entry["source_path"]
        if not target.is_file():
            issues.append(f"{entry['path']}: listed in the manifest but missing")
            continue
        if common.sha256_file(target) != entry["sha256"]:
            issues.append(f"{entry['path']}: changed since it was exported (hash differs)")
            continue
        if not source.is_file():
            issues.append(f"{entry['path']}: its source {entry['source_path']} is missing, so the export cannot be checked")
            continue
        if common.sha256_file(source) != entry["source_sha256"]:
            issues.append(f"{entry['path']}: stale, because its source {entry['source_path']} changed after the export")
            continue
        if entry["role"] == "sheet":
            issues += _sheet_issues(entry["path"], target, source)
        elif entry["role"] == "atlas":
            issues += _atlas_issues(entry["path"], target, source, source_folder)
        elif target.read_bytes() != source.read_bytes():
            issues.append(f"{entry['path']}: should be an unchanged copy of {entry['source_path']}")
    for extra in sorted(p.relative_to(export_dir).as_posix() for p in export_dir.rglob("*") if p.is_file()):
        if extra not in listed:
            issues.append(f"{extra}: in the export folder but not listed in the manifest")
    return issues


def _sheet_issues(name, runtime_path, source_path):
    from PIL import Image
    with Image.open(runtime_path) as opened:
        if opened.mode != "RGBA":
            return [f"{name}: should be an RGBA picture, not {opened.mode}"]
        runtime = opened.copy()
    issues = []
    alpha = runtime.getchannel("A")
    counts = alpha.histogram()
    soft = sum(counts[1:255])
    if soft:
        issues.append(f"{name}: {soft} pixel(s) are partly transparent, but a runtime copy of a delivered sheet has only fully transparent and fully opaque pixels")
    hidden = Image.composite(runtime.convert("RGB"), Image.new("RGB", runtime.size, (0, 0, 0)), alpha.point(lambda v: 255 if v == 0 else 0))
    if hidden.getbbox() is not None:
        issues.append(f"{name}: some fully transparent pixels carry colour; they should be black")
    with Image.open(source_path) as opened:
        source = opened.convert("RGBA")
    if runtime.size != source.size or over_key(runtime).tobytes() != source.tobytes():
        issues.append(f"{name}: laid over the key colour it does not reproduce the delivered sheet {source_path.name} exactly")
    return issues


def _atlas_issues(name, runtime_path, source_path, source_folder):
    runtime, source = common.read_json(runtime_path), common.read_json(source_path)
    block = runtime.pop("runtime", None)
    runtime.pop("background_alpha", None)
    source.pop("background_alpha", None)
    issues = []
    if not isinstance(block, dict) or block.get("derived") is not True:
        issues.append(f"{name}: has no runtime block saying it is a derived copy")
    else:
        for key, path in (("source_atlas_sha256", source_path), ("source_sheet_sha256", source_folder / block.get("source_sheet", ""))):
            if not path.is_file() or block.get(key) != common.sha256_file(path):
                issues.append(f"{name}: runtime.{key} does not match the current {path.name}")
    if runtime != source:
        issues.append(f"{name}: its frames, pivots, anchors, durations or tags differ from the delivered atlas")
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--sheet", type=Path)
    parser.add_argument("--atlas", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify", type=Path, help="A runtime export folder to check against --source")
    parser.add_argument("--source", type=Path, help="The bundle folder the export was made from (with --verify)")
    args = parser.parse_args()
    try:
        if args.verify:
            if not args.source:
                raise ValueError("--verify needs --source, the folder the export was made from")
            issues = verify_export(args.verify, args.source)
            print(json.dumps({"status": "failed" if issues else "passed", "issues": issues}, indent=2))
            return 1 if issues else 0
        if not args.output_dir:
            raise ValueError("--output-dir is required")
        if args.bundle:
            manifest = export_bundle(args.bundle, args.output_dir)
        elif args.sheet and args.atlas:
            manifest = export_sheet(args.sheet, args.atlas, args.output_dir)
        else:
            raise ValueError("give --bundle FOLDER, or --sheet and --atlas")
        print(json.dumps({"written": [entry["path"] for entry in manifest["files"]] + [MANIFEST], "output_dir": str(args.output_dir),
                          "note": "Derived copies: never approved and never a source for new art."}, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
