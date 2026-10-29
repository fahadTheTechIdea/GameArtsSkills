#!/usr/bin/env python3
"""Game Arts lifecycle owner: generated -> approved -> revoked for mockups and production assets.

Used INTERNALLY by Claude/Codex. Never derive a production source from a revoked/rejected/superseded record. Every
transition keeps the complete bundle, backs up the manifest, runs under one manifest lock and verifies its own result.

Operations (all take --game-root): check-settings, confirm-settings, register, register-generated, import-mockup, audit-mockup, approve-mockup, extract-scene, detect-scene, remove-scene, evaluate-scene,
register-asset, audit, approve, select, list, revoke, restore, reconcile, reconcile-assets.

Every operation that changes a record rebuilds the art report (.gamearts/system/report/index.html) and names it in its result.
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import gamearts_presets as presets
import gamearts_setup as setup_wizard  # noqa: E402

KINDS = ("assets", "mockups")
STATES = {"approved", "generated", "revoked"}
STATE_FIELD = "status"
REVIEW_PROTOCOLS = ("review_packet", "review_packet_v1")  # the second spelling exists in already-approved assets
APPROVAL_VALUES = ("user_granted", "approved", "granted")
TOOL_MODES = ("built_in_image_gen", "cli_image_gen", "connected_tool", "external_import")
SCOPES = ("world", "scene", "asset", "character", "ui_screen", "ui_flow", "mixed", "style")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


# ------------------------------------------------------------------------------------------------ plumbing
def _paths(game_root, kind):
    root = common.game_root(game_root)
    if kind not in KINDS:
        raise ValueError("Invalid lifecycle type")
    return root, root / ".gamearts" / "outputs", root / ".gamearts" / "outputs" / "manifests" / (kind + ".json")


def manifest_lock(root):
    """One lock for every lifecycle write in a game, shared by both agents; the operating system releases it if its owner dies."""
    return common.file_lock(Path(root).resolve() / ".gamearts" / "system" / "manifests.lock", wait_seconds=30, name="lifecycle change")


def _read(game_root, kind):
    root, out, file = _paths(game_root, kind)
    if not file.is_file():
        raise ValueError(f"Missing {kind} lifecycle manifest")
    data = common.read_json(file)
    rows = data.get(kind) if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"Invalid {kind} lifecycle manifest")
    return root, out, file, data, rows


def _read_or_empty(game_root, kind):
    """Like `_read`, but a game that has registered nothing yet has no manifest: that is an empty list, not an error."""
    root, out, file = _paths(game_root, kind)
    if not file.is_file():
        return root, out, file, {}, []
    return _read(game_root, kind)


def _id(record, kind):
    return record.get("asset_id" if kind == "assets" else "mockup_id", record.get("id"))


def _record(rows, kind, item_id, revision=None):
    found = [r for r in rows if isinstance(r, dict) and _id(r, kind) == item_id
             and (revision is None or r.get("revision", r.get("mockup_revision")) == revision)]
    if len(found) != 1:
        raise ValueError(f"Expected one exact {kind} record for {item_id!r}, got {len(found)}")
    return found[0]


def _storage_path(root, out, record, kind):
    status = record.get(STATE_FIELD)
    if status not in STATES:
        raise ValueError(f"Unknown lifecycle state {status!r}; deny selection")
    rel = record.get("bundle_path" if kind == "assets" else "file")
    if not isinstance(rel, str) or not rel:
        raise ValueError("Lifecycle record has no managed path")
    candidate = (root / rel).resolve()
    if not common.inside(candidate, out / kind / status):
        raise ValueError("Lifecycle record state disagrees with its physical folder")
    if not candidate.exists() or candidate.is_symlink():
        raise ValueError("Lifecycle file/bundle is missing or a symlink")
    return candidate


def _bundle_file(folder, name):
    """The single rule for a declared bundle file: relative, inside the bundle, nested paths allowed, must exist."""
    target = common.safe_member(folder, name, "bundle file")
    if not target.is_file():
        raise ValueError(f"missing or unsafe bundle file: {name}")
    return target


def _game_id(root):
    try:
        settings, _, _ = common.load_project_settings(root, require_confirmed=False)
        return settings.get("project_id", Path(root).name)
    except ValueError:
        return Path(root).name


def _normalize_manifest(root, kind, data):
    data.setdefault("schema_version", "1.0")
    data.setdefault("game_id", _game_id(root))
    data.setdefault(kind, [])
    return data


def _write_manifest(root, kind, data):
    """Atomic replace through a unique temp name; validates the whole manifest shape (not legacy record content)."""
    data = _normalize_manifest(root, kind, data)
    if not isinstance(data.get(kind), list) or data.get("schema_version") != "1.0":
        raise ValueError(f"Refusing to write an invalid {kind} manifest")
    _, _, path = _paths(root, kind)
    common.atomic_write_json(path, data)


def _backup(root, label, source_path):
    backups = Path(root).resolve() / ".gamearts" / "system" / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    target = backups / f"{label}_{_stamp()}.json"
    common.atomic_write_bytes(target, Path(source_path).read_bytes())
    return target


def _ensure_manifest(root, kind):
    _, _, manifest_path = _paths(root, kind)
    if manifest_path.is_file():
        data = common.read_json(manifest_path)
        if not isinstance(data.get(kind), list):
            raise ValueError(f"Invalid {kind} lifecycle manifest")
        return manifest_path, data
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data = _normalize_manifest(root, kind, {})
    common.atomic_write_json(manifest_path, data)
    return manifest_path, data


def _try(problems, label, action):
    """Run one best-effort rollback step and record (never swallow) its failure."""
    try:
        action()
    except OSError as exc:
        problems.append(f"{label}: {exc}")


def _snapshot(paths):
    """Bytes of the files a transition will rewrite, so a rollback restores their content and not only their location."""
    return {Path(p): Path(p).read_bytes() for p in paths if p is not None}


def _roll_back(failure, moved, contents, manifest_path, manifest_bytes):
    """Undo a failed transition and re-raise it: move files back, restore rewritten contents, restore the manifest.

    Each step that itself fails is named in the error beside the original failure; nothing is swallowed. Never returns.
    """
    problems = []
    for current, original in reversed(moved):
        if current.exists() and not original.exists():
            _try(problems, f"move {current.name} back", lambda c=current, o=original: common.move_path(c, o))
    for path, data in contents.items():
        if path.parent.is_dir():
            _try(problems, f"restore content of {path.name}", lambda p=path, d=data: common.atomic_write_bytes(p, d))
        else:
            problems.append(f"restore content of {path.name}: its folder {path.parent.name} is missing")
    _try(problems, "restore manifest", lambda: common.atomic_write_bytes(manifest_path, manifest_bytes))
    if problems:
        raise ValueError(f"{failure}; ROLLBACK INCOMPLETE, inspect by hand: {'; '.join(problems)}") from failure
    raise failure


# ------------------------------------------------------------------------------------------------ settings
def _settings_snapshot(root):
    """(settings, canonical_hash, raw_hash); the project file must pass its schema and be owner_confirmed."""
    return common.load_project_settings(root)


def _anchor_summary(root, settings):
    anchor = common.resolve_style_anchor(root, settings)
    return None if anchor is None else {key: anchor[key] for key in ("id", "revision", "status", "scope", "problem")}


def _settings_warnings(settings):
    """Things valid settings can still get wrong, said once and never refused: a diamond grid whose tile is not 2:1, a square tile that disagrees with the scale."""
    warnings = []
    world = settings.get("world") or {}
    tile = world.get("ground_tile_px")
    if world.get("grid") == "isometric" and tile and tile[0] != 2 * tile[1]:
        warnings.append(f"world.grid is isometric but ground_tile_px is {tile[0]} x {tile[1]}, which is not 2:1; a 2:1 diamond is twice as wide as it is tall. "
                        "Confirm the tile size with the owner (a different ratio needs world.grid custom).")
    meters, per_meter = world.get("logical_tile_m"), world.get("pixels_per_meter")
    if world.get("grid") == "orthogonal_square" and tile and meters and per_meter and any(abs(m * per_meter - px) > 1e-6 for m, px in zip(meters, tile)):
        warnings.append(f"world.ground_tile_px is {tile[0]} x {tile[1]}, but logical_tile_m {meters[0]} x {meters[1]} at {per_meter} pixels per metre makes a tile "
                        f"{meters[0] * per_meter:g} x {meters[1] * per_meter:g}. Confirm the tile size and the scale with the owner.")
    return warnings


def confirm_settings(game_root, confirmed_by, confirmation_reference, presented_version=None):
    """Record the owner's confirmation of the saved settings: the real time, who, and the owner's words. Nothing else in the file changes."""
    if not (confirmed_by or "").strip() or not (confirmation_reference or "").strip():
        raise ValueError("Say who confirmed (--by) and quote the owner's words (--user-confirmation-ref); a confirmation is never invented")
    root = common.game_root(game_root)
    settings, _, _ = common.load_project_settings(root, require_confirmed=False)
    chosen = setup_wizard.setup_problems(settings)
    shown = setup_wizard.version((settings.get("setup") or {}).get("answers") or {})
    if not chosen and presented_version != shown:  # the owner confirms exactly the settings they were shown, not whatever the file says now
        chosen = [f"the version shown to the owner ({presented_version or 'none given'}) is not the version of these settings ({shown}); show the owner the written summary and its version"]
    if chosen:  # every setting is the owner's own pick: nothing is confirmed while one was filled in for them
        raise ValueError("These settings cannot be confirmed yet: " + "; ".join(chosen) + ". Run the setup wizard (gamearts_setup.py next) and ask each question")
    settings.update({"settings_status": "owner_confirmed", "confirmed_at": _now(), "confirmed_by": confirmed_by.strip(),
                     "confirmation_ref": confirmation_reference.strip()})
    common.validate_schema(settings, "gamearts-project")
    common.atomic_write_json(root / ".gamearts" / "project.json", settings)
    return check_settings(root)


def check_settings(game_root):
    root = common.game_root(game_root)
    settings, canonical, raw = common.load_project_settings(root, require_confirmed=False)
    engine = presets.resolve_engine_target(settings)
    return {"status": "valid", "settings_status": settings.get("settings_status", "unset"),
            "owner_confirmed": settings.get("settings_status") == "owner_confirmed", "material_settings_sha256": canonical,
            "warnings": _settings_warnings(settings),
            "setup": {"complete": not setup_wizard.setup_problems(settings), "problems": setup_wizard.setup_problems(settings),
                      "version": setup_wizard.version((settings.get("setup") or {}).get("answers") or {})},
            "image_generation": settings.get("image_generation"), "world_kind": common.world_kind(settings),
            "directions": common.resolve_directions(settings), "screen": settings.get("screen"),
            "engine_target": engine, "style_preset": presets.resolve_style_preset(settings), "style_anchor": _anchor_summary(root, settings),
            "integration_notes": [] if engine.get("problem") else presets.integration_notes(settings)}


# ------------------------------------------------------------------------------------------------ technical gate
def _gate_settings(root):
    """(settings, problem) for the style part of the technical gate. Settings that cannot be read are returned as a problem to record,
    never skipped silently and never a reason to block (the same file is checked strictly wherever a mockup is registered)."""
    try:
        settings, _, _ = common.load_project_settings(root, require_confirmed=False)
        return settings, None
    except ValueError as exc:
        return None, str(exc)


def technical_check_bundle(folder, settings=None, settings_problem=None, root=None, limited_profile=None):
    """Mechanical artwork gate for an asset bundle: every sheet's atlas and exact-key pixels, the component gate, and the style checks
    the game's preset requires. `settings` (with `root`, to find the game's palette) turns the style checks on; without them the result
    says they were not applicable or, when `settings_problem` is given, untested and why. `limited_profile` is the asset's recorded owner approval
    of a limited facing set, which lets a bundle that faces only some of the game's directions pass the settings-fit check."""
    from validate_component_bundle import validate as validate_bundle
    from validate_settings_fit import fit_report
    from validate_sheet_atlas import validate as validate_sheet
    from validate_style_conformance import bundle_report
    from validate_tileset import validate as validate_tileset
    folder = Path(folder)
    issues, atlases = [], sorted(folder.glob("*.atlas.json"))
    bundles = list(folder.glob("*.bundle.json"))
    if not atlases and not bundles:
        issues.append("bundle has no production sheet: it needs at least one <name>.atlas.json (a standalone image is a one-frame atlas)")
    for atlas in atlases:
        try:
            image = folder / common.read_json(atlas)["image"]
        except (ValueError, KeyError, OSError) as exc:
            issues.append(f"{atlas.name}: unreadable atlas ({exc})")
            continue
        issues += [f"{atlas.name}: {problem}" for problem in validate_sheet(image, atlas)]
    gate = "not_applicable"
    if bundles:
        problems = validate_bundle(folder, approval_gate=True)
        issues += [f"component bundle: {p}" for p in problems]
        gate = "failed" if problems else "passed"
    tilesets = sorted(folder.glob("*.tileset.json"))
    for tileset in tilesets:  # the sheet itself was checked above with its atlas
        issues += [f"{tileset.name}: {problem}" for problem in validate_tileset(tileset, check_sheet=False)]
    chosen = presets.resolve_style_preset(settings) if settings else None
    if chosen and chosen.get("found") and not chosen["soft_edges"]:  # a look with hard edges has nothing for a matte to carry
        issues += [f"{atlas.name}: carries a matte, but the {chosen['preset']} look has hard edges and never gets one" for atlas in atlases if "matte" in common.read_json(atlas)]
    style = bundle_report(folder, [a for a in atlases if not any(i.startswith(a.name) for i in issues)], settings, root, settings_problem)
    issues += style.pop("issues")
    result = {"status": "failed" if issues else "passed", "checked_at_utc": _now(),
              "atlases": [a.name for a in atlases], "bundle_gate": gate, "style_conformance": style,
              "settings_fit": fit_report(folder, settings, settings_problem, limited_profile), "issues": issues}
    if tilesets:
        result["tilesets"] = [tileset.name for tileset in tilesets]
    return result


