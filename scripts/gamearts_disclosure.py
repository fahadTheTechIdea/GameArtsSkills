#!/usr/bin/env python3
"""AI-content disclosure summary: what the game's recorded provenance says about how its approved art was made.

Run internally by the agent when the owner asks what to declare to a store or publisher:
  python scripts/gamearts_disclosure.py --game-root GAME

It only reads the manifests. It writes nothing, and it reports what was recorded, not what a store requires: whether a
disclosure applies, and its wording, is the store's rule and changes (check the store's current page before filling a survey).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402

MANIFESTS = Path(".gamearts") / "outputs" / "manifests"
NOT_COVERED = (
    "Art made or edited outside Game Arts, and anything not registered through it.",
    "Which tool made an approved asset unless its own provenance was recorded at registration (`register-asset --extra`); otherwise it only inherits its source mockup.",
    "What an imported (supplied) picture was made with: only the import is recorded, never how the owner made it.",
    "Content a game generates while it runs (live generation); this records pictures made during development only.",
    "Whether a store requires a disclosure for any of this, and what its form asks.",
)


def _rows(root, kind):
    path = common.game_root(root) / MANIFESTS / f"{kind}.json"
    if not path.is_file():
        return []
    return common.read_json(path).get(kind, [])


def _mockup_entry(row):
    tool = row.get("tool_name") or row["tool_mode"]
    entry = {"id": row["mockup_id"], "revision": row["revision"], "scope": row.get("scope"), "origin": "supplied" if row["tool_mode"] == "external_import" else "ai_generated"}
    if entry["origin"] == "ai_generated":
        entry["tool"] = tool
        provenance = row.get("provenance") or {}
        if provenance.get("model"):
            entry["model"] = provenance["model"]
        if provenance.get("generator_role") == "fallback":
            entry["generator_role"] = "fallback"
    return entry


def build(game_root):
    """The summary as a dict; approved art only, because that is what can ship."""
    mockups = {(r["mockup_id"], r["revision"]): _mockup_entry(r) for r in _rows(game_root, "mockups") if r.get("status") == "approved"}
    assets = []
    for row in _rows(game_root, "assets"):
        if row.get("status") != "approved":
            continue
        links = [mockups.get((link["mockup_id"], link["revision"])) for link in row.get("source_mockups", [])]
        known = [m for m in links if m]
        if not row.get("source_mockups"):
            origin = "no_source_recorded"
        elif any(m["origin"] == "ai_generated" for m in known):
            origin = "from_ai_generated_mockup"
        elif len(known) == len(links):
            origin = "from_supplied_mockup"
        else:
            origin = "source_not_approved"
        entry = {"id": row["asset_id"], "revision": row["revision"], "origin": origin}
        provenance = row.get("provenance") or {}
        recorded = {key: provenance[key] for key in ("provider", "model", "edit_mode") if provenance.get(key)}
        if recorded:
            entry["recorded_provenance"] = recorded
        assets.append(entry)
    generated = [m for m in mockups.values() if m["origin"] == "ai_generated"]
    return {
        "mockups": sorted(mockups.values(), key=lambda m: (m["id"], m["revision"])),
        "assets": sorted(assets, key=lambda a: (a["id"], a["revision"])),
        "tools": sorted({m["tool"] for m in generated}),
        "models": sorted({m["model"] for m in generated if "model" in m}),
        "ai_generated_mockups": len(generated),
        "supplied_mockups": len(mockups) - len(generated),
        "assets_from_ai_generated_mockups": sum(a["origin"] == "from_ai_generated_mockup" for a in assets),
        "assets_without_recorded_provenance": sum("recorded_provenance" not in a for a in assets),
        "not_covered": list(NOT_COVERED),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game-root", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.game_root), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
