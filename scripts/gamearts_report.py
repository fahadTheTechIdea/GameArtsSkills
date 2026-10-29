#!/usr/bin/env python3
"""Game Arts report: one offline page showing a game's art, its status, the user's approval words and what happens next.

  python scripts/gamearts_report.py --game-root GAME

Writes .gamearts/system/report/index.html (and small previews beside it). The folder is derived, regenerable and kept out of version
control with the other system files. The page is built only from the game's records (settings, storyboard, the two manifests and
their reconcile checks), so it can never show a status the records do not hold. It loads nothing from the network and needs no
script to read. The lifecycle rebuilds it after every change; a report that cannot be built is reported, never allowed to fail the
change that already happened.
"""
import argparse
import html
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import gamearts_presets as presets  # noqa: E402
import render_preview as animations  # noqa: E402

REPORT = Path(".gamearts") / "system" / "report"
PREVIEW_WIDTH = 640
PREVIEWS_PER_ASSET = 3
ANIMATIONS_PER_ASSET = 4
MAX_NEXT_STEPS = 8
QUOTE_LIMIT = 300

STATUS_LABEL = {"generated": "Waiting for your decision", "approved": "Approved", "revoked": "Withdrawn"}
STYLE_LABEL = {"pixel_art": "pixel art", "hand_painted": "hand-painted", "illustrated": "illustrated", "vector": "vector",
               "rendered_2d": "pre-rendered 3D", "custom": "custom"}
WORLD_LABEL = {"grid_world": "A tile map", "free_world": "Open space without tiles", "layered_scene": "Scrolling layers",
               "screen_space": "No ground world (screens and menus)"}
CAMERA_LABEL = {"orthogonal_3_4_oblique": "from above and a little in front", "top_down": "straight down", "side": "from the side",
                "isometric_3_4": "isometric", "custom": "custom view"}
GRID_LABEL = {"orthogonal_square": "square tiles", "isometric": "diamond tiles", "hex_pointy": "hexagon tiles, point up",
              "hex_flat": "hexagon tiles, point sideways", "custom": "custom tiles"}
DIRECTION_LABEL = {"dirs_8": "eight directions", "dirs_4": "four directions", "dirs_2_side": "left and right",
                   "dirs_1_side": "one side only", "dirs_1_front": "one front view"}
GENERATOR_LABEL = {"built_in_image_gen": "the agent's built-in image tool", "cli_image_gen": "the command-line image tool",
                   "connected_tool": "a connected tool", "user_supplied": "you make the pictures yourself"}

CSS = """
:root{--bg:#f6f4ef;--panel:#ffffff;--text:#1d1b16;--muted:#5b574d;--line:#d8d3c6;--accent:#1f5f8b;--ok:#17613a;--wait:#8a4b00;--gone:#6b2d2d;--bad:#a11d1d}
@media (prefers-color-scheme:dark){:root{--bg:#16150f;--panel:#201e17;--text:#efece2;--muted:#b3ad9c;--line:#3a372c;--accent:#7bb8e6;--ok:#6fd49b;--wait:#f0b25e;--gone:#e08a8a;--bad:#ff8f8f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header,main,footer{max-width:1100px;margin:0 auto;padding:0 16px}header{padding-top:24px}h1{font-size:1.7rem;margin:.2em 0}
h2{font-size:1.25rem;margin:1.6em 0 .5em;border-bottom:1px solid var(--line);padding-bottom:.25em}h3{font-size:1.05rem;margin:.2em 0}
.meta,.muted{color:var(--muted)}a{color:var(--accent)}ol,ul{padding-left:1.3em}dl{display:grid;grid-template-columns:max-content 1fr;gap:.25em 1em}dt{color:var(--muted)}dd{margin:0}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;padding:0;list-style:none}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px}.card img{width:100%;height:auto;background:#808080;border-radius:4px}
.card img.pixel{image-rendering:pixelated}.card figure{margin:8px 0}.card figcaption{font-size:.9rem}.badge{display:inline-block;font-weight:600;border:1px solid currentColor;border-radius:999px;padding:0 .6em;font-size:.85rem}
.approved .badge{color:var(--ok)}.generated .badge{color:var(--wait)}.revoked .badge{color:var(--gone)}.problem{color:var(--bad)}
blockquote{margin:.4em 0;padding:.2em .8em;border-left:3px solid var(--line);color:var(--muted)}summary{cursor:pointer}footer{padding:16px;color:var(--muted);font-size:.9rem}
a:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
"""


