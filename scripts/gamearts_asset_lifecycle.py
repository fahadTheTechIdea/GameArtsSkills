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


def _record(rows, kind, item_id):
    found = [r for r in rows if isinstance(r, dict) and _id(r, kind) == item_id]
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


def select(game_root, kind, stage, item_id=None):
    if stage not in ("approved", "generated"):
        raise ValueError("Only approved production references or generated candidates may be selected")
    root, out, file, data, rows = _read(game_root, kind)
    choices = [_record(rows, kind, item_id)] if item_id else [r for r in rows if isinstance(r, dict)]
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
        if stage == "approved" and kind == "mockups":
            expected = record.get("sha256")
            if not expected:
                raise ValueError("Approved mockup source is missing registered SHA256")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("Approved mockup hash mismatch; source cannot be used")
        eligible.append({"id": _id(record, kind), "status": status, "path": str(path)})
    return eligible


def revoke(game_root, kind, item_id, reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Explicit nonempty rejection/revocation reason required")
    root, out, file, data, rows = _read(game_root, kind)
    record = _record(rows, kind, item_id)
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
    backup = backup_root / f"{kind}_before_{item_id}_{timestamp}.json"
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
    deny = commands.add_parser("revoke")
    deny.add_argument("--id", required=True)
    deny.add_argument("--reason", required=True)
    for item in (choose, deny):
        item.add_argument("--game-root", type=Path, required=True)
        item.add_argument("--kind", choices=("mockups", "assets"), required=True)
    args = parser.parse_args()
    try:
        if args.operation == "select":
            result = select(args.game_root, args.kind, args.stage, args.id)
        else:
            result = revoke(args.game_root, args.kind, args.id, args.reason)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
