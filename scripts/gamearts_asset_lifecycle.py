#!/usr/bin/env python3
"""Game Arts lifecycle guard for active selection and explicit rejection.

Used INTERNALLY by Claude/Codex. Never derive a production source from a
revoked/rejected/superseded record. All transitions preserve the complete
bundle, keep a manifest backup, and require an explicit rejection reason.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

# Tools are usually executed from this scripts folder, but standalone import
# in regression/agent contexts also needs sibling visual review utilities.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

KINDS = {"assets": "assets", "mockups": "mockups"}
STATES = {"approved", "generated", "revoked"}
STATE_FIELD = "status"


def _paths(game_root, kind):
    root = Path(game_root).resolve()
    if kind not in KINDS:
        raise ValueError("Invalid lifecycle type")
    return root, root / ".gamearts" / "outputs", root / ".gamearts" / "outputs" / "manifests" / (kind + ".json")


def _read(game_root, kind):
    root, out, file = _paths(game_root, kind)
    if not file.is_file():
        raise ValueError(f"Missing {kind} lifecycle manifest")
    data = json.loads(file.read_text(encoding="utf-8"))
    rows = data.get(kind) if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"Invalid {kind} lifecycle manifest")
    return root, out, file, data, rows


def _id(record, kind):
    return record.get("asset_id" if kind == "assets" else "mockup_id", record.get("id"))


def _record(rows, kind, item_id, revision=None):
    found = [r for r in rows if isinstance(r, dict) and _id(r, kind) == item_id
             and (revision is None or r.get("revision", r.get("mockup_revision")) == revision)]
    if len(found) != 1:
        raise ValueError(f"Expected one exact {kind} record for {item_id!r}, got {len(found)}")
    return found[0]


def _within(path, directory):
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _storage_path(root, out, record, kind):
    status = record.get(STATE_FIELD)
    if status not in STATES:
        raise ValueError(f"Unknown lifecycle state {status!r}; deny selection")
    if kind == "assets":
        rel = record.get("bundle_path")
    else:
        rel = record.get("file")
    if not isinstance(rel, str) or not rel:
        raise ValueError("Lifecycle record has no managed path")
    candidate = (root / rel).resolve()
    storage = out / kind / status
    if not _within(candidate, storage):
        raise ValueError("Lifecycle record state disagrees with its physical folder")
    if not candidate.exists() or candidate.is_symlink():
        raise ValueError("Lifecycle file/bundle is missing or a symlink")
    return candidate



def audit_asset(game_root, item_id):
    """Check a recorded asset's own lifecycle, source and metadata consistency.

    File/manifest metadata audit only, not artistic correctness or engine readiness.
    Returns issues; callers must block approval/reference use if nonempty.
    """
    root, out, _, data, rows = _read(game_root, "assets")
    record = _record(rows, "assets", item_id)
    issues = []
    try:
        folder = _storage_path(root, out, record, "assets")
    except (ValueError, OSError) as exc:
        return [str(exc)]
    status = record.get("status")
    if status == "approved" and (
        record.get("visual_review") != "approved" or
        record.get("approval") not in ("user_granted", "approved", "granted")
    ):
        issues.append("approved manifest missing explicit user visual/art approval")
    required = record.get("files", [])
    if not isinstance(required, list) or not required:
        issues.append("asset manifest lacks declared bundle files")
        required = []
    for filename in required:
        if not isinstance(filename, str) or not filename:
            issues.append("invalid declared bundle file")
            continue
        target = (folder / filename).resolve()
        if not _within(target, folder) or not target.is_file():
            issues.append(f"missing or unsafe bundle file: {filename}")
    # Manifest and approved-source provenance must match actual registered bytes.
    mockups = record.get("source_mockups", [])
    if status == "approved" and not mockups:
        issues.append("approved asset has no approved source mockup linkage")
    if mockups:
        try:
            _, _, _, _, references = _read(game_root, "mockups")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            issues.append(f"cannot validate approved sources: {exc}")
            references = []
        for ref in mockups:
            if not isinstance(ref, dict):
                issues.append("invalid source mockup reference")
                continue
            matches = [m for m in references if isinstance(m, dict)
                       and _id(m, "mockups") == ref.get("mockup_id")
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
                elif hashlib.sha256(image.read_bytes()).hexdigest() != recorded_hash:
                    issues.append("approved source mockup image bytes have changed")
            except (OSError, ValueError) as exc:
                issues.append(f"approved source unavailable: {exc}")
    for bp in folder.glob("*.blueprint.json"):
        try:
            body = json.loads(bp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"invalid blueprint {bp.name}: {exc}")
            continue
        if status == "approved":
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
            body = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"invalid validation report {report.name}: {exc}")
            continue
        if status == "approved":
            if body.get("status") in ("generated", "pending", "rejected"):
                issues.append(f"{report.name}: validation status contradicts approval")
            sprite_status = body.get("isolated_props_background_masking")
            if isinstance(sprite_status, str) and "pending_user_review" in sprite_status:
                issues.append(f"{report.name}: sprite review is still marked pending")
    # For NEW production using the visual-review protocol, a claim of approval
    # is invalid without the exact reviewed packet, explicit user decision and
    # unchanged source/art/mask/board hashes. Legacy approvals are not revoked
    # merely because the protocol was introduced later.
    if status == "approved" and record.get("visual_review_protocol") == "review_packet_v1":
        slots = record.get("visual_reviews")
        if not isinstance(slots, list) or not slots:
            issues.append("approved asset lacks mandatory user visual review packet")
        else:
            for index, slot in enumerate(slots):
                if not isinstance(slot, dict):
                    issues.append(f"visual review {index}: invalid record")
                    continue
                paths = []
                for key in ("packet", "decision"):
                    rel = slot.get(key)
                    if not isinstance(rel, str) or not rel.strip():
                        issues.append(f"visual review {index}: missing {key} path")
                        break
                    candidate = (folder / rel).resolve()
                    if not _within(candidate, folder) or not candidate.is_file():
                        issues.append(f"visual review {index}: missing or unsafe {key} file")
                        break
                    paths.append(candidate)
                if len(paths) != 2:
                    continue
                try:
                    # Import lazily so old installations continue to read legacy
                    # manifests but cannot claim a NEW review protocol pass.
                    from visual_review_cleanup import verify as verify_visual_cleanup
                    verified = verify_visual_cleanup(paths[0], paths[1])
                    if verified["asset_id"] != _id(record, "assets"):
                        issues.append(f"visual review {index}: approved different asset ID")
                    if record.get("revision") and verified["revision"] != record["revision"]:
                        issues.append(f"visual review {index}: approved different revision")
                    source_ids = {(m.get("mockup_id"), m.get("revision"))
                                  for m in record.get("source_mockups", [])
                                  if isinstance(m, dict)}
                    if (verified.get("approved_mockup_id"),
                        verified.get("approved_mockup_revision")) not in source_ids:
                        issues.append(f"visual review {index}: displayed mockup is not the asset's approved source")
                except (ImportError, OSError, ValueError, TypeError, KeyError,
                        json.JSONDecodeError) as err:
                    issues.append(f"visual review {index}: invalid approval evidence: {err}")
    elif status == "approved" and record.get("visual_review_protocol") not in (
        None, "legacy", "review_packet_v1"
    ):
        issues.append("approved asset declares unknown visual-review protocol")

    # No claim of engine testing here. Godot status can legitimately be not_tested.
    return issues


def select(game_root, kind, stage, item_id=None, revision=None):
    if stage not in ("approved", "generated"):
        raise ValueError("Only approved production references or generated candidates may be selected")
    root, out, file, data, rows = _read(game_root, kind)
    choices = [_record(rows, kind, item_id, revision)] if item_id else [r for r in rows if isinstance(r, dict)]
    eligible = []
    for record in choices:
        status = record.get(STATE_FIELD)
        if status == "revoked" or record.get("approval") == "rejected" or record.get("visual_review") == "rejected":
            if item_id:
                raise ValueError("REJECTED/REVOKED asset cannot be used: " + str(_id(record, kind)))
            continue
        if status != stage:
            if item_id:
                raise ValueError(f"Item {_id(record,kind)} is {status}, not {stage}; do not bypass lifecycle")
            continue
        path = _storage_path(root, out, record, kind)
        if stage == "approved" and kind == "assets":
            problems = audit_asset(game_root, _id(record, "assets"))
            if problems:
                raise ValueError("Approved asset metadata audit failed: " + "; ".join(problems))
        if stage == "approved" and kind == "mockups":
            expected = record.get("sha256")
            if not expected:
                raise ValueError("Approved mockup source is missing registered SHA256")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("Approved mockup hash mismatch; source cannot be used")
        eligible.append({"id": _id(record, kind), "status": status, "path": str(path)})
    return eligible


def revoke(game_root, kind, item_id, reason, revision=None):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Explicit nonempty rejection/revocation reason required")
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
        if not isinstance(required, list) or not required or not all(
            isinstance(v, str) and (src / v).is_file() and Path(v).name == v
            for v in required
        ):
            raise ValueError("Bundle missing required artifact(s); refuse incomplete revocation")
    backup_root = root / ".gamearts" / "system" / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_name = "".join(char if char.isalnum() or char in "_-" else "_" for char in str(item_id))
    backup = backup_root / f"{kind}_before_{safe_name}_{timestamp}.json"
    backup.write_bytes(file.read_bytes())
    previous_record = json.loads(json.dumps(record))
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    try:
        record["status"] = "revoked"
        record["revocation_reason"] = reason.strip()
        record["revoked_at_utc"] = datetime.now(timezone.utc).isoformat()
        if kind == "assets":
            record["bundle_path"] = str(dest.relative_to(root)).replace(os.sep, "/")
            record["approval"] = "not_granted"
            record["visual_review"] = "rejected"
        else:
            record["file"] = str(dest.relative_to(root)).replace(os.sep, "/")
        pending = file.with_name(file.name + ".pending")
        try:
            pending.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(pending, file)
        finally:
            pending.unlink(missing_ok=True)
    except Exception:
        record.clear()
        record.update(previous_record)
        shutil.move(str(dest), str(src))
        raise
    if src.exists() or not dest.exists():
        raise OSError("Unable to verify revocation transition")
    return {"id": item_id, "from": prior_state, "status": "revoked",
            "path": str(dest), "manifest_backup": str(backup)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    choose = commands.add_parser("select")
    choose.add_argument("--stage", choices=("approved", "generated"), required=True)
    choose.add_argument("--id")
    choose.add_argument("--revision", help="Specific mockup revision when ID is shared")
    check = commands.add_parser("audit")
    check.add_argument("--id", required=True)
    check.add_argument("--game-root", type=Path, required=True)
    deny = commands.add_parser("revoke")
    deny.add_argument("--id", required=True)
    deny.add_argument("--revision", help="Exact mockup revision when ID is shared")
    deny.add_argument("--reason", required=True)
    for item in (choose, deny):
        item.add_argument("--game-root", type=Path, required=True)
        item.add_argument("--kind", choices=("mockups", "assets"), required=True)
    args = parser.parse_args()
    try:
        if args.operation == "select":
            result = select(args.game_root, args.kind, args.stage, args.id, args.revision)
        elif args.operation == "audit":
            issues = audit_asset(args.game_root, args.id)
            result = {"asset_id": args.id, "status": "blocked" if issues else "consistent",
                      "issues": issues, "artistic_fidelity": "not_assessed",
                      "godot_runtime": "not_assessed"}
        else:
            result = revoke(args.game_root, args.kind, args.id, args.reason, args.revision)
        print(json.dumps(result, indent=2))
        return 1 if args.operation == "audit" and result["issues"] else 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