def esc(value):
    return html.escape(str(value), quote=True)


def _rel(folder, target):
    """URL path from `folder` to `target`, with forward slashes and escaped characters."""
    return quote(os.path.relpath(target, folder).replace(os.sep, "/"), safe="/.-_~")


def _short(text, limit=QUOTE_LIMIT):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


# ------------------------------------------------------------------------------------------------ plain words
def describe_settings(settings):
    """The saved settings as (label, plain words) pairs."""
    style = settings["art_style"]
    chosen = presets.resolve_style_preset(settings)
    look = chosen["title"] if chosen and chosen.get("found") else STYLE_LABEL.get(style["id"], style["id"])
    kind = common.world_kind(settings)
    rows = [("Look", look), ("Kind of world", WORLD_LABEL[kind])]
    world = settings.get("world")
    if world and kind != "screen_space":
        parts = [GRID_LABEL.get(world.get("grid"), world.get("grid")), CAMERA_LABEL.get(world.get("camera_profile"), world.get("camera_profile"))]
        rows.append(("Tiles and viewpoint", ", ".join(str(p) for p in parts if p)))
    if settings.get("screen"):
        width, height = settings["screen"]["base_resolution_px"]
        rows.append(("Screen", f"{width} × {height} px"))
    directions = settings.get("directions")
    if directions is not None:
        rows.append(("Characters face", DIRECTION_LABEL.get(directions) if isinstance(directions, str) else f"{len(directions)} listed directions"))
    generator = settings.get("image_generation")
    if generator:
        label = GENERATOR_LABEL[generator["tool"]]
        rows.append(("Pictures made by", f"{label} ({generator['tool_name']})" if generator.get("tool_name") else label))
        if generator.get("notes"):
            rows.append(("Note with every picture", generator["notes"]))
        spares = common.image_fallbacks(generator)
        for number, spare in enumerate(spares, 1):
            ordinal = "" if len(spares) == 1 else f" ({number})"
            rows.append((f"If that is unavailable{ordinal}" if number == 1 else f"If that is unavailable too{ordinal}",
                         f"{GENERATOR_LABEL[spare['tool']]} ({spare['tool_name']})" if spare.get("tool_name") else GENERATOR_LABEL[spare["tool"]]))
            if spare.get("notes"):
                rows.append((f"Note with the fallback{ordinal}", spare["notes"]))
    engine = presets.resolve_engine_target(settings)
    rows.append(("Engine or tool", engine.get("title") or engine["profile"] + " (no profile installed)"))
    if engine.get("version_note"):
        rows.append(("Engine version", engine["version_note"]))
    rows.append(("Settings", {"owner_confirmed": "confirmed by the owner", "needs_review": "need the owner to look again",
                              "inferred": "saved, waiting for the owner to confirm"}.get(settings.get("settings_status"), "not confirmed")))
    return rows