RUNTIME_STORE = "runtime"  # .gamearts/outputs/runtime/<asset id>/<revision>/: derived files, kept apart from every status folder


def _derived_issues(root, out, record, entry, folder):
    """Everything wrong with one recorded derived export of an asset; empty when it is sound, current and where the record says."""
    import export_runtime as exporter
    if record.get("status") != "approved":
        return ["derived files exist for an asset that is not approved"]
    target = (root / entry["path"]).resolve()
    if not common.inside(target, out / RUNTIME_STORE) or not target.is_dir():
        return [f"{entry['path']} is missing or outside the runtime store"]
    manifest = target / exporter.MANIFEST
    if not manifest.is_file() or common.sha256_file(manifest) != entry["manifest_sha256"]:
        return [f"{entry['path']}: its manifest is missing or differs from the one recorded"]
    return exporter.verify_export(target, folder)


def export_runtime(game_root, item_id, revision=None, replace=False):
    """Write the engine-ready copies (the key colour made real transparency) of one APPROVED asset into the runtime store and record them on the asset.

    The copies are derived: they are never approved, never a source for new art, listed on the record as `derived_exports`, checked by reconcile and
    removed if the asset is revoked. Existing ones are kept unless `replace` is set, and a replacement that fails restores the previous copies."""
    import export_runtime as exporter
    problems = audit_asset(game_root, item_id)
    if problems:
        raise ValueError("The asset fails its audit, so nothing is derived from it: " + "; ".join(problems[:3]))
    with manifest_lock(game_root):
        root, out, file, data, rows = _read(game_root, "assets")
        record = _record(rows, "assets", item_id, revision)
        if record.get("status") != "approved":
            raise ValueError("Only an approved asset gets runtime files: approve it first")
        source = _storage_path(root, out, record, "assets")
        target = out / RUNTIME_STORE / _id(record, "assets") / record["revision"]
        previous = None
        if target.exists():
            if not replace:
                raise ValueError("Runtime files for this asset already exist; ask to replace them if the art changed")
            previous = target.with_name(target.name + ".replaced")
            if previous.exists():
                shutil.rmtree(previous)
            common.move_path(target, previous)
        try:
            manifest = exporter.export_bundle(source, target)
            entry = {"kind": "runtime", "path": target.relative_to(root).as_posix(), "manifest_sha256": common.sha256_file(target / exporter.MANIFEST),
                     "created_at_utc": _now(), "status": "derived"}
            record["derived_exports"] = [e for e in record.get("derived_exports", []) if e["kind"] != "runtime"] + [entry]
            common.validate_schema(record, "gamearts-assets-manifest", ("properties", "assets", "items"))
            _backup(root, "assets_pre_runtime_export", file)
            _write_manifest(root, "assets", data)
        except BaseException:
            if target.exists():
                shutil.rmtree(target)
            if previous is not None:
                common.move_path(previous, target)  # the replacement failed: the previous copies are put back untouched
            raise
        if previous is not None:
            shutil.rmtree(previous)
    return {"asset_id": _id(record, "assets"), "revision": record["revision"], "kind": "runtime", "path": entry["path"],
            "files": [item["path"] for item in manifest["files"]] + [exporter.MANIFEST], "derived": True}


def auto_exports(game_root, item_id):
    """The derived files this game's engine profile asks for when an asset is approved, made now. Returns {kind: outcome}; empty when the profile
    asks for none. The approval has already happened, so a failure is reported in the outcome and never undoes it."""
    root = common.game_root(game_root)
    settings, problem = _gate_settings(root)
    if settings is None:
        return {"settings": {"status": "unread", "reason": problem}}
    exporters = {"runtime": export_runtime}
    outcomes = {}
    for kind in presets.resolve_engine_target(settings).get("default_exports", []):
        try:
            outcomes[kind] = {"status": "written", **exporters[kind](root, item_id)}
        except (OSError, ValueError) as exc:  # reported to the caller in the outcome; the approval is already recorded
            outcomes[kind] = {"status": "failed", "reason": str(exc)}
    return outcomes


def approve_batch(game_root, kind, items, shown, user_approval_reference):
    """Approve a named list of exact revisions on one user reference.

    Each item goes through the ordinary single approval (`approve_mockup` or `approve_asset`), so each has its own gate, audit and rollback. An item that
    was not among those shown to the owner, is not waiting for approval, does not exist, or fails its gate is reported with the reason and left as it
    was, and the rest go ahead. `items` and `shown` are lists of (id, revision). The result lists what was approved and what was not."""
    if kind not in ("mockups", "assets"):
        raise ValueError("A batch approves mockups or assets")
    if not isinstance(user_approval_reference, str) or not user_approval_reference.strip():
        raise ValueError("A batch needs the owner's approval reference (their own words), never an invented one")
    if not items:
        raise ValueError("Name at least one item to approve")
    if len(set(items)) != len(items):
        raise ValueError("An item is named more than once")
    shown = set(shown)
    approved, left = [], []
    for item_id, revision in items:
        label = f"{item_id}:{revision}"
        if (item_id, revision) not in shown:
            left.append({"item": label, "reason": "it was not among the items shown to the owner for this approval"})
            continue
        try:
            if kind == "mockups":
                approve_mockup(game_root, item_id, revision, user_approval_reference)
            else:
                rows = _read(game_root, "assets")[4]
                if not any(_id(r, "assets") == item_id and r.get("revision") == revision for r in rows if isinstance(r, dict)):
                    raise ValueError(f"no asset {item_id} with revision {revision} is registered")
                approve_asset(game_root, item_id, user_approval_reference)
        except (ValueError, OSError) as exc:  # reported against this item; the others go ahead and this one stays as it was (the single path rolls back)
            left.append({"item": label, "reason": str(exc)})
            continue
        approved.append(label)
    return {"kind": kind, "approved": approved, "not_approved": left, "ok": not left}


def _needs_packet(folder, record):
    if record.get("visual_review_protocol") in REVIEW_PROTOCOLS:
        return True
    for item in Path(folder).glob("*.bundle.json"):
        if common.read_json(item).get("visual_review_protocol") in REVIEW_PROTOCOLS:
            return True
    for item in Path(folder).glob("*.blueprint.json"):
        proof = common.read_json(item).get("visual_review_evidence", {})
        if isinstance(proof, dict) and proof.get("review_protocol") in REVIEW_PROTOCOLS:
            return True
    return False


# ------------------------------------------------------------------------------------------------ asset audit
def audit_asset(game_root, item_id, notes=None):
    """Check a recorded asset's lifecycle, source and metadata consistency (file/manifest audit, not art quality).

    Returns blocking issues. Non-blocking observations (for example a legacy approval without a recorded technical gate)
    are appended to `notes` when a list is passed.
    """
    notes = notes if notes is not None else []
    root, out, _, data, rows = _read(game_root, "assets")
    record = _record(rows, "assets", item_id)
    issues = []
    try:
        folder = _storage_path(root, out, record, "assets")
    except (ValueError, OSError) as exc:
        return [str(exc)]
    status = record.get("status")
    if status == "approved" and (record.get("visual_review") != "approved" or record.get("approval") not in APPROVAL_VALUES):
        issues.append("approved manifest missing explicit user visual/art approval")
    required = record.get("files", [])
    if not isinstance(required, list) or not required:
        issues.append("asset manifest lacks declared bundle files")
        required = []
    for filename in required:
        try:
            _bundle_file(folder, filename)
        except ValueError:
            issues.append(f"missing or unsafe bundle file: {filename}")
    mockups = record.get("source_mockups", [])
    if status == "approved" and not mockups:
        issues.append("approved asset has no approved source mockup linkage")
    if mockups:
        try:
            _, _, _, _, references = _read(game_root, "mockups")
        except (OSError, ValueError, TypeError) as exc:
            issues.append(f"cannot validate approved sources: {exc}")
            references = []
        for ref in mockups:
            if not isinstance(ref, dict):
                issues.append("invalid source mockup reference")
                continue
            matches = [m for m in references if isinstance(m, dict) and _id(m, "mockups") == ref.get("mockup_id")
                       and m.get("revision", m.get("mockup_revision")) == ref.get("revision")]
            if len(matches) != 1 or matches[0].get("status") != "approved":
                issues.append("asset refers to a missing or nonapproved mockup")
                continue
            m = matches[0]
            try:
                image = _storage_path(root, out, m, "mockups")
                recorded_hash = m.get("sha256")
                ref_hash = ref.get("reference_sha256", ref.get("sha256"))
                if not recorded_hash or not ref_hash or recorded_hash != ref_hash:
                    issues.append("asset source mockup hash disagrees with approved manifest")
                elif common.sha256_file(image) != recorded_hash:
                    issues.append("approved source mockup image bytes have changed")
            except (OSError, ValueError) as exc:
                issues.append(f"approved source unavailable: {exc}")
    if record.get("source_assets"):
        try:
            _, _, _, _, asset_rows = _read(game_root, "assets")
        except (OSError, ValueError, TypeError) as exc:
            issues.append(f"cannot validate source assets: {exc}")
            asset_rows = []
        for ref in record["source_assets"]:
            found = [a for a in asset_rows if isinstance(a, dict) and _id(a, "assets") == ref.get("asset_id") and a.get("revision") == ref.get("revision")]
            if len(found) != 1 or found[0].get("status") != "approved":
                issues.append(f"asset is made from {ref.get('asset_id')} {ref.get('revision')}, which is missing or no longer approved")
    checksums = record.get("artifact_hashes")
    if checksums is not None:
        if not isinstance(checksums, dict) or not checksums:
            issues.append("approved asset has invalid artifact hashes")
        else:
            for rel, expected in checksums.items():
                try:
                    file = common.safe_member(folder, rel, "artifact")
                    if not file.is_file() or common.sha256_file(file) != expected:
                        raise ValueError
                except ValueError:
                    issues.append(f"approved artifact bytes changed since acceptance: {rel}")
    for bp in folder.glob("*.blueprint.json"):
        try:
            body = common.read_json(bp)
        except (OSError, ValueError) as exc:
            issues.append(f"invalid blueprint {bp.name}: {exc}")
            continue
        if status == "approved" and isinstance(body, dict):
            if str(body.get("status", "")).startswith("generated") or body.get("status") in ("pending", "rejected"):
                issues.append(f"{bp.name}: blueprint still reports unapproved status")
            if body.get("production_approval") in ("not_granted", "pending", "rejected", False):
                issues.append(f"{bp.name}: blueprint contradicts recorded production approval")
            if body.get("approved_clean_plate") is False and str(body.get("clean_plate_approval", "")).startswith("approved"):
                issues.append(f"{bp.name}: clean-plate approval fields contradict each other")
            visual = body.get("user_visual_approval")
            if isinstance(visual, dict) and visual.get("status") not in ("approved", "user_granted"):
                issues.append(f"{bp.name}: blueprint visual approval disagrees with manifest")
    for report in folder.glob("*.validation.json"):
        try:
            body = common.read_json(report)
        except (OSError, ValueError) as exc:
            issues.append(f"invalid validation report {report.name}: {exc}")
            continue
        if status == "approved" and isinstance(body, dict):
            if body.get("status") in ("generated", "pending", "rejected"):
                issues.append(f"{report.name}: validation status contradicts approval")
            sprite_status = body.get("isolated_props_background_masking")
            if isinstance(sprite_status, str) and "pending_user_review" in sprite_status:
                issues.append(f"{report.name}: sprite review is still marked pending")
    requires_review = _needs_packet(folder, record)
    if status == "approved" and requires_review and record.get("visual_review_protocol") not in REVIEW_PROTOCOLS:
        issues.append("new composite asset cannot omit mandatory visual-review protocol from approved manifest")
    if status == "approved" and record.get("visual_review_protocol") in REVIEW_PROTOCOLS:
        slots = record.get("visual_reviews")
        if not isinstance(slots, list) or not slots:
            issues.append("approved asset lacks mandatory user visual review packet")
        else:
            for index, slot in enumerate(slots):
                issues += _audit_review_slot(folder, record, slot, index)
    elif status == "approved" and record.get("visual_review_protocol") not in (None, "legacy", *REVIEW_PROTOCOLS):
        issues.append("approved asset declares unknown visual-review protocol")
    if status == "approved":
        technical = record.get("technical_validation")
        if technical is None:
            notes.append("legacy approval: no technical artwork gate was recorded when this asset was approved")
        elif technical.get("status") != "passed":
            issues.append("recorded technical artwork gate did not pass")
    return issues