def next_steps(settings_state, mockups, assets, storyboard):
    """What the person should do or ask for next, in plain words, from the records alone."""
    steps = []
    if settings_state == "missing":
        steps.append("Set up the game's art settings (one short chat: kind of game, look, viewpoint, facing directions, engine).")
    elif settings_state != "owner_confirmed":
        steps.append("Confirm the game's art settings; mockups cannot be registered or approved before that.")
    if storyboard:
        if storyboard["sequence"] != "approved":
            steps.append("Choose which storyboard scenes to approve, in playing order.")
        elif storyboard["waiting"]:
            first = storyboard["waiting"][0]
            more = f" ({len(storyboard['waiting']) - 1} more after it)" if len(storyboard["waiting"]) > 1 else ""
            steps.append(f"Make the mockup for the scene “{first['title']}”{more}.")
    for record in mockups:
        if record.get("status") == "generated":
            steps.append(f"Approve or ask for changes to the mockup {record.get('mockup_id')} {record.get('revision')}.")
    built_from = {(m.get("mockup_id"), m.get("revision")) for a in assets if a.get("status") != "revoked" for m in a.get("source_mockups", []) if isinstance(m, dict)}
    for record in mockups:
        if record.get("status") == "approved" and (record.get("mockup_id"), record.get("revision")) not in built_from:
            steps.append(f"Plan the art from the approved mockup {record.get('mockup_id')} {record.get('revision')}.")
    for record in mockups:
        if record.get("status") == "approved" and record.get("scope") in ("world", "scene", "mixed") and not record.get("scene_extraction"):
            what = "Run the scene extraction (extract-scene) for" if record.get("blueprint") else "Analyze (object sweep and blueprint), then extract the objects of"
            steps.append(f"{what} the approved scene mockup {record.get('mockup_id')} {record.get('revision')}.")
    for record in assets:
        if record.get("status") == "generated":
            failed = (record.get("technical_validation") or {}).get("status") == "failed"
            steps.append(f"{'Fix and rebuild' if failed else 'Review and approve'} the asset {record.get('asset_id')} {record.get('revision')}.")
    if not steps:
        steps.append("Everything registered is approved. Ask for the next piece of art.")
    return steps[:MAX_NEXT_STEPS]