def _audit_review_slot(folder, record, slot, index):
    issues = []
    if not isinstance(slot, dict):
        return [f"visual review {index}: invalid record"]
    paths = []
    for key in ("packet", "decision"):
        rel = slot.get(key)
        try:
            candidate = common.safe_member(folder, rel, f"visual review {index} {key}")
            if not candidate.is_file():
                raise ValueError("missing")
        except ValueError:
            return [f"visual review {index}: missing or unsafe {key} file"]
        paths.append(candidate)
    try:
        from visual_review_cleanup import verify as verify_visual_cleanup
        verified = verify_visual_cleanup(paths[0], paths[1])
        if verified["asset_id"] != _id(record, "assets"):
            issues.append(f"visual review {index}: approved different asset ID")
        if record.get("revision") and verified["revision"] != record["revision"]:
            issues.append(f"visual review {index}: approved different revision")
        sources = [m for m in record.get("source_mockups", []) if isinstance(m, dict)]
        matched = next((m for m in sources if m.get("mockup_id") == verified.get("approved_mockup_id")
                        and m.get("revision") == verified.get("approved_mockup_revision")), None)
        if matched is None:
            issues.append(f"visual review {index}: displayed mockup is not the asset's approved source")
        elif verified.get("approved_mockup_source_sha256") != matched.get("reference_sha256", matched.get("sha256")):
            issues.append(f"visual review {index}: displayed approved crop comes from different source image hash")
    except (ImportError, OSError, ValueError, TypeError, KeyError) as err:
        issues.append(f"visual review {index}: invalid approval evidence: {err}")
    return issues


# ------------------------------------------------------------------------------------------------ select / list
def select(game_root, kind, stage, item_id=None, revision=None, report=False):
    """Eligible records for production use. With an id a failure raises; without one, failing records are reported
    (report=True returns {"eligible", "blocked"}) instead of hiding or aborting the rest."""
    if stage not in ("approved", "generated"):
        raise ValueError("Only approved production references or generated candidates may be selected")
    root, out, _, data, rows = _read_or_empty(game_root, kind)
    choices = [_record(rows, kind, item_id, revision)] if item_id else [r for r in rows if isinstance(r, dict)]
    eligible, blocked = [], []
    for record in choices:
        status = record.get(STATE_FIELD)
        if status == "revoked" or record.get("approval") == "rejected" or record.get("visual_review") == "rejected":
            if item_id:
                raise ValueError("REJECTED/REVOKED asset cannot be used: " + str(_id(record, kind)))
            continue
        if status != stage:
            if item_id:
                raise ValueError(f"Item {_id(record, kind)} is {status}, not {stage}; do not bypass lifecycle")
            continue
        try:
            path = _storage_path(root, out, record, kind)
            if stage == "approved" and kind == "assets":
                problems = audit_asset(game_root, _id(record, "assets"))
                if problems:
                    raise ValueError("Approved asset metadata audit failed: " + "; ".join(problems))
            if stage == "approved" and kind == "mockups":
                expected = record.get("sha256")
                if not expected:
                    raise ValueError("Approved mockup source is missing registered SHA256")
                if common.sha256_file(path) != expected:
                    raise ValueError("Approved mockup hash mismatch; source cannot be used")
        except (ValueError, OSError) as exc:
            if item_id:
                raise
            blocked.append({"id": _id(record, kind), "revision": record.get("revision"), "reason": str(exc)})
            continue
        eligible.append({"id": _id(record, kind), "status": status, "path": str(path)})
    return {"eligible": eligible, "blocked": blocked} if report else eligible


def records(game_root, kind):
    """Every record of a kind exactly as the manifest holds it (a game that has registered nothing has none)."""
    return [dict(row) for row in _read_or_empty(game_root, kind)[4] if isinstance(row, dict)]


def list_records(game_root, kind, status=None):
    _, _, _, _, rows = _read_or_empty(game_root, kind)
    keep = ("status", "revision", "approval", "visual_review", "replaced_by", "revocation_reason", "storyboard_scene_id")
    return [{"id": _id(r, kind), **{k: r[k] for k in keep if k in r}} for r in rows
            if isinstance(r, dict) and (status is None or r.get(STATE_FIELD) == status)]


# ------------------------------------------------------------------------------------------------ asset register / approve
def _require_scene_extraction(root, mockup, label):
    """A world, scene or mixed mockup that has a blueprint is taken through the extraction before any asset is built from it, and the extraction
    on record must still be the one on disk (its manifest unchanged). A mockup of another scope, or one with no blueprint, is not held to this."""
    if mockup.get("scope") not in SCENE_SCOPES or not mockup.get("blueprint"):
        return
    done = mockup.get("scene_extraction")
    if not done:
        raise ValueError(f"source mockup {label} is a scene with a blueprint and has not been extracted: run extract-scene first")
    manifest = common.safe_member(root, done["path"] + "/extraction.json", "scene extraction")
    if not manifest.is_file() or common.sha256_file(manifest) != done.get("manifest_sha256"):
        raise ValueError(f"source mockup {label}: its recorded extraction is missing or has changed since it was recorded; run extract-scene again on a new revision")


def register_asset(game_root, asset_id, revision, bundle, source_mockups, extra=None, source_assets=None, limited_profile_ref=None):
    """Register a generated asset bundle (already inside assets/generated) with verified source links and a technical check.
    `source_assets` ([(asset_id, revision)]) names approved assets this one was made from, as a palette variant names its base.
    `limited_profile_ref` is the owner's own words approving a bundle that faces only some of the game's directions; it is refused for a bundle
    that does not need it, so it can never be recorded and then ignored."""
    root, out, _ = _paths(game_root, "assets")
    if not common.SLUG.fullmatch(asset_id or "") or not common.REVISION.fullmatch(revision or ""):
        raise ValueError("asset_id must be a filename-safe ID and revision must look like v001")
    folder = common.safe_member(root, bundle, "bundle")
    if folder.parent != (out / "assets" / "generated").resolve() or not folder.is_dir() or folder.is_symlink():
        raise ValueError("bundle must be a folder directly inside .gamearts/outputs/assets/generated")
    with manifest_lock(root):
        manifest_path, manifest = _ensure_manifest(root, "assets")
        rows = manifest["assets"]
        if any(_id(r, "assets") == asset_id and r.get("revision") == revision for r in rows if isinstance(r, dict)):
            raise ValueError("Asset id and revision already registered; create a new revision")
        links = []
        if not source_mockups:
            raise ValueError("an asset must name at least one approved source mockup (id:revision)")
        _, _, _, _, mockup_rows = _read(root, "mockups")
        for mockup_id, mockup_revision in source_mockups:
            match = _record(mockup_rows, "mockups", mockup_id, mockup_revision)
            if match.get("status") != "approved":
                raise ValueError(f"source mockup {mockup_id} {mockup_revision} is not approved")
            path = _storage_path(root, out, match, "mockups")
            if common.sha256_file(path) != match.get("sha256"):
                raise ValueError(f"source mockup {mockup_id} {mockup_revision} bytes differ from the approved hash")
            _require_scene_extraction(root, match, f"{mockup_id} {mockup_revision}")
            links.append({"mockup_id": mockup_id, "revision": mockup_revision, "reference_sha256": match["sha256"]})
        asset_links = []
        for source_id, source_revision in source_assets or []:
            if (source_id, source_revision) == (asset_id, revision):
                raise ValueError("an asset cannot be made from itself")
            found = next((r for r in rows if isinstance(r, dict) and _id(r, "assets") == source_id and r.get("revision") == source_revision), None)
            if found is None or found.get("status") != "approved":
                raise ValueError(f"source asset {source_id} {source_revision} is not an approved asset; a variant is made from approved art only")
            if any(link["asset_id"] == source_id and link["revision"] == source_revision for link in asset_links):
                raise ValueError(f"source asset {source_id} {source_revision} is named twice")
            asset_links.append({"asset_id": source_id, "revision": source_revision})
        files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and not p.name.startswith("."))
        if limited_profile_ref is not None and not str(limited_profile_ref).strip():
            raise ValueError("A limited facing profile needs the owner's own words approving it (--limited-profile-ref)")
        limited = {"approval_ref": limited_profile_ref.strip()} if limited_profile_ref else None
        technical = technical_check_bundle(folder, *_gate_settings(root), root=root, limited_profile=limited)
        if limited and not any(item.get("limited_profile") for item in technical["settings_fit"].get("checks", [])):
            raise ValueError("A limited facing profile applies only to a component bundle that faces some, but not all, of the game's directions; "
                             "this bundle does not, so there is nothing to approve")
        record = {"asset_id": asset_id, "revision": revision, "status": "generated", "bundle_path": folder.relative_to(root).as_posix(),
                  "files": files, "approval": "pending", "visual_review": "pending", "source_mockups": links,
                  "technical_validation": technical, "engine_validation": "not_tested", "registered_at_utc": _now()}
        if asset_links:
            record["source_assets"] = asset_links
        if limited:
            record["limited_profile"] = limited
        for key in ("provenance", "rights"):
            if extra and key in extra:
                record[key] = extra[key]
        if _needs_packet(folder, {}):
            record["visual_review_protocol"] = "review_packet"
        common.validate_schema(record, "gamearts-assets-manifest", ("properties", "assets", "items"))
        _backup(root, "assets_pre_register", manifest_path)
        rows.append(record)
        _write_manifest(root, "assets", manifest)
    return {"asset_id": asset_id, "revision": revision, "status": "generated", "technical_validation": technical["status"],
            "technical_issues": technical["issues"], "files": len(files)}


def approve_asset(game_root, item_id, user_approval_reference, review_records=None):
    """Promote ONE exact generated asset after the technical artwork gate, integrity checks and genuine user review.

    The user's actual message cannot be host-attested by a JSON file. Agents MUST call this only after observing the
    user's explicit acceptance.
    """
    if not isinstance(user_approval_reference, str) or not user_approval_reference.strip():
        raise ValueError("Explicit user approval message reference is required")
    root, out, manifest_path, manifest, records = _read(game_root, "assets")
    with manifest_lock(root):
        root, out, manifest_path, manifest, records = _read(game_root, "assets")  # re-read under the lock
        record = _record(records, "assets", item_id)
        if record.get("status") != "generated":
            raise ValueError("Only a generated non-rejected asset can be approved")
        if record.get("visual_review") == "rejected" or record.get("approval") == "rejected":
            raise ValueError("Rejected artwork cannot be approved without a new candidate")
        src = _storage_path(root, out, record, "assets")
        if not src.is_dir():
            raise ValueError("Expected complete generated asset bundle folder")
        destination = out / "assets" / "approved" / src.name
        if destination.exists():
            raise FileExistsError("Target approved asset revision already exists")
        required = record.get("files", [])
        if not isinstance(required, list) or not required:
            raise ValueError("Asset must declare required production files")
        for name in required:
            try:
                _bundle_file(src, name)
            except ValueError:
                raise ValueError("Required generated bundle file is missing or unsafe: " + str(name)) from None
        technical = technical_check_bundle(src, *_gate_settings(root), root=root, limited_profile=record.get("limited_profile"))
        if technical["status"] != "passed":
            raise ValueError("Technical artwork gate failed: " + "; ".join(technical["issues"]))
        needs_packet = _needs_packet(src, record)
        selections = review_records if review_records is not None else record.get("visual_reviews", [])
        if not isinstance(selections, list):
            raise ValueError("Review records must be an array")
        if needs_packet and not selections:
            raise ValueError("Mandatory visual acceptance packet missing for new composite asset")
        if selections:
            from visual_review_cleanup import verify as verify_visual
            for slot in selections:
                if not isinstance(slot, dict):
                    raise ValueError("Invalid visual-review slot")
                links = {key: common.safe_member(src, slot.get(key), f"visual review {key}") for key in ("packet", "decision")}
                checked = verify_visual(links["packet"], links["decision"])
                if checked.get("asset_id") != item_id:
                    raise ValueError("Visual acceptance reviewed another asset")
                if record.get("revision") and checked.get("revision") != record["revision"]:
                    raise ValueError("Visual acceptance reviewed a different revision")
                if common.read_json(links["decision"]).get("user_approval_reference") != user_approval_reference:
                    raise ValueError("User acceptance reference disagrees with actual recorded decision")
        old_manifest = manifest_path.read_bytes()
        backup_file = _backup(root, f"assets_pre_approval_{''.join(c if c.isalnum() or c in '-_' else '_' for c in str(item_id))}", manifest_path)
        changed = {}

        def update_json(path, transform):
            raw = path.read_bytes()
            body = json.loads(raw.decode("utf-8"))
            transform(body)
            changed[path.relative_to(src).as_posix()] = raw
            common.atomic_write_json(path, body)

        def approve_blueprint(body):
            body["status"] = "approved_artwork_not_engine_verified"
            body["production_approval"] = "granted_by_user"
            body["user_visual_approval"] = {"status": "approved", "user_reference": user_approval_reference}
            if selections:
                body["approved_clean_plate"] = True
                body["clean_plate_approval"] = "approved_by_user"
                visual = body.setdefault("visual_review_evidence", {})
                if isinstance(visual, dict):
                    visual["review_protocol"] = "review_packet"
                    visual["review_status"] = "user_visual_approval_recorded"

        def approve_validation(body):
            if body.get("status") not in ("failed", "rejected"):
                body["status"] = "approved_artwork_not_engine_verified"
            if selections:
                body["isolated_props_background_masking"] = "user_approved"
                body["visual_review"] = "approved"

        try:
            for bp in src.glob("*.blueprint.json"):
                update_json(bp, approve_blueprint)
            for qa in src.glob("*.validation.json"):
                update_json(qa, approve_validation)
            destination.parent.mkdir(parents=True, exist_ok=True)
            common.move_path(src, destination)
            record["status"], record["approval"], record["visual_review"] = "approved", "user_granted", "approved"
            record["approved_at_utc"], record["approval_reference"] = _now(), user_approval_reference
            record["bundle_path"] = destination.relative_to(root).as_posix()
            record["technical_validation"] = technical
            if needs_packet or selections:
                record["visual_review_protocol"] = "review_packet"
                record["visual_reviews"] = selections
            # Hash the exact immutable approved bundle so later mutation is detectable without confusing it with engine readiness.
            record["artifact_hashes"] = {f.relative_to(destination).as_posix(): common.sha256_file(f)
                                         for f in sorted(destination.rglob("*")) if f.is_file()}
            _write_manifest(root, "assets", manifest)
            problems = audit_asset(root, item_id)
            if problems:
                raise ValueError("Post-approval asset audit failed: " + "; ".join(problems))
        except Exception as failure:
            _roll_back(failure, [(destination, src)], {src / rel: raw for rel, raw in changed.items()}, manifest_path, old_manifest)
    return {"asset_id": item_id, "status": "approved", "path": str(destination), "manifest_backup": str(backup_file),
            "visual_review_protocol": record.get("visual_review_protocol"), "technical_validation": "passed",
            "engine_validation": "not_assessed_by_approval"}


# ------------------------------------------------------------------------------------------------ revoke / restore
def _dependents(root, mockup_id, revision):
    try:
        _, _, _, _, rows = _read(root, "assets")
    except ValueError:
        return []
    return [{"asset_id": _id(r, "assets"), "status": r.get("status")} for r in rows if isinstance(r, dict) and r.get("status") != "revoked"
            and any(isinstance(m, dict) and m.get("mockup_id") == mockup_id and m.get("revision") == revision
                    for m in r.get("source_mockups", []))]


def _asset_dependents(root, asset_id, revision):
    """Assets (not revoked) that name this asset revision as a source, as a palette variant names its base."""
    try:
        _, _, _, _, rows = _read(root, "assets")
    except ValueError:
        return []
    return [{"asset_id": _id(r, "assets"), "status": r.get("status")} for r in rows if isinstance(r, dict) and r.get("status") != "revoked"
            and any(isinstance(s, dict) and s.get("asset_id") == asset_id and s.get("revision") == revision for s in r.get("source_assets", []))]


def revoke(game_root, kind, item_id, reason, revision=None, replaced_by=None):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Explicit nonempty rejection/revocation reason required")
    root = common.game_root(game_root)
    with manifest_lock(root):
        root, out, file, data, rows = _read(game_root, kind)
        record = _record(rows, kind, item_id, revision)
        prior_state = record.get(STATE_FIELD)
        if prior_state == "revoked":
            raise ValueError("Item is already revoked; do not reprocess rejected artwork")
        if prior_state not in ("generated", "approved"):
            raise ValueError("Only existing generated/approved items can be revoked")
        src = _storage_path(root, out, record, kind)
        dest = out / kind / "revoked" / src.name
        if dest.exists():
            raise FileExistsError("Revoked destination already exists; use exact revision identity")
        if kind == "assets":
            required = record.get("files", [])
            if not isinstance(required, list) or not required:
                raise ValueError("Bundle missing required artifact(s); refuse incomplete revocation")
            for v in required:
                try:
                    _bundle_file(src, v)
                except ValueError:
                    raise ValueError("Bundle missing required artifact(s); refuse incomplete revocation") from None
        backup = _backup(root, f"{kind}_before_{''.join(c if c.isalnum() or c in '_-' else '_' for c in str(item_id))}", file)
        companion_paths = {}
        if kind == "mockups":
            for key in ("metadata", "blueprint"):
                rel = record.get(key)
                if rel:
                    companion = (root / rel).resolve()
                    if not common.inside(companion, src.parent) or not companion.is_file():
                        raise ValueError(f"Mockup {key} companion is missing or unsafe; refuse incomplete revocation")
                    companion_paths[key] = companion
        dependents = (_dependents if kind == "mockups" else _asset_dependents)(root, item_id, record.get("revision"))
        contents = _snapshot(companion_paths.values())
        dest.parent.mkdir(parents=True, exist_ok=True)
        moved = []
        common.move_path(src, dest)
        moved.append((dest, src))
        try:
            new_paths = {"file": dest}
            for key, companion in companion_paths.items():
                target = dest.parent / companion.name
                if target.exists():
                    raise FileExistsError(f"Revoked mockup companion already exists: {target.name}")
                common.move_path(companion, target)
                moved.append((target, companion))
                new_paths[key] = target
            record["status"], record["revocation_reason"], record["revoked_at_utc"] = "revoked", reason.strip(), _now()
            record["approval"], record["visual_review"] = "not_granted", "rejected"
            if replaced_by:
                record["replaced_by"] = replaced_by
            if kind == "assets":
                record["bundle_path"] = dest.relative_to(root).as_posix()
                withdrawn_exports = record.pop("derived_exports", [])
            else:
                for key, path in new_paths.items():
                    record[key] = path.relative_to(root).as_posix()
                _update_metadata_paths(new_paths.get("metadata"), record["file"], record.get("blueprint"))
            _write_manifest(root, kind, data)
        except Exception as failure:
            _roll_back(failure, moved, contents, file, backup.read_bytes())
        if src.exists() or not dest.exists():
            raise OSError("Unable to verify revocation transition")
    result = {"id": item_id, "from": prior_state, "status": "revoked", "path": str(dest), "manifest_backup": str(backup)}
    if kind == "assets" and withdrawn_exports:  # derived copies of withdrawn art must not stay where a game could pick them up
        result["derived_exports_removed"], result["problems"] = [], []
        for entry in withdrawn_exports:
            path = (root / entry["path"]).resolve()
            try:
                if common.inside(path, out / RUNTIME_STORE) and path.is_dir():
                    shutil.rmtree(path)
                result["derived_exports_removed"].append(entry["path"])
            except OSError as exc:  # the revocation is already recorded; say which files are still there
                result["problems"].append(f"{entry['path']} could not be removed ({exc}); delete that folder by hand")
    result["dependents"] = dependents  # approved/generated assets built on this mockup or made from this asset; their next audit will fail
    return result


def restore(game_root, kind, item_id, revision, user_restore_reference):
    """Move a revoked revision back to `generated` (never straight to approved): it must be validated and approved again."""
    if not isinstance(user_restore_reference, str) or not user_restore_reference.strip():
        raise ValueError("A reference to the user's explicit restore request is required")
    root = common.game_root(game_root)
    with manifest_lock(root):
        root, out, file, data, rows = _read(game_root, kind)
        record = _record(rows, kind, item_id, revision)
        if record.get("status") != "revoked":
            raise ValueError("Only a revoked revision can be restored")
        src = _storage_path(root, out, record, kind)
        dest = out / kind / "generated" / src.name
        if dest.exists():
            raise FileExistsError("A generated revision with that name already exists")
        if kind == "assets":
            technical = technical_check_bundle(src, *_gate_settings(root), root=root, limited_profile=record.get("limited_profile"))
            if technical["status"] != "passed":
                raise ValueError("Restore refused; the bundle fails the technical gate: " + "; ".join(technical["issues"]))
        backup = _backup(root, f"{kind}_before_restore", file)
        companions = {}
        if kind == "mockups":
            for key in ("metadata", "blueprint"):
                rel = record.get(key)
                if rel:
                    companion = (root / rel).resolve()
                    if not common.inside(companion, src.parent) or not companion.is_file():
                        raise ValueError(f"Mockup {key} companion is missing or unsafe; refuse incomplete restore")
                    companions[key] = companion
        contents = _snapshot(companions.values())
        moved = [(dest, src)]
        dest.parent.mkdir(parents=True, exist_ok=True)
        common.move_path(src, dest)
        try:
            new_paths = {"file": dest}
            for key, companion in companions.items():
                target = dest.parent / companion.name
                if target.exists():
                    raise FileExistsError(f"Generated mockup companion already exists: {target.name}")
                common.move_path(companion, target)
                moved.append((target, companion))
                new_paths[key] = target
            record["status"], record["approval"], record["visual_review"] = "generated", "pending", "pending"
            record["restored_from"], record["restore_reference"] = "revoked", user_restore_reference
            for stale in ("approved_at_utc", "approval_reference", "artifact_hashes"):
                record.pop(stale, None)
            if kind == "assets":
                record["bundle_path"] = dest.relative_to(root).as_posix()
                record["technical_validation"] = technical
                record["visual_reviews"] = []
            else:
                for key, path in new_paths.items():
                    record[key] = path.relative_to(root).as_posix()
                _update_metadata_paths(new_paths.get("metadata"), record["file"], record.get("blueprint"))
            _write_manifest(root, kind, data)
        except Exception as failure:
            _roll_back(failure, moved, contents, file, backup.read_bytes())
    return {"id": item_id, "revision": revision, "status": "generated", "path": str(dest),
            "next_step": "validate and obtain a fresh explicit approval; restoring does not reactivate the revision"}