# ------------------------------------------------------------------------------------------------ previews
def write_preview(source, target, pixel_art):
    """A review aid: the delivered sheet with the key colour shown as a checkerboard, reduced to a readable width. Never game art."""
    from PIL import Image
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    shown = animations.show_key_as_checkerboard(image)
    if shown.width > PREVIEW_WIDTH:
        height = max(1, round(shown.height * PREVIEW_WIDTH / shown.width))
        shown = shown.resize((PREVIEW_WIDTH, height), Image.NEAREST if pixel_art else Image.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    shown.save(target)


# ------------------------------------------------------------------------------------------------ cards
def animation_blocks(record, bundle, folder, previews_dir, pixel_art, problems, written):
    """Static strips with a link to the animated GIF for the animations on a bundle's sheets. Previews are review aids; the strip is shown
    still (an animation that starts by itself cannot be paused) and the GIF opens on request."""
    blocks, more = [], 0
    for index, atlas in enumerate(sorted(bundle.glob("*.atlas.json"))):
        try:
            sheet = bundle / common.read_json(atlas)["image"]
            made = animations.render(sheet, atlas, previews_dir, pixel_art, stem=f"{record.get('asset_id')}_{record.get('revision')}_{index}", min_frames=2)
        except (OSError, ValueError, KeyError) as exc:  # one sheet's animation preview failing is named on the page; the report still builds
            problems.append(f"animation preview of {record.get('asset_id')} {record.get('revision')}/{atlas.name}: {exc}")
            continue
        for item in made:
            written.update((item["strip"], item["gif"]))
            if len(blocks) >= ANIMATIONS_PER_ASSET:
                more += 1
                continue
            label = f"{item['action'] or 'frames'}" + (f" facing {item['direction']}" if item["direction"] else "")
            timing = (f' <span class="muted">The GIF format rounds {len(item["gif_timing_changed"])} frame time(s); the sheet keeps its own times.</span>'
                      if item["gif_timing_changed"] else "")
            blocks.append(f'<figure><a href="{_rel(folder, previews_dir / item["strip"])}"><img class="{"pixel" if pixel_art else ""}" '
                          f'src="{_rel(folder, previews_dir / item["strip"])}" alt="Animation {esc(label)}: {item["frames"]} frames side by side, '
                          f'{item["duration_ms"]} ms in total" loading="lazy"></a>'
                          f'<figcaption>{esc(label)}: {item["frames"]} frames, {item["duration_ms"]} ms. '
                          f'<a href="{_rel(folder, previews_dir / item["gif"])}">Play it as an animated GIF</a>.{timing}</figcaption></figure>')
    if more:
        blocks.append(f'<p class="muted">{more} more animation(s) on these sheets are not shown here.</p>')
    return "".join(blocks)


def _quote_block(record):
    reference = record.get("approval_reference")
    if not reference:
        return ""
    when = f" on {esc(str(record.get('approved_at_utc', ''))[:10])}" if record.get("approved_at_utc") else ""
    return f'<p class="muted">Approved{when}, in your words:</p><blockquote>{esc(_short(reference))}</blockquote>'


def _rights(record):
    rights = record.get("rights") or {}
    return f'<p class="muted">Rights: {esc(rights["status"])}</p>' if rights.get("status") else ""


def mockup_card(record, root, folder, pixel_art):
    status = record.get("status", "generated")
    title = f"{record.get('mockup_id')} {record.get('revision')}"
    image = ""
    if record.get("file") and (root / record["file"]).is_file():
        image = (f'<a href="{_rel(folder, root / record["file"])}"><img class="{"pixel" if pixel_art else ""}" '
                 f'src="{_rel(folder, root / record["file"])}" alt="Mockup {esc(title)}, {esc(STATUS_LABEL.get(status, status).lower())}" loading="lazy"></a>')
    scene = f'<p class="muted">Storyboard scene: {esc(record["storyboard_scene_id"])}</p>' if record.get("storyboard_scene_id") else ""
    reason = f'<p class="problem">Withdrawn because: {esc(_short(record["revocation_reason"]))}</p>' if status == "revoked" and record.get("revocation_reason") else ""
    return (f'<li class="card {esc(status)}" data-record="mockup:{esc(record.get("mockup_id"))}:{esc(record.get("revision"))}" data-status="{esc(status)}">'
            f'<h3>{esc(title)}</h3><p><span class="badge">{esc(STATUS_LABEL.get(status, status))}</span> <span class="muted">{esc(record.get("scope", ""))}</span></p>'
            f'{image}{scene}{_quote_block(record)}{_rights(record)}{reason}</li>')


def asset_card(record, root, folder, previews_dir, pixel_art, problems, written):
    status = record.get("status", "generated")
    title = f"{record.get('asset_id')} {record.get('revision')}"
    bundle = root / record.get("bundle_path", "")
    pictures = []
    sheets = [name for name in record.get("files", []) if str(name).lower().endswith(".png")][:PREVIEWS_PER_ASSET]
    for index, name in enumerate(sheets):
        source = bundle / name
        if not source.is_file():
            continue
        target = previews_dir / f"{record.get('asset_id')}_{record.get('revision')}_{index}.png".replace("/", "_")
        try:
            write_preview(source, target, pixel_art)
        except (OSError, ValueError) as exc:  # a sheet that cannot be previewed is named on the page; the report still builds
            problems.append(f"preview of {title}/{name}: {exc}")
            continue
        written.add(target.name)
        pictures.append(f'<a href="{_rel(folder, source)}"><img class="{"pixel" if pixel_art else ""}" src="{_rel(folder, target)}" '
                        f'alt="Sheet {esc(name)} of {esc(title)}, key colour shown as a checkerboard" loading="lazy"></a>')
    pictures.append(animation_blocks(record, bundle, folder, previews_dir, pixel_art, problems, written))
    technical = record.get("technical_validation") or {}
    if technical.get("status") == "passed":
        checks = '<p>Mechanical checks passed. <span class="muted">They check files and pixels only; they do not judge the art.</span></p>'
    elif technical.get("status") == "failed":
        checks = f'<p class="problem">Mechanical checks failed: {esc(_short("; ".join(technical.get("issues", []))))}</p>'
    else:
        checks = '<p class="muted">No mechanical checks are recorded.</p>'
    engine = f'<p class="muted">Engine: {esc(str(record.get("engine_validation", "not_tested")).replace("_", " "))}</p>'
    exports = record.get("derived_exports") or []
    copies = (f'<p class="muted">Engine-ready copies made from this approved art ({esc(", ".join(e.get("kind", "") for e in exports))}): '
              'derived files, not new art, kept outside the approved folder.</p>') if exports else ""
    sources = ", ".join(f'{m.get("mockup_id")} {m.get("revision")}' for m in record.get("source_mockups", []) if isinstance(m, dict))
    source_line = f'<p class="muted">Built from: {esc(sources)}</p>' if sources else ""
    bases = ", ".join(f'{a.get("asset_id")} {a.get("revision")}' for a in record.get("source_assets", []) if isinstance(a, dict))
    source_line += f'<p class="muted">Made from the asset: {esc(bases)}</p>' if bases else ""
    made_with = record.get("provenance") or {}
    tool = " ".join(str(made_with[key]) for key in ("provider", "model") if made_with.get(key))
    source_line += (f'<p class="muted">Made with: {esc(tool)}</p>' if tool
                    else '<p class="muted">The tool that made this is not recorded.</p>') if status != "revoked" else ""
    fit = technical.get("settings_fit") or {}
    mismatches = [item["detail"] for item in fit.get("checks", []) if item.get("status") == "mismatch"]
    source_line += f'<p class="problem">Does not match the saved settings of this game: {esc(_short("; ".join(mismatches)))}</p>' if mismatches else ""
    limited = record.get("limited_profile") or {}
    source_line += f'<p class="muted">Faces only some of the directions of this game; the owner approved that: {esc(_short(limited["approval_ref"]))}</p>' if limited else ""
    reason = f'<p class="problem">Withdrawn because: {esc(_short(record["revocation_reason"]))}</p>' if status == "revoked" and record.get("revocation_reason") else ""
    return (f'<li class="card {esc(status)}" data-record="asset:{esc(record.get("asset_id"))}:{esc(record.get("revision"))}" data-status="{esc(status)}">'
            f'<h3>{esc(title)}</h3><p><span class="badge">{esc(STATUS_LABEL.get(status, status))}</span></p>{"".join(pictures)}'
            f'{source_line}{checks}{engine}{copies}{_quote_block(record)}{_rights(record)}{reason}</li>')


# ------------------------------------------------------------------------------------------------ build
def _storyboard_summary(root):
    import gamearts_storyboard as storyboard
    if not storyboard.exists(root):
        return None
    data = storyboard.load(root)
    return {"title": data["title"], "sequence": data["sequence"]["status"], "scenes": data["scenes"],
            "order": data["sequence"]["order"], "waiting": storyboard.next_scenes(root)}


def build(game_root, now=None):
    """Write the report and its previews; returns {"path", "counts", "next_steps", "problems"}. Problems are listed on the page too."""
    import gamearts_asset_lifecycle as lifecycle
    root = common.game_root(game_root)
    folder = root / REPORT
    previews = folder / "previews"
    problems = []
    try:
        settings, _, _ = common.load_project_settings(root, require_confirmed=False)
        state = settings.get("settings_status", "inferred")
    except common.DependencyMissing:
        raise
    except ValueError as exc:
        settings, state = None, "missing"
        if (root / ".gamearts" / "project.json").is_file():
            problems.append(f"The settings could not be read: {exc}")
    mockups, assets = lifecycle.records(root, "mockups"), lifecycle.records(root, "assets")
    try:
        board = _storyboard_summary(root)
    except ValueError as exc:
        board = None
        problems.append(f"The storyboard could not be read: {exc}")
    pixel_art = bool(settings) and settings["art_style"]["id"] == "pixel_art"
    checks = {"mockups": lifecycle.reconcile_mockups(root), "assets": lifecycle.reconcile_assets(root)}
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    game = settings.get("project_id") if settings else root.name

    written = set()
    live_assets = [a for a in assets if a.get("status") != "revoked"]
    live_mockups = [m for m in mockups if m.get("status") != "revoked"]
    gone = [m for m in mockups if m.get("status") == "revoked"] + [a for a in assets if a.get("status") == "revoked"]

    def cards(kind, rows):
        if not rows:
            return f'<p class="muted">No {kind} yet.</p>'
        built = []
        for row in rows:
            if kind == "mockups":
                built.append(mockup_card(row, root, folder, pixel_art))
            else:
                built.append(asset_card(row, root, folder, previews, pixel_art, problems, written))
        return f'<ul class="cards">{"".join(built)}</ul>'

    steps = next_steps(state, mockups, assets, board)
    sections = [f'<section aria-labelledby="next"><h2 id="next">What happens next</h2><ol>{"".join(f"<li>{esc(s)}</li>" for s in steps)}</ol></section>']
    if settings:
        rows = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in describe_settings(settings))
        notes = "" if presets.resolve_engine_target(settings).get("problem") else "".join(
            f"<li><strong>{esc(n['topic'])}.</strong> {esc(n['text'])}</li>" for n in presets.integration_notes(settings))
        guidance = f'<h3>Notes for using the files in your engine or tool</h3><ul>{notes}</ul>' if notes else ""
        sections.append(f'<section aria-labelledby="settings"><h2 id="settings">Your settings</h2><dl>{rows}</dl>{guidance}</section>')
    else:
        sections.append('<section aria-labelledby="settings"><h2 id="settings">Your settings</h2><p class="muted">This game has no saved art settings yet.</p></section>')
    if board:
        items = "".join(f'<li data-scene="{esc(s["id"])}" data-status="{esc(s["status"])}"><strong>{esc(s["title"])}</strong> '
                        f'<span class="muted">{esc(s["status"].replace("_", " "))}</span></li>' for s in board["scenes"])
        sections.append(f'<section aria-labelledby="storyboard"><h2 id="storyboard">Storyboard: {esc(board["title"])}</h2>'
                        f'<p class="muted">Order: {esc(board["sequence"])}</p><ol>{items}</ol></section>')
    sections.append(f'<section aria-labelledby="mockups"><h2 id="mockups">Mockups</h2>{cards("mockups", live_mockups)}</section>')
    sections.append(f'<section aria-labelledby="assets"><h2 id="assets">Art made from the mockups</h2>{cards("assets", live_assets)}</section>')
    if gone:
        withdrawn = "".join((mockup_card(r, root, folder, pixel_art) if "mockup_id" in r else asset_card(r, root, folder, previews, pixel_art, problems, written)) for r in gone)
        sections.append(f'<section aria-labelledby="withdrawn"><h2 id="withdrawn">Withdrawn</h2><details><summary>{len(gone)} withdrawn item(s); '
                        f'they are kept but never used again</summary><ul class="cards">{withdrawn}</ul></details></section>')
    lines = []
    for kind, result in checks.items():
        verdict = "consistent" if result["status"] == "consistent" else "needs attention"
        lines.append(f'<li>{esc(kind)}: {esc(verdict)}' + ("" if result["status"] == "consistent" else
                     "<ul>" + "".join(f'<li class="problem">{esc(_short(i))}</li>' for i in result["issues"][:10]) + "</ul>") + "</li>")
    for problem in problems:
        lines.append(f'<li class="problem">{esc(_short(problem))}</li>')
    sections.append(f'<section aria-labelledby="records"><h2 id="records">Records check</h2><ul>{"".join(lines)}</ul></section>')

    page = (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(game)} — art report</title><style>{CSS}</style></head><body>'
            f'<header><h1>{esc(game)}</h1><p class="meta">Game Arts report, built {esc(stamp)} from the game\'s records. It shows only what the records hold; '
            f'pictures with a magenta background are shown over a checkerboard here, and the files themselves are never changed.</p></header>'
            f'<main>{"".join(sections)}</main>'
            f'<footer>Ask the agent to “update the art report” to rebuild this page. It is a derived file and is kept out of version control.</footer></body></html>\n')
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "index.html"
    common.atomic_write_bytes(target, page.encode("utf-8"))
    if previews.is_dir():
        for stale in sorted(p for pattern in ("*.png", "*.gif") for p in previews.glob(pattern) if p.name not in written):  # previews of assets that no longer exist
            stale.unlink()
    return {"path": str(target), "counts": {"mockups": len(mockups), "assets": len(assets), "withdrawn": len(gone)},
            "next_steps": steps, "problems": problems, "records": {kind: r["status"] for kind, r in checks.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.game_root), indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, ImportError) as exc:
        print("BLOCKED", f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