# ------------------------------------------------------------------------------------------------ mockups
def _validate_mockup_metadata(metadata):
    if not isinstance(metadata, dict):
        raise ValueError("Mockup metadata must be a JSON object")
    common.validate_schema(metadata, "gamearts-mockup-metadata")
    if metadata["status"] != "generated":
        raise ValueError("Mockup metadata status must be generated")
    if not common.MOCKUP_ID.fullmatch(metadata["mockup_id"]) or not common.REVISION.fullmatch(metadata["revision"]):
        raise ValueError("Mockup metadata mockup_id or revision is invalid")
    if not metadata["prompt"].strip():
        raise ValueError("Mockup metadata prompt is required")
    try:
        datetime.fromisoformat(str(metadata["created_at_utc"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Mockup metadata created_at_utc is invalid") from exc
    return metadata


def _check_image_tool(settings, metadata):
    """The owner's chosen image generator is the only one a generated mockup may come from (an import is the owner's own art)."""
    chosen = settings.get("image_generation")
    mode = metadata["tool_mode"]
    if not chosen or mode == "external_import":
        return
    tool = chosen["tool"]
    if tool == "user_supplied":
        raise ValueError("The project's image generator is user_supplied: the owner makes the pictures, so a generated mockup cannot be "
                         "registered. Import the owner's picture with import-mockup, or have the owner change the image generator setting first")
    allowed = [chosen] + ([chosen["fallback"]] if chosen.get("fallback") else [])  # the owner's main tool, then the one they chose for when it is unavailable
    mismatch = None
    for candidate in allowed:
        if mode != candidate["tool"]:
            mismatch = mismatch or (f"This mockup was made with {mode} but the project's image generator is {tool}: use the chosen tool, "
                                    "or have the owner change the image generator setting first")
        elif candidate["tool"] == "connected_tool" and str(metadata["tool_name"]).strip().casefold() != candidate["tool_name"].strip().casefold():
            mismatch = (f"This mockup was made with the connected tool {metadata['tool_name']} but the project's image generator is "
                        f"{candidate['tool_name']}: use the chosen tool, or have the owner change the image generator setting first")  # the more specific reason wins
        else:
            return
    raise ValueError(mismatch)


def _update_metadata_paths(metadata_path, file_rel, blueprint_rel=None):
    if metadata_path is None:
        return
    body = common.read_json(metadata_path)
    body["file"] = file_rel
    if blueprint_rel:
        body["blueprint"] = blueprint_rel
    else:
        body.pop("blueprint", None)
    common.atomic_write_json(metadata_path, body)


def _companion_path(root, out, record, key, status):
    rel = record.get(key)
    if not isinstance(rel, str) or not rel:
        return None
    path = (root / rel).resolve()
    if not common.inside(path, out / "mockups" / status) or not path.is_file():
        raise ValueError(f"Mockup {key} path is missing, unsafe, or outside the {status} folder")
    return path


def _mockup_companions(root, out, record, status):
    return {key: path for key in ("metadata", "blueprint") if (path := _companion_path(root, out, record, key, status)) is not None}


def _picture_problems(path):
    """Whether the mockup's picture can be read and shows anything: a corrupt file, a fully transparent picture and a single flat colour have nothing for the analyzer, the
    reference crop or the owner's approval to stand on."""
    from PIL import Image
    try:
        with Image.open(path) as opened:
            opened.load()
            extrema = opened.convert("RGBA").getextrema()
    except (OSError, ValueError) as exc:
        return [f"mockup picture cannot be read: {exc}"]
    if extrema[3] == (0, 0):
        return ["mockup picture is fully transparent: it shows nothing to analyze"]
    if all(low == high for low, high in extrema):
        return ["mockup picture is one flat colour: it shows nothing to analyze"]
    return []


def audit_mockup(game_root, item_id, revision, notes=None):
    """Blocking issues for one mockup. A settings change after approval is a review flag (in `notes`), never an issue."""
    notes = notes if notes is not None else []
    root, out, _, data, rows = _read(game_root, "mockups")
    record = _record(rows, "mockups", item_id, revision)
    issues = []
    try:
        path = _storage_path(root, out, record, "mockups")
    except (ValueError, OSError) as exc:
        return [str(exc)]
    status = record.get("status")
    expected = record.get("sha256")
    if not expected:
        issues.append("mockup manifest lacks registered SHA256")
    elif common.sha256_file(path) != expected:
        issues.append("mockup image hash mismatch")
    issues += _picture_problems(path)
    if record.get("mockup_id") != item_id or record.get("revision") != revision:
        issues.append("mockup record identity is inconsistent")
    if not isinstance(record.get("prompt"), str) or not record["prompt"].strip():
        issues.append("mockup manifest lacks a generation prompt")
    if record.get("tool_mode") not in TOOL_MODES:
        issues.append("mockup manifest lacks a valid tool mode")
    accepted = set()
    try:
        _, canonical, raw = _settings_snapshot(root)
        accepted = {canonical, raw}
    except (OSError, ValueError) as exc:
        text = f"current project settings are not usable: {exc}"
        (issues if status == "generated" else notes).append(text)
    if accepted and record.get("settings_sha256") not in accepted:
        text = "mockup was made under different material settings than the current owner-confirmed settings"
        (issues if status == "generated" else notes).append(text + ("" if status == "generated" else " (flagged for owner review)"))
    for key in ("metadata", "blueprint"):
        try:
            _companion_path(root, out, record, key, status)
        except (ValueError, OSError) as exc:
            issues.append(str(exc))
    metadata_path = None
    try:
        metadata_path = _companion_path(root, out, record, "metadata", status)
    except (ValueError, OSError):
        pass
    if metadata_path:
        try:
            metadata = _validate_mockup_metadata(common.read_json(metadata_path))
            if metadata["mockup_id"] != item_id or metadata["revision"] != revision:
                issues.append("mockup metadata identity disagrees with manifest")
            if metadata["sha256"].lower() != str(record.get("sha256", "")).lower():
                issues.append("mockup metadata image hash disagrees with manifest")
            if metadata["file"].replace("\\", "/") != str(record.get("file", "")).replace("\\", "/"):
                issues.append("mockup metadata file path disagrees with manifest")
        except (OSError, ValueError) as exc:
            issues.append("mockup metadata invalid: " + str(exc))
    if status == "approved":
        if record.get("approval") not in APPROVAL_VALUES:
            issues.append("approved mockup lacks explicit user approval")
        if record.get("visual_review") != "approved":
            issues.append("approved mockup lacks approved visual review")
        if not record.get("approval_reference"):
            issues.append("approved mockup lacks approval reference")
        if not record.get("approved_at_utc"):
            issues.append("approved mockup lacks approved_at_utc")
        hashes = record.get("artifact_hashes")
        if not isinstance(hashes, dict) or not hashes:
            issues.append("approved mockup lacks artifact hashes")
        else:
            for rel, digest in hashes.items():
                try:
                    target = common.safe_member(path.parent, rel, "artifact")
                    if not target.is_file() or common.sha256_file(target) != digest:
                        raise ValueError
                except ValueError:
                    issues.append(f"approved mockup artifact changed or missing: {rel}")
    elif status == "generated":
        if record.get("approval") != "pending":
            issues.append("generated mockup must remain approval=pending")
        if record.get("visual_review") != "pending":
            issues.append("generated mockup must remain visual_review=pending")
    return issues


def register_mockup(game_root, metadata_path, image_path=None):
    root, out, _ = _paths(game_root, "mockups")
    settings, canonical, raw = _settings_snapshot(root)
    metadata_source = Path(metadata_path).resolve()
    if not metadata_source.is_file():
        raise ValueError("Mockup metadata file does not exist")
    metadata = _validate_mockup_metadata(common.read_json(metadata_source))
    _check_image_tool(settings, metadata)
    if metadata.get("settings_sha256") and metadata["settings_sha256"].lower() not in (canonical, raw):
        raise ValueError("Mockup metadata settings_sha256 does not match the current .gamearts/project.json settings")
    from gamearts_storyboard import scene_gate
    scene_gate(root, metadata["scope"], metadata.get("storyboard_scene_id"))
    image_source = Path(image_path).resolve() if image_path else None
    if image_source is None:
        candidate = (root / metadata["file"]).resolve()
        if candidate.is_file():
            image_source = candidate
    if image_source is None or not image_source.is_file():
        raise ValueError("Mockup image file does not exist")
    if common.sha256_file(image_source).lower() != metadata["sha256"].lower():
        raise ValueError("Mockup metadata sha256 does not match the actual image")
    revision, mockup_id = metadata["revision"], metadata["mockup_id"]
    with manifest_lock(root):
        manifest_path, manifest = _ensure_manifest(root, "mockups")
        rows = manifest["mockups"]
        if any(_id(row, "mockups") == mockup_id and row.get("revision") == revision for row in rows):
            raise ValueError("Mockup id and revision already registered; create a new revision")
        generated = out / "mockups" / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        destination = generated / image_source.name
        if destination.exists() and common.sha256_file(destination).lower() != metadata["sha256"].lower():
            raise FileExistsError("A different generated image already uses that filename")
        created, problems = [], []
        backup = _backup(root, "mockups_pre_register", manifest_path) if manifest_path.exists() else None
        companion = destination.with_suffix(".metadata.json")
        previous_companion = companion.read_bytes() if companion.exists() else None
        previous_manifest = manifest_path.read_bytes()
        try:
            if image_source != destination and not destination.exists():
                shutil.copy2(image_source, destination)
                created.append(destination)
            normalized = json.loads(json.dumps(metadata))
            normalized["file"] = destination.relative_to(root).as_posix()
            normalized["status"] = "generated"
            normalized["settings_sha256"] = canonical
            blueprint_path, blueprint_source = None, metadata.get("blueprint")
            if isinstance(blueprint_source, str) and blueprint_source:
                source = (root / blueprint_source).resolve() if not Path(blueprint_source).is_absolute() else Path(blueprint_source).resolve()
                if source.is_file():
                    blueprint_path = destination.with_suffix(".blueprint.json")
                    if blueprint_path.exists():
                        raise FileExistsError(f"Mockup blueprint companion already exists: {blueprint_path.name}")
                    shutil.copy2(source, blueprint_path)
                    created.append(blueprint_path)
                    normalized["blueprint"] = blueprint_path.relative_to(root).as_posix()
            common.atomic_write_json(companion, normalized)
            if previous_companion is None:
                created.append(companion)
            record = {"mockup_id": mockup_id, "revision": revision, "scope": metadata["scope"], "status": "generated",
                      "file": destination.relative_to(root).as_posix(), "metadata": companion.relative_to(root).as_posix(),
                      "sha256": metadata["sha256"].lower(), "settings_sha256": canonical, "prompt": metadata["prompt"],
                      "prompt_origin": metadata.get("prompt_origin", "agent_brief"),
                      "imagegen_prompt_captured": bool(metadata.get("imagegen_prompt_captured", False)),
                      "tool_mode": metadata["tool_mode"], "created_at_utc": metadata["created_at_utc"], "approval": "pending",
                      "visual_review": "pending", "source_references": metadata.get("source_references", []),
                      "constraints": metadata.get("constraints", [])}
            for key in ("storyboard_scene_id", "provenance", "rights", "tool_name"):
                if metadata.get(key):
                    record[key] = metadata[key]
            if blueprint_path is not None:
                record["blueprint"] = blueprint_path.relative_to(root).as_posix()
            record["artifact_hashes"] = {p.relative_to(destination.parent).as_posix(): common.sha256_file(p)
                                         for p in [destination, companion] + ([blueprint_path] if blueprint_path else [])}
            common.validate_schema(record, "gamearts-mockups-manifest", ("properties", "mockups", "items"))
            rows.append(record)
            _write_manifest(root, "mockups", manifest)
            audit_problems = audit_mockup(root, mockup_id, revision)
            if audit_problems:
                raise ValueError("Post-registration mockup audit failed: " + "; ".join(audit_problems))
        except Exception as failure:
            for item in reversed(created):
                _try(problems, f"remove {item.name}", lambda i=item: i.unlink(missing_ok=True))
            if previous_companion is not None:
                _try(problems, "restore companion", lambda: common.atomic_write_bytes(companion, previous_companion))
            _try(problems, "restore manifest", lambda: common.atomic_write_bytes(manifest_path, previous_manifest))
            if problems:
                raise ValueError(f"{failure}; ROLLBACK INCOMPLETE, inspect by hand: {'; '.join(problems)}") from failure
            raise
    return {"mockup_id": mockup_id, "revision": revision, "status": "generated", "path": str(destination), "metadata": str(companion),
            "manifest": str(manifest_path), "manifest_backup": str(backup) if backup else None,
            "image_generator_setting": (settings.get("image_generation") or {}).get("tool", "not_set")}


@contextmanager
def _scratch_folder(root, prefix):
    """Staging space inside the game (`.gamearts/system/tmp`), so no operation writes outside the game folder."""
    base = Path(root) / ".gamearts" / "system" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=prefix, dir=base) as scratch:
        yield Path(scratch)


def _check_mockup_identity(mockup_id, revision, scope):
    if not common.MOCKUP_ID.fullmatch(mockup_id or "") or not common.REVISION.fullmatch(revision or ""):
        raise ValueError("mockup id must look like city-scene and the revision like v001")
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}")


def _managed_mockup_name(settings, root, scope, mockup_id, revision):
    game = re.sub(r"[^A-Za-z0-9]+", "-", str(settings.get("project_id", root.name))).strip("-") or "game"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", mockup_id).strip("-")
    return f"{game}_{scope}_{slug}_mockup_{revision}.png"


def _pixel_facts(png_path):
    """Informational facts about a PNG's pixels; they never certify anything."""
    from PIL import Image
    with Image.open(png_path) as image:
        rgba = image.convert("RGBA")
        return {"has_transparency": rgba.getchannel("A").getextrema() != (255, 255),
                "contains_exact_key_pixels": common.mask_count(common.nonkey_mask(rgba)) != rgba.width * rgba.height}


def import_mockup(game_root, source, mockup_id, revision, scope, rights="user_supplied", rights_notes="", scene_id=None, notes="",
                  approval_reference=None):
    """Bring a mockup made OUTSIDE Game Arts into the lifecycle as a managed copy; the original is never touched.

    A PNG is copied byte for byte; another raster format is decoded and saved as PNG without altering a pixel (the original's
    hash and format are recorded). The record states honestly that no generation prompt exists. It is registered as `generated`;
    only when `approval_reference` (the user's own statement that this exact image is already approved) is given is it also
    approved. Returns the registration result plus informational image checks; the checks never certify anything.
    """
    from PIL import Image
    root = common.game_root(game_root)
    _check_mockup_identity(mockup_id, revision, scope)
    common.require_rights(rights)
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Source must be a regular file: {source}")
    settings, _, _ = _settings_snapshot(root)  # imports need confirmed settings exactly as generated mockups do
    original_hash = common.sha256_file(source)
    with _scratch_folder(root, "import-") as scratch:
        image_path = scratch / _managed_mockup_name(settings, root, scope, mockup_id, revision)
        with Image.open(source) as opened:
            original_format, size, mode = opened.format, opened.size, opened.mode
            if original_format == "PNG":
                shutil.copyfile(source, image_path)
            else:
                opened.convert("RGBA" if "A" in opened.getbands() or "transparency" in opened.info else "RGB").save(image_path, format="PNG")
        checks = {"original_format": original_format, "converted_to_png": original_format != "PNG", "size": list(size), "mode": mode,
                  **_pixel_facts(image_path), "original_sha256": original_hash}
        metadata = {
            "schema_version": "1.0", "mockup_id": mockup_id, "revision": revision, "scope": scope, "status": "generated",
            "file": image_path.name, "sha256": common.sha256_file(image_path),
            "prompt": f"No generation prompt exists: this mockup was made outside Game Arts and supplied by the user (original file {source.name}).",
            "prompt_origin": "external_provider", "imagegen_prompt_captured": False, "tool_mode": "external_import", "created_at_utc": _now(),
            "source_references": [{"original_name": source.name, "original_sha256": original_hash, "original_format": original_format}],
            "provenance": {"provider": "supplied by the user", "edit_mode": "none" if original_format == "PNG" else "lossless re-encode to PNG"},
            "rights": {"status": rights, "notes": rights_notes}}
        if scene_id:
            metadata["storyboard_scene_id"] = scene_id
        if notes:
            metadata["notes"] = notes
        metadata_path = scratch / "import.metadata.json"
        common.atomic_write_json(metadata_path, metadata)
        result = register_mockup(root, metadata_path, image_path)
    result["import_checks"] = checks
    if approval_reference:
        try:
            result.update(approve_mockup(root, mockup_id, revision, approval_reference))
        except (ValueError, OSError) as exc:
            raise ValueError(f"Imported and registered as generated, but approval failed: {exc}") from exc
        result["metadata"] = str(Path(result["path"]).with_suffix(".metadata.json"))  # the files moved on approval
    return result


def register_generated_mockup(game_root, image, mockup_id, revision, scope, prompt, tool_mode=None, tool_name=None, scene_id=None,
                              notes="", model=None, use_fallback=False, fallback_reason=""):
    """Register a mockup an image tool has just produced: names the file, hashes it, writes the metadata record and registers it.

    The agent hands over the tool's own output and the prompt it actually sent; it never assembles the metadata or the manifest by
    hand. The tool defaults to the owner's `image_generation` choice and `register` refuses any other. The result is `generated`
    and awaits the owner's approval; the pixel facts returned never certify anything.
    """
    from PIL import Image
    root = common.game_root(game_root)
    _check_mockup_identity(mockup_id, revision, scope)
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("the prompt that was actually sent to the image tool is required")
    image = Path(image)
    if image.is_symlink() or not image.is_file():
        raise ValueError(f"image must be a regular file: {image}")
    settings, _, _ = _settings_snapshot(root)
    chosen = settings.get("image_generation")
    if use_fallback:
        if not chosen or not chosen.get("fallback"):
            raise ValueError("This game has no fallback image generator: the owner chose none, so the main tool is the only one. Say that it is unavailable and stop, "
                             "or have the owner add a fallback to the image generator setting")
        if not str(fallback_reason).strip():
            raise ValueError("Say why the main image generator was not used (--fallback-reason): the fallback is only for when it is unavailable in the session")
        if tool_mode is not None:
            raise ValueError("use_fallback names the owner's fallback tool itself: do not also name a tool")
        tool_mode, tool_name = chosen["fallback"]["tool"], chosen["fallback"].get("tool_name")
    elif tool_mode is None:
        if not chosen:
            raise ValueError("No image generator is saved for this game: ask the owner which one to use and save it in the project "
                             "settings, or name the tool with tool-mode")
        tool_mode, tool_name = chosen["tool"], tool_name or chosen.get("tool_name")
    _check_image_tool(settings, {"tool_mode": tool_mode, "tool_name": tool_name or ""})
    if tool_mode not in ("built_in_image_gen", "cli_image_gen", "connected_tool"):
        raise ValueError("tool-mode must be built_in_image_gen, cli_image_gen or connected_tool (an owner's own picture is imported with import-mockup)")
    with Image.open(image) as opened:
        if opened.format != "PNG":
            raise ValueError(f"A generated mockup must be a PNG, this is {opened.format}: have the tool save a PNG")
    original_hash = common.sha256_file(image)
    with _scratch_folder(root, "generated-") as scratch:
        staged = scratch / _managed_mockup_name(settings, root, scope, mockup_id, revision)
        shutil.copyfile(image, staged)
        metadata = {
            "schema_version": "1.0", "mockup_id": mockup_id, "revision": revision, "scope": scope, "status": "generated",
            "file": staged.name, "sha256": common.sha256_file(staged), "prompt": prompt,
            "prompt_origin": "agent_brief", "imagegen_prompt_captured": True, "tool_mode": tool_mode, "created_at_utc": _now(),
            "source_references": [{"original_name": image.name, "original_sha256": original_hash}],
            "provenance": {"provider": tool_name or tool_mode, "edit_mode": "generated", **({"model": model} if model else {}),
                           **({"generator_role": "fallback", "fallback_reason": str(fallback_reason).strip()} if use_fallback else {})}}
        if tool_name:
            metadata["tool_name"] = tool_name
        if scene_id:
            metadata["storyboard_scene_id"] = scene_id
        if notes:
            metadata["notes"] = notes
        metadata_path = scratch / "generated.metadata.json"
        common.atomic_write_json(metadata_path, metadata)
        result = register_mockup(root, metadata_path, staged)
        result["pixel_facts"] = _pixel_facts(staged)
    return result


def approve_mockup(game_root, item_id, revision, user_approval_reference):
    if not isinstance(user_approval_reference, str) or not user_approval_reference.strip():
        raise ValueError("Explicit user approval message reference is required")
    root = common.game_root(game_root)
    with manifest_lock(root):
        root, out, manifest_path, manifest, rows = _read(game_root, "mockups")
        record = _record(rows, "mockups", item_id, revision)
        if record.get("status") != "generated":
            raise ValueError("Only a generated non-rejected mockup can be approved")
        if record.get("approval") == "rejected" or record.get("visual_review") == "rejected":
            raise ValueError("Rejected mockup cannot be approved without a new candidate")
        problems = audit_mockup(root, item_id, revision)
        if problems:
            raise ValueError("Pre-approval mockup audit failed: " + "; ".join(problems))
        from gamearts_storyboard import scene_gate
        scene_gate(root, record.get("scope"), record.get("storyboard_scene_id"))
        src = _storage_path(root, out, record, "mockups")
        companions = _mockup_companions(root, out, record, "generated")
        destination = out / "mockups" / "approved" / src.name
        if destination.exists():
            raise FileExistsError("Target approved mockup revision already exists")
        backup = _backup(root, "mockups_pre_approval", manifest_path)
        contents = _snapshot(companions.values())
        moved = []
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            common.move_path(src, destination)
            moved.append((destination, src))
            new_paths = {"file": destination}
            for key, source in companions.items():
                target = destination.parent / source.name
                if target.exists():
                    raise FileExistsError(f"Approved companion already exists: {target.name}")
                common.move_path(source, target)
                moved.append((target, source))
                new_paths[key] = target
            record["status"], record["approval"], record["visual_review"] = "approved", "user_granted", "approved"
            record["approved_at_utc"], record["approval_reference"] = _now(), user_approval_reference
            for key, path in new_paths.items():
                record[key] = path.relative_to(root).as_posix()
            _update_metadata_paths(new_paths.get("metadata"), record["file"], record.get("blueprint"))
            record["artifact_hashes"] = {p.relative_to(destination.parent).as_posix(): common.sha256_file(p) for p in new_paths.values()}
            _write_manifest(root, "mockups", manifest)
            problems = audit_mockup(root, item_id, revision)
            if problems:
                raise ValueError("Post-approval mockup audit failed: " + "; ".join(problems))
        except Exception as failure:
            _roll_back(failure, moved, contents, manifest_path, backup.read_bytes())
    return {"mockup_id": item_id, "revision": revision, "scope": record.get("scope"), "status": "approved", "path": str(destination),
            "manifest_backup": str(backup), "engine_validation": "not_assessed"}


SCENE_SCOPES = ("world", "scene", "mixed")
SCRIPTS = Path(__file__).resolve().parent
SCENE_STAGES = {"extraction": "scene_extraction", "detection": "scene_detection", "clean_parent": "scene_removal", "evaluation": "scene_evaluation"}


def _scene_mockup(game_root, item_id, revision, need_blueprint=True):
    """The manifest row of an approved world, scene or mixed mockup, which every scene stage works on; the stage's own folder is
    `.gamearts/outputs/scenes/<id>_<rev>/<stage>` so that no stage ever writes into another's."""
    root, out, manifest_path, manifest, rows = _read(game_root, "mockups")
    record = _record(rows, "mockups", item_id, revision)
    if record.get("status") != "approved":
        raise ValueError("Only an approved mockup can be taken through the scene stages: the objects of an unapproved picture may still change")
    if record.get("scope") not in SCENE_SCOPES:
        raise ValueError(f"The scene stages are for {', '.join(SCENE_SCOPES)} mockups; this one is {record.get('scope')}")
    if need_blueprint and not record.get("blueprint"):
        raise ValueError("The mockup has no blueprint: analyze it (mockup-analyzer) and register the blueprint first")
    return root, out, manifest, record


def _scene_result(root, manifest, record, stage, folder, summary):
    record[SCENE_STAGES[stage]] = {"path": folder.relative_to(root).as_posix(), "recorded_at_utc": _now(), **summary}
    _write_manifest(root, "mockups", manifest)


def extract_scene(game_root, item_id, revision, masks_from=None):
    """Cut every object out of an approved scene mockup as its reviewed blueprint says and record the account on the mockup's row. The
    extractor itself refuses a blueprint with an inconsistent object sweep or one that does not belong to this picture."""
    import extract_scene_objects as extractor
    with manifest_lock(common.game_root(game_root)):
        root, out, manifest, record = _scene_mockup(game_root, item_id, revision)
        target = out / "scenes" / f"{item_id}_{revision}" / "extraction"
        with tempfile.TemporaryDirectory() as staging:
            staged, masks_from = _staged_blueprint(root, record, masks_from, Path(staging))
            found = extractor.extract(staged, common.safe_member(root, record["file"], "mockup picture"), target)
        _scene_result(root, manifest, record, "extraction", target,
                      {"masks_from": masks_from, "manifest_sha256": common.sha256_file(target / "extraction.json"), "objects": len(found["objects"]), "per_class": found["per_class"],
                       "absent_classes": found["absent_classes"], "possible_duplicates": len(found["possible_duplicates"])})
    return {"mockup_id": item_id, "revision": revision, "status": "extracted", "path": str(target), "objects": len(found["objects"]), "per_class": found["per_class"],
            "absent_classes": found["absent_classes"], "possible_duplicates": found["possible_duplicates"], "not_assessed": found["not_assessed"]}


def detect_scene(game_root, item_id, revision, command=None, detector_args=()):
    """Run the detection step on an approved scene mockup and record its DRAFT blueprint. The detector is an optional extra that lives in its
    own environment, so it runs as a separate process (`command` is the interpreter and script; `detector_args` are the step's own options).
    The draft is pending review: it is never the mockup's blueprint, and nothing downstream reads it except `evaluate-scene`."""
    import subprocess
    with manifest_lock(common.game_root(game_root)):
        root, out, manifest, record = _scene_mockup(game_root, item_id, revision, need_blueprint=False)
        target = out / "scenes" / f"{item_id}_{revision}" / "detection"
        command = list(command) if command else [sys.executable, str(SCRIPTS / "detect_scene_objects.py")]
        done = subprocess.run(command + ["detect", "--mockup", str(common.safe_member(root, record["file"], "mockup picture")), "--mockup-id", item_id, "--revision", revision,
                                         "--output-dir", str(target)] + list(detector_args), capture_output=True, text=True)
        if done.returncode != 0:
            raise ValueError("the detection step failed: " + (done.stderr.strip() or done.stdout.strip() or f"exit status {done.returncode}"))
        draft, findings = target / "detected.blueprint.json", target / "detections.json"
        if not draft.is_file() or not findings.is_file():
            raise ValueError("the detection step finished but wrote no draft blueprint and detections file")
        found = common.read_json(findings)
        _scene_result(root, manifest, record, "detection", target,
                      {"status": "draft_pending_review", "draft_blueprint_sha256": common.sha256_file(draft), "kept": found["kept"], "per_class": found["per_class"], "flagged": found["flagged"]})
    return {"mockup_id": item_id, "revision": revision, "status": "draft_pending_review", "path": str(target), "kept": found["kept"], "per_class": found["per_class"],
            "flagged": found["flagged"], "not_assessed": found["not_assessed"]}


def _staged_blueprint(root, record, masks_from, staging):
    """The reviewed blueprint copied into `staging` with the masks it names (`removal_mask_ref`), taken from `masks_from` (a folder in the game; default: the
    recorded detection's folder). The extraction and the removal both read masks beside the blueprint they are given; staging puts them there without
    writing to the approved mockup's folder. A mask the blueprint names that cannot be found is named; a blueprint that names none needs no folder."""
    data = common.read_json(common.safe_member(root, record["blueprint"], "mockup blueprint"))
    wanted = [(component.get("component_id"), component["removal_mask_ref"]) for element in data.get("elements", [])
              for component in element.get("separation_inventory", []) if component.get("removal_mask_ref")]
    if wanted:
        if not masks_from:
            if not record.get("scene_detection"):
                raise ValueError("The blueprint names masks: name the folder that holds them (--masks-from), or run detect-scene, whose masks are used by default")
            masks_from = record["scene_detection"]["path"]
        source = common.safe_member(root, masks_from, "masks folder")
        if not source.is_dir():
            raise ValueError(f"the masks folder {masks_from} does not exist")
        for component_id, reference in wanted:
            found = common.safe_member(source, reference, f"{component_id} mask")
            if not found.is_file():
                raise ValueError(f"{component_id}: the mask {reference} is not in {masks_from}")
            target = common.safe_member(staging, reference, f"{component_id} mask")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(found, target)
    staged = staging / "blueprint.json"
    common.atomic_write_json(staged, data)
    return staged, masks_from


def remove_scene(game_root, item_id, revision, inpainter=None, grow=2, max_share=0.03, masks_from=None):
    """Write the DRAFT clean parent of an approved scene mockup: its reviewed blueprint's objects with masks are removed and reconstructed. The
    result is inferred, never observed, and stays a draft for the cleanup gate; it never becomes the approved clean parent here. It follows the
    extraction (the objects are first accounted for, then removed). The masks come from `masks_from`, a folder inside the game (default: the
    recorded detection's `masks`), and are staged with a copy of the blueprint so the approved mockup's folder is not written to."""
    import remove_scene_objects as remover
    with manifest_lock(common.game_root(game_root)):
        root, out, manifest, record = _scene_mockup(game_root, item_id, revision)
        if not record.get("scene_extraction"):
            raise ValueError("The mockup has not been extracted: run extract-scene first, so the objects are accounted for before they are removed")
        target = out / "scenes" / f"{item_id}_{revision}" / "clean_parent"
        with tempfile.TemporaryDirectory() as staging:
            staged, masks_from = _staged_blueprint(root, record, masks_from, Path(staging))
            found = remover.remove(staged, common.safe_member(root, record["file"], "mockup picture"), target, inpainter or remover.TeleaInpainter(), grow, False, max_share)
        _scene_result(root, manifest, record, "clean_parent", target,
                      {"status": "draft_pending_review", "masks_from": masks_from, "report_sha256": common.sha256_file(target / "removal_report.json"), "removed": len(found["removed"]),
                       "not_removed": {reason: len(ids) for reason, ids in found["not_removed"].items()}, "reconstructed_share": found["reconstructed_share"]})
    return {"mockup_id": item_id, "revision": revision, "status": "draft_pending_review", "path": str(target), "removed": found["removed"], "not_removed": found["not_removed"],
            "reconstructed_share": found["reconstructed_share"], "overlapping_masks": found["overlapping_masks"], "pixel_status": found["pixel_status"], "not_assessed": found["not_assessed"]}


def evaluate_scene(game_root, item_id, revision, iou=0.5):
    """Score the recorded detection draft against the mockup's reviewed blueprint: how many of the reviewed objects the detector found and how many
    of its own were real. Measures the detector; it does not approve anything and does not say the reviewed account is complete."""
    import evaluate_extraction as evaluator
    with manifest_lock(common.game_root(game_root)):
        root, out, manifest, record = _scene_mockup(game_root, item_id, revision)
        detected = record.get("scene_detection")
        if not detected:
            raise ValueError("The mockup has no recorded detection: run detect-scene first")
        report = evaluator.compare(evaluator.objects_of(common.safe_member(root, record["blueprint"], "mockup blueprint"), "reference"),
                                   evaluator.objects_of(common.safe_member(root, detected["path"] + "/detected.blueprint.json", "detection draft"), "draft"), iou)
        target = out / "scenes" / f"{item_id}_{revision}" / "evaluation"
        if target.exists() and any(target.iterdir()):
            raise ValueError(f"{target.name} already holds an evaluation; an evaluation is never overwritten")
        target.mkdir(parents=True, exist_ok=True)
        common.atomic_write_json(target / "evaluation.json", report)
        _scene_result(root, manifest, record, "evaluation", target,
                      {"report_sha256": common.sha256_file(target / "evaluation.json"), "recall": report["recall"], "precision": report["precision"], "f1": report["f1"]})
    return {"mockup_id": item_id, "revision": revision, "status": "evaluated", "path": str(target), **{k: report[k] for k in ("reference_objects", "draft_objects", "matched", "recall", "precision", "f1")},
            "confused": report["confused"], "not_assessed": report["not_assessed"]}


# ------------------------------------------------------------------------------------------------ reconcile
def _manifest_shape_issues(kind, data):
    try:
        common.validate_schema(data, f"gamearts-{kind}-manifest")
        return []
    except ValueError as exc:
        return [f"manifest shape: {exc}"]


def reconcile_mockups(game_root):
    root, out, manifest_path = _paths(game_root, "mockups")
    issues = []
    data = common.read_json(manifest_path) if manifest_path.is_file() else _normalize_manifest(root, "mockups", {})  # nothing registered yet
    rows = data.get("mockups")
    if not isinstance(rows, list):
        return {"status": "blocked", "issues": ["Invalid mockups lifecycle manifest"], "counts": {}}
    by_file, seen = {}, set()
    for record in rows:
        if not isinstance(record, dict):
            issues.append("Invalid mockup manifest record")
            continue
        item_id, revision = _id(record, "mockups"), record.get("revision")
        if (item_id, revision) in seen:
            issues.append(f"Duplicate mockup manifest identity: {item_id} {revision}")
        seen.add((item_id, revision))
        try:
            path = _storage_path(root, out, record, "mockups")
        except (ValueError, OSError) as exc:
            issues.append(f"{item_id} {revision}: {exc}")
            continue
        by_file[path.resolve()] = record
        if record.get("sha256") and common.sha256_file(path) != record["sha256"]:
            issues.append(f"{item_id} {revision}: image hash mismatch")
        for key in ("metadata", "blueprint"):
            if record.get(key):
                try:
                    _companion_path(root, out, record, key, record.get("status"))
                except (ValueError, OSError) as exc:
                    issues.append(f"{item_id} {revision}: {exc}")
    for status in ("generated", "approved", "revoked"):
        folder = out / "mockups" / status
        if not folder.is_dir():
            continue
        for image in sorted(folder.glob("*.png")):
            if image.resolve() not in by_file:
                issues.append(f"Unregistered mockup image: {image.relative_to(root).as_posix()}")
            metadata = image.with_suffix(".metadata.json")
            if not metadata.is_file():
                issues.append(f"Missing mockup metadata: {metadata.relative_to(root).as_posix()}")
    for metadata in sorted((out / "mockups").glob("*/*.metadata.json")):
        image = metadata.with_name(metadata.name[:-len(".metadata.json")] + ".png")
        if not image.is_file():
            issues.append(f"Orphan mockup metadata: {metadata.relative_to(root).as_posix()}")
    try:
        _, canonical, raw = _settings_snapshot(root)
        for record in rows:
            if record.get("status") == "generated" and record.get("settings_sha256") not in (canonical, raw):
                issues.append(f"{_id(record, 'mockups')} {record.get('revision')}: generated under different settings")
    except (OSError, ValueError) as exc:
        issues.append(str(exc))
    issues += _manifest_shape_issues("mockups", data)
    counts = {"records": len(rows), "images": sum(1 for _ in (out / "mockups").glob("*/*.png")),
              "unregistered": sum(1 for i in issues if i.startswith("Unregistered")),
              "missing_metadata": sum(1 for i in issues if i.startswith("Missing mockup metadata"))}
    return {"status": "blocked" if issues else "consistent", "issues": issues, "counts": counts}


def reconcile_assets(game_root):
    root, out, manifest_path = _paths(game_root, "assets")
    issues = []
    data = common.read_json(manifest_path) if manifest_path.is_file() else _normalize_manifest(root, "assets", {})  # nothing registered yet
    rows = data.get("assets")
    if not isinstance(rows, list):
        return {"status": "blocked", "issues": ["Invalid assets lifecycle manifest"], "counts": {}}
    known, seen = set(), set()
    for record in rows:
        if not isinstance(record, dict):
            issues.append("Invalid asset manifest record")
            continue
        item_id, revision = _id(record, "assets"), record.get("revision")
        if (item_id, revision) in seen:
            issues.append(f"Duplicate asset manifest identity: {item_id} {revision}")
        seen.add((item_id, revision))
        try:
            folder = _storage_path(root, out, record, "assets")
        except (ValueError, OSError) as exc:
            issues.append(f"{item_id} {revision}: {exc}")
            continue
        known.add(folder.resolve())
        for name in record.get("files", []):
            try:
                _bundle_file(folder, name)
            except ValueError:
                issues.append(f"{item_id} {revision}: missing or unsafe bundle file {name}")
        if record.get("status") == "approved":
            problems = audit_asset(root, item_id)
            issues += [f"{item_id} {revision}: {p}" for p in problems]
        for entry in record.get("derived_exports", []):
            issues += [f"{item_id} {revision}: runtime export: {p}" for p in _derived_issues(root, out, record, entry, folder)]
    for status in ("generated", "approved", "revoked"):
        folder = out / "assets" / status
        if folder.is_dir():
            for bundle in sorted(p for p in folder.iterdir() if p.is_dir()):
                if bundle.resolve() not in known:
                    issues.append(f"Unregistered asset bundle: {bundle.relative_to(root).as_posix()}")
    issues += _manifest_shape_issues("assets", data)
    return {"status": "blocked" if issues else "consistent", "issues": issues, "counts": {"records": len(rows)}}


# ------------------------------------------------------------------------------------------------ report
MUTATING_OPERATIONS = ("register", "register-generated", "import-mockup", "approve-mockup", "extract-scene", "detect-scene", "remove-scene", "evaluate-scene", "register-asset", "import-asset", "approve", "approve-batch", "export-runtime", "revoke", "restore")


def next_step_for(name, result):
    """One plain sentence telling the agent what to do after an operation, built from the operation's own result, so the closing line
    of a stage (what exists, what the person must decide, what comes next) comes from facts and not from improvisation."""
    if name in ("register", "register-generated"):
        return "Show the mockup to the owner and ask plainly: approve it, or what should change?"
    if name == "import-mockup":
        if result.get("status") == "approved":
            return "The imported mockup is approved. Analyze it (mockup-analyzer), then plan the production art from it."
        return "Show the imported mockup to the owner and ask whether it is approved or what should change."
    if name == "detect-scene":
        return ("The detector's DRAFT blueprint is written, pending review: it misses objects and sees ones that are not there. Compare it with the picture "
                "(the analyzer's visual audit), correct it into the mockup's reviewed blueprint, then run evaluate-scene to measure the detector and extract-scene to cut out the objects.")
    if name == "remove-scene":
        return ("The draft clean parent is written; its reconstructed pixels are inferred, never observed. Show the owner what was and was not removed and give it to "
                "the cleanup gate for review before it counts as a clean plate.")
    if name == "evaluate-scene":
        return ("Tell the owner how much of the reviewed account the detector found (recall) and how much of its own was real (precision); the reviewed account may itself "
                "miss objects, so an extra may be real.")
    if name == "extract-scene":
        return ("The scene's objects are cut out into " + str(result.get("path", "the scenes folder")) + ". Show the owner the contact sheet and overview, say what the extraction "
                "did not assess (the objects it may have missed), and plan the production art from the approved mockup.")
    if name == "approve-mockup":
        if result.get("scope") in SCENE_SCOPES:
            return ("Analyze the approved mockup (mockup-analyzer) including the object sweep, register its blueprint, then run extract-scene "
                    "to cut out every object; plan the production art after that.")
        return "Analyze the approved mockup (mockup-analyzer), then plan the production art from it."
    if name == "register-asset":
        if result.get("technical_validation") == "passed":
            return ("The mechanical checks passed. Show the result (with the review boards for a composite asset) "
                    "and ask the owner to approve it or ask for changes.")
        return "The mechanical checks failed: fix the issues listed, rebuild the bundle and register a new revision."
    if name == "approve":
        made = (result.get("derived_exports") or {}).get("runtime", {})
        if made.get("status") == "written":
            return f"The asset is approved and its engine-ready copies are in {made.get('path', 'the runtime folder')}. Tell the owner and ask what to make next."
        if made.get("status") == "failed":
            return f"The asset is approved, but its engine-ready copies could not be made ({made.get('reason', 'no reason was given')}). Tell the owner, then ask what to make next."
        return "The asset is approved. Tell the owner and ask what to make next."
    if name == "import-asset":
        if not result.get("ok", True):
            return ("The art was registered but its mechanical checks failed: read the issues in the result, tell the owner what they mean and what would fix them. "
                    "Nothing is approved.")
        offered = " It was also offered as the game's style anchor: ask the owner whether to make it the game's look." if result.get("anchor_offer") else ""
        return ("The owner's art is registered as a generated asset, and its picture is an approved reference. Show it to the owner and ask them to approve "
                "the production asset, or say what to change." + offered)
    if name == "approve-batch":
        done, left = result.get("approved") or [], result.get("not_approved") or []
        if not left:
            return f"{len(done)} approved. Tell the owner and ask what to make next."
        return (f"{len(done)} approved, {len(left)} left as they were: " + "; ".join(f"{item['item']} ({item['reason']})" for item in left)
                + ". Tell the owner which, and what to do about each.")
    if name == "export-runtime":
        return (f"The engine-ready copies are in {result.get('path', 'the runtime folder')}. They are derived files: "
                "tell the owner they are for the game, not new art, and ask what to make next.")
    if name == "revoke":
        built = result.get("dependents") or []
        later = (f" {len(built)} asset(s) were built on it and will fail their next audit, so ask whether to rebuild them." if built else "")
        return "Tell the owner what was withdrawn and why." + later + " Ask whether to make a replacement."
    return "Tell the owner what changed."


def refresh_report(game_root):
    """Rebuild the art report after a change. The change has already succeeded, so a report that cannot be built never fails it: the
    failure is returned for the caller to show, and the result names the report so a person can open it."""
    try:
        import gamearts_report
        return {"updated": True, "path": gamearts_report.build(game_root)["path"]}
    except (ImportError, OSError, ValueError, TypeError, KeyError) as exc:
        return {"updated": False, "problem": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------------------------------------------ CLI
def _dimensions(text):
    """`16x16` -> (16, 16)."""
    first, _, second = text.lower().partition("x")
    if not first.isdigit() or not second.isdigit():
        raise argparse.ArgumentTypeError("use two whole numbers joined by x, for example 4x2")
    return int(first), int(second)


def _pair(text):
    mockup_id, _, revision = text.partition(":")
    if not mockup_id or not revision:
        raise argparse.ArgumentTypeError("use id:revision, for example city-scene:v001")
    return mockup_id, revision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    ops = parser.add_subparsers(dest="operation", required=True)

    def op(name, **kw):
        sub = ops.add_parser(name, **kw)
        sub.add_argument("--game-root", type=Path, required=True)
        return sub
    op("check-settings")
    sub = op("confirm-settings")
    sub.add_argument("--by", required=True, help="Who confirmed: the owner or an authorized role")
    sub.add_argument("--user-confirmation-ref", required=True, help="The owner's own words confirming the settings; never invent")
    sub.add_argument("--presented-version", required=True, help="The version printed by finish or check-settings, as shown to the owner")
    sub = op("select")
    sub.add_argument("--stage", choices=("approved", "generated"), required=True)
    sub.add_argument("--kind", choices=KINDS, required=True)
    sub.add_argument("--id")
    sub.add_argument("--revision", help="Specific revision when the ID is shared")
    sub = op("list")
    sub.add_argument("--kind", choices=KINDS, required=True)
    sub.add_argument("--status", choices=sorted(STATES))
    sub = op("audit")
    sub.add_argument("--id", required=True)
    sub = op("approve")
    sub.add_argument("--id", required=True)
    sub.add_argument("--user-approval-ref", required=True, help="Reference to the actual user approval message; never invent")
    sub.add_argument("--visual-review", nargs=2, action="append", metavar=("PACKET", "DECISION"),
                     help="Bundle-relative visual-review packet and decision paths (repeatable); required for composite assets")
    sub = op("import-asset")
    sub.add_argument("--source", type=Path, required=True, help="The owner's sprite sheet; it is read, never changed")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    layout = sub.add_mutually_exclusive_group(required=True)
    layout.add_argument("--grid", type=_dimensions, metavar="COLSxROWS", help="The sheet is this many columns and rows of equal frames")
    layout.add_argument("--cell", type=_dimensions, metavar="WxH", help="The sheet is made of frames of this size")
    layout.add_argument("--data", type=Path, help="The data file Aseprite wrote beside the sheet (array or hash form): frame rectangles, times and tags")
    sub.add_argument("--duration-ms", type=int, help="Time of every frame when the data file gives none (default 125)")
    sub.add_argument("--pivot", type=int, nargs=2, metavar=("X", "Y"), help="Pivot of every frame in pixels (default: bottom centre)")
    sub.add_argument("--alpha-threshold", type=int, help="Turn each partly transparent pixel into art (at least this opaque, 1 to 255) or empty")
    sub.add_argument("--rights", default="user_supplied", choices=common.RIGHTS)
    sub.add_argument("--rights-notes", default="")
    sub.add_argument("--user-approval-ref", required=True, help="The owner's own words that this art is theirs and approved as the reference; never invent")
    sub.add_argument("--anchor", action="store_true", help="Also import the picture as an approved style board and offer it as the style anchor")
    sub.add_argument("--extract-palette", metavar="NAME", help="Save the art's colours as a palette with this name")
    sub = op("approve-batch")
    sub.add_argument("--kind", choices=("mockups", "assets"), required=True)
    sub.add_argument("--item", type=_pair, action="append", required=True, metavar="ID:REVISION", help="An exact revision to approve (repeatable)")
    sub.add_argument("--shown", type=_pair, action="append", required=True, metavar="ID:REVISION",
                     help="An item the owner was actually shown (repeatable); an item not listed here is left unapproved")
    sub.add_argument("--user-approval-ref", required=True, help="The owner's own approving words; never invent")
    sub = op("export-runtime")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", help="Exact revision when the ID is shared")
    sub.add_argument("--replace", action="store_true", help="Replace runtime files that already exist (for example after the art changed)")
    sub = op("register")
    sub.add_argument("--metadata", required=True, help="Mockup metadata JSON; see schemas/gamearts-mockup-metadata.schema.json")
    sub.add_argument("--image", help="Actual PNG when the metadata file does not point to it")
    sub = op("register-generated")
    sub.add_argument("--image", type=Path, required=True, help="The PNG the image tool produced (it is copied; the original stays where the tool saved it)")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    sub.add_argument("--scope", required=True, choices=SCOPES)
    sub.add_argument("--prompt-file", type=Path, required=True, help="Text file holding the prompt that was actually sent to the image tool")
    sub.add_argument("--tool-mode", choices=("built_in_image_gen", "cli_image_gen", "connected_tool"),
                     help="Omit to use the image generator saved in the project settings")
    sub.add_argument("--tool-name", help="Name of the connected tool; omit to use the saved one")
    sub.add_argument("--model", help="Model the tool reported, when it reports one")
    sub.add_argument("--use-fallback", action="store_true", help="The picture came from the owner's fallback image generator (the main one is unavailable in this session)")
    sub.add_argument("--fallback-reason", default="", help="Why the main image generator was not used; required with --use-fallback and recorded with the picture")
    sub.add_argument("--storyboard-scene-id")
    sub.add_argument("--notes", default="")
    sub = op("import-mockup")
    sub.add_argument("--source", type=Path, required=True, help="The user's own mockup file; it is copied, never moved or changed")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    sub.add_argument("--scope", required=True, choices=SCOPES)
    sub.add_argument("--rights", default="user_supplied", choices=common.RIGHTS,
                     help="owned when the user says they made it or own it, licensed when they say they hold a licence, otherwise user_supplied")
    sub.add_argument("--rights-notes", default="")
    sub.add_argument("--storyboard-scene-id")
    sub.add_argument("--notes", default="")
    sub.add_argument("--user-approval-ref", help="The user's own statement that this exact image is already approved; omit to leave it generated")
    sub = op("approve-mockup")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    sub.add_argument("--user-approval-ref", required=True, help="Reference to the actual user approval message; never invent")
    sub = op("extract-scene")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    sub.add_argument("--masks-from", help="Folder inside the game that holds the masks the blueprint names (default: the recorded detection's folder)")
    sub = op("detect-scene")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    sub.add_argument("--python", help="The interpreter of the environment that has the detection extra (torch, transformers); default: this one")
    sub.add_argument("detector_args", nargs=argparse.REMAINDER, help="After --: options of detect_scene_objects.py (tiles, detector kind, excluded regions and so on)")
    sub = op("remove-scene")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    sub.add_argument("--masks-from", help="Folder inside the game that holds the masks the blueprint names (default: the recorded detection's folder)")
    sub.add_argument("--grow", type=int, default=2)
    sub.add_argument("--max-share", type=float, default=0.03)
    sub = op("evaluate-scene")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    sub.add_argument("--iou", type=float, default=0.5)
    sub = op("audit-mockup")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    sub = op("register-asset")
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    sub.add_argument("--bundle", required=True, help="Folder inside .gamearts/outputs/assets/generated, relative to the game root")
    sub.add_argument("--source-mockup", type=_pair, action="append", required=True, help="Approved mockup as id:revision (repeatable)")
    sub.add_argument("--extra", type=Path, help="JSON file holding optional provenance / rights objects")
    sub.add_argument("--source-asset", type=_pair, action="append", metavar="ID:REVISION",
                     help="An approved asset this one is made from, as a palette variant names its base (repeatable)")
    sub.add_argument("--limited-profile-ref", help="The owner's own words approving a bundle that faces only some of the game's directions")
    op("reconcile")
    op("reconcile-assets")
    sub = op("revoke")
    sub.add_argument("--kind", choices=KINDS, required=True)
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", help="Exact revision when the ID is shared")
    sub.add_argument("--reason", required=True)
    sub.add_argument("--replaced-by", help="ID of the revision that supersedes this one")
    sub = op("restore")
    sub.add_argument("--kind", choices=KINDS, required=True)
    sub.add_argument("--id", required=True)
    sub.add_argument("--revision", required=True)
    sub.add_argument("--user-restore-ref", required=True, help="Reference to the user's explicit restore request; never invent")
    args = parser.parse_args()
    try:
        name = args.operation
        if name == "check-settings":
            result = check_settings(args.game_root)
        elif name == "confirm-settings":
            result = confirm_settings(args.game_root, args.by, args.user_confirmation_ref, args.presented_version)
        elif name == "select":
            result = select(args.game_root, args.kind, args.stage, args.id, args.revision, report=True)
        elif name == "list":
            result = list_records(args.game_root, args.kind, args.status)
        elif name == "approve":
            reviews = [{"packet": packet, "decision": decision} for packet, decision in args.visual_review] if args.visual_review else None
            result = approve_asset(args.game_root, args.id, args.user_approval_ref, reviews)
            derived = auto_exports(args.game_root, args.id)
            if derived:
                result["derived_exports"] = derived
        elif name == "import-asset":
            import gamearts_import_asset as importer
            layout = {"grid": args.grid} if args.grid else {"cell": args.cell} if args.cell else {"data": args.data}
            result = importer.import_asset(args.game_root, args.source, args.id, args.revision, layout, args.rights, args.rights_notes, args.user_approval_ref,
                                           args.duration_ms, tuple(args.pivot) if args.pivot else None, args.alpha_threshold, args.anchor, args.extract_palette)
        elif name == "approve-batch":
            result = approve_batch(args.game_root, args.kind, args.item, args.shown, args.user_approval_ref)
        elif name == "export-runtime":
            result = export_runtime(args.game_root, args.id, args.revision, args.replace)
        elif name == "register":
            result = register_mockup(args.game_root, args.metadata, args.image)
        elif name == "register-generated":
            result = register_generated_mockup(args.game_root, args.image, args.id, args.revision, args.scope,
                                               args.prompt_file.read_text(encoding="utf-8"), args.tool_mode, args.tool_name,
                                               args.storyboard_scene_id, args.notes, args.model, args.use_fallback, args.fallback_reason)
        elif name == "import-mockup":
            result = import_mockup(args.game_root, args.source, args.id, args.revision, args.scope, args.rights, args.rights_notes,
                                   args.storyboard_scene_id, args.notes, args.user_approval_ref)
        elif name == "approve-mockup":
            result = approve_mockup(args.game_root, args.id, args.revision, args.user_approval_ref)
        elif name == "extract-scene":
            result = extract_scene(args.game_root, args.id, args.revision, args.masks_from)
        elif name == "detect-scene":
            extra = args.detector_args[1:] if args.detector_args[:1] == ["--"] else args.detector_args
            result = detect_scene(args.game_root, args.id, args.revision, [args.python, str(SCRIPTS / "detect_scene_objects.py")] if args.python else None, extra)
        elif name == "remove-scene":
            result = remove_scene(args.game_root, args.id, args.revision, None, args.grow, args.max_share, args.masks_from)
        elif name == "evaluate-scene":
            result = evaluate_scene(args.game_root, args.id, args.revision, args.iou)
        elif name == "audit-mockup":
            notes = []
            issues = audit_mockup(args.game_root, args.id, args.revision, notes)
            result = {"mockup_id": args.id, "revision": args.revision, "status": "blocked" if issues else "consistent",
                      "issues": issues, "review_flags": notes, "artistic_fidelity": "not_assessed", "engine_validation": "not_assessed"}
        elif name == "audit":
            notes = []
            issues = audit_asset(args.game_root, args.id, notes)
            result = {"asset_id": args.id, "status": "blocked" if issues else "consistent", "issues": issues, "notes": notes,
                      "artistic_fidelity": "not_assessed", "engine_validation": "not_assessed"}
        elif name == "register-asset":
            extra = common.read_json(args.extra) if args.extra else None
            result = register_asset(args.game_root, args.id, args.revision, args.bundle, args.source_mockup, extra, args.source_asset, args.limited_profile_ref)
        elif name == "reconcile":
            result = reconcile_mockups(args.game_root)
        elif name == "reconcile-assets":
            result = reconcile_assets(args.game_root)
        elif name == "restore":
            result = restore(args.game_root, args.kind, args.id, args.revision, args.user_restore_ref)
        else:
            result = revoke(args.game_root, args.kind, args.id, args.reason, args.revision, args.replaced_by)
        if name in MUTATING_OPERATIONS and isinstance(result, dict):
            result.setdefault("ok", True)
            result.setdefault("next_step", next_step_for(name, result))
            result["report"] = refresh_report(args.game_root)
        print(json.dumps(result, indent=2))
        if name == "approve-batch" and not result["ok"]:
            return 1  # a partial batch is reported in full above, and the exit status tells a caller that something was left
        return 1 if name in ("audit", "audit-mockup", "reconcile", "reconcile-assets") and result.get("issues") else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:  # ValueError covers JSON, contract and lock errors
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
