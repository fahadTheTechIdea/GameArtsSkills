#!/usr/bin/env python3
"""The setup wizard: every setting of a game is a question the owner answers by choosing, never a value the agent fills in.

  python scripts/gamearts_setup.py show   --game-root GAME                      # the whole wizard: every question, its prompt, its options, what is answered
  python scripts/gamearts_setup.py next   --game-root GAME                      # the next unanswered question, ready to show
  python scripts/gamearts_setup.py answer --game-root GAME --id QUESTION --value OPTION --said "<the owner's own words>" [--text WORDS]
  python scripts/gamearts_setup.py status --game-root GAME                      # answered, unanswered, complete or not
  python scripts/gamearts_setup.py finish --game-root GAME                    # write project.json from the answers (complete wizards only)

An agent shows each question exactly as `next` gives it (the `prompt` and the numbered `options`, using its own choice control where it has one), records the
owner's pick with `answer`, and asks again until `status` says complete. Nothing is assumed: an unanswered question has no value, `finish` refuses while any
is open, and `confirm-settings` refuses settings the wizard did not write. The answers wait in `.gamearts/system/setup_answers.json` until `finish`, so no
half-answered or placeholder `project.json` ever exists. A question changes what later questions ask (the world kind decides the viewpoint, the scale and
the screen), so answering it again resets only the questions that depend on it. Changing an existing game's settings goes through the same wizard.
"""
import argparse
import functools
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import gamearts_presets as presets  # noqa: E402

STATE = Path(".gamearts") / "system" / "setup_answers.json"
OTHER = "other"  # the option that takes the owner's own words (`--text`)

WORLD_KINDS = [
    ("grid_world", "A tile map", "The world is a grid of tiles with a ground: farming and life sims, roguelikes, tactics, city builders, top-down adventures."),
    ("free_world", "Free movement, no tiles", "Characters move through continuous space: platformers, fighting games, shooters, side-scrolling action."),
    ("layered_scene", "Scrolling layers", "Parallax backgrounds that scroll at different speeds: endless runners, side-scrollers with painted backdrops."),
    ("screen_space", "No ground world at all", "Screens and menus only: card games, match-3, puzzle, visual novels, idle games."),
]
# value: (grid, camera_profile, label, description, object_camera, ground_camera, tile choices (px) for a tile map)
VIEWS = {
    "oblique": ("orthogonal_square", "orthogonal_3_4_oblique", "Seen from above and a little in front",
                "The fronts of walls and objects show, as in most farming sims and top-down RPGs.",
                "elevated 3/4 top-down oblique orthographic, non-isometric; square footprints, flat roofs, vertical walls",
                "orthogonal ground grid seen from the same elevated angle", [(16, 16), (32, 32), (48, 48), (64, 64)]),
    "top_down": ("orthogonal_square", "top_down", "Straight down",
                 "Roofs and floors only, no fronts.", "directly or nearly overhead, orthographic", "orthogonal ground grid seen from directly above",
                 [(16, 16), (32, 32), (48, 48), (64, 64)]),
    "side": ("orthogonal_square", "side", "From the side", "Side-on, no top faces, as in a platformer.",
             "side-view orthographic, no top faces", "logical depth grid drawn as a side-on ground plane", [(16, 16), (32, 32), (48, 48), (64, 64)]),
    "isometric": ("isometric", "isometric_3_4", "Isometric diamonds", "Diamond tiles seen at an angle, as in tactics games. Give your own angle in your own words if it is not the standard one.",
                  "isometric 3/4 orthographic, 2:1 diamond grid", "2:1 diamond ground grid", [(64, 32), (128, 64), (256, 128)]),
}
DIRECTIONS = [
    ("dirs_8", "Eight directions", "Characters face all eight ways."),
    ("dirs_4", "Four directions", "Up, down, left, right."),
    ("dirs_2_side", "Left and right", "Side views."),
    ("dirs_1_side", "One side only", "The game mirrors it for the other side where the art stays correct."),
    ("dirs_1_front", "One front view", "Always facing the viewer."),
    ("per_object", "Decide for each object", "Saved as eight directions; static things and interface art never use it."),
]
ANIMATION = [
    ("hybrid", "Let Game Arts choose", "Frames where they read best, moving parts where they save work."),
    ("frame_based", "Frame by frame", "Every pose is a picture."),
    ("transform_based", "Moving parts", "Cut-out pieces moved and rotated by the game."),
]
IMAGE_TOOLS = [
    ("built_in_image_gen", "My agent's own image tool", "Only if your coding agent has one (Codex's image_gen does)."),
    ("cli_image_gen", "Codex's command-line image tool", "Needs an OpenAI API key."),
    ("connected_tool", "A connected tool I name", "A connector or plugin you have set up; you will be asked its name."),
    ("user_supplied", "I make the pictures myself", "You hand the pictures in; the agent never generates any."),
]
SCREENS = [("1280x720", "1280 x 720", "Small landscape screen."), ("1920x1080", "1920 x 1080", "Full-HD landscape."),
           ("1080x1920", "1080 x 1920", "Phone portrait."), ("2560x1440", "2560 x 1440", "Large landscape.")]
SCALING = [("fit", "Fit the window", "Scale to fit and keep the proportions."), ("integer", "Whole-number steps", "Crisp pixels: only 1x, 2x, 3x ..."),
           ("stretch", "Stretch to fill", "Fill the window; proportions may change."), ("none", "No scaling", "Always the base size.")]
SCALES = [("16", "16 pixels per meter", "Small, simple art."), ("32", "32 pixels per meter", "Medium detail."), ("64", "64 pixels per meter", "Rich detail."),
          ("128", "128 pixels per meter", "Very detailed art.")]
LAYER_STACKS = {
    "3": [("sky", [0, 0]), ("midground", [0.5, 0.1]), ("foreground", [1.2, 1])],
    "5": [("sky", [0, 0]), ("far_background", [0.15, 0.05]), ("midground", [0.4, 0.1]), ("near_background", [0.7, 0.3]), ("foreground", [1.2, 1])],
    "7": [("sky", [0, 0]), ("clouds", [0.05, 0]), ("mountains", [0.15, 0.05]), ("hills", [0.35, 0.1]), ("far_trees", [0.55, 0.2]),
          ("near_backdrop", [0.75, 0.4]), ("foreground", [1.2, 1])],
}
PALETTE = [("words", "Describe it in words", "For example: warm earth tones, at most 32 colours. You will be asked for the description."),
           ("picture", "Use a palette picture", "A picture of your colours; you will be asked for its path and the colours are read from it."),
           ("none", "No fixed palette", "Recorded as your choice, so it is never an oversight.")]
SOFT_EDGES = [("hard", "Keep the delivered edges hard", "Soft coverage is kept separately wherever your image tool can return true alpha, so nothing is lost silently."),
              ("matte", "Deliver a soft-edge companion", "A matte picture beside each sheet; needs an image tool that returns true alpha. The runtime export turns it into real soft alpha.")]
SOFT_EDGE_RULES = {"hard": "Soft edges: delivered pictures keep hard edges; any soft coverage is kept separately and never claimed to be recovered from the key colour.",
                   "matte": "Soft edges: deliver a companion matte (<name>.matte.png) beside each key sheet where the image tool returns true alpha."}
ORDER = ["project_name", "world_kind", "look", "soft_edges", "viewpoint", "tile_size", "scale", "layers", "screen_size", "screen_scaling", "directions", "animation",
         "image_generator", "image_fallback", "engine", "palette"]
DEPENDS = {"look": {"world_kind"}, "soft_edges": {"look"}, "viewpoint": {"world_kind"}, "tile_size": {"world_kind", "viewpoint"}, "scale": {"world_kind", "viewpoint"},
           "layers": {"world_kind"}, "image_fallback": {"image_generator"}, "screen_size": {"world_kind"}, "screen_scaling": {"world_kind"}, "directions": {"world_kind"}}


@functools.lru_cache(maxsize=None)
def _styles():
    """The installed looks, read and checked once per run: every question asks for them again."""
    return presets.style_presets()


@functools.lru_cache(maxsize=None)
def _engines():
    return presets.engine_profiles()


def _opts(items):
    return [{"value": value, "label": label, "description": description} for value, label, description in items]


def _value(answers, question):
    return (answers.get(question) or {}).get("value")


def _kind(answers):
    return _value(answers, "world_kind")


def _look_options(answers):
    kind = _kind(answers)
    found = [(name, entry["title"], entry["description"]) for name, entry in sorted(_styles().items()) if kind in entry["world_kinds"]]
    return _opts(found) + [{"value": OTHER, "label": "Something else", "description": "Describe the look in your own words; you will be asked for it."}]


def _soft(answers):
    """Whether the chosen look has soft edges: a look of the owner's own words is asked too, because nothing says it has none."""
    chosen = _value(answers, "look")
    if chosen is None:
        return False
    return chosen == OTHER or bool(_styles()[chosen].get("soft_edges"))


def question(name, answers):
    """The question with this id as the wizard shows it now, or None when this game's answers make it not apply."""
    kind = _kind(answers)
    has_ground = kind in ("grid_world", "free_world", "layered_scene")
    if name == "project_name":
        return {"id": name, "header": "Name", "prompt": "What is your game called? It becomes the short name that starts every file Game Arts makes.",
                "options": [{"value": "name", "label": "Type the name", "description": "Give it with --text; it is saved as a short lowercase name of letters, digits and hyphens."}]}
    if name == "world_kind":
        return {"id": name, "header": "World", "prompt": "What kind of world does your game have?", "options": _opts(WORLD_KINDS)}
    if kind is None:
        return None
    if name == "look":
        return {"id": name, "header": "Look", "prompt": "Which look do you want for the art?", "options": _look_options(answers)}
    if name == "soft_edges" and _soft(answers):
        return {"id": name, "header": "Soft edges", "prompt": "Your look has soft painted edges, and the opaque magenta-keyed pictures Game Arts delivers cannot store them. What should happen to the softness?",
                "options": _opts(SOFT_EDGES)}
    if name == "viewpoint" and has_ground:
        keys = ["side", "oblique", "top_down"] if kind == "layered_scene" else list(VIEWS)
        options = _opts((key, VIEWS[key][2], VIEWS[key][3]) for key in keys)
        return {"id": name, "header": "Viewpoint", "prompt": "From where does the player see the world?", "options": options}
    view = VIEWS.get(_value(answers, "viewpoint"))
    if name == "tile_size" and kind == "grid_world" and view:
        options = _opts((f"{w}x{h}", f"{w} x {h} pixels", "One tile.") for w, h in view[6])
        options.append({"value": OTHER, "label": "Another size", "description": "Give it as WIDTHxHEIGHT in pixels, for example 48x48."})
        return {"id": name, "header": "Tile size", "prompt": "How big is one tile on the ground, in pixels?", "options": options}
    if name == "scale" and kind in ("free_world", "layered_scene") and view:
        return {"id": name, "header": "Scale", "prompt": "How many art pixels make one meter of your world?", "options": _opts(SCALES)}
    if name == "layers" and kind == "layered_scene":
        options = _opts((count, f"{count} layers", ", ".join(layer for layer, _ in stack)) for count, stack in LAYER_STACKS.items())
        return {"id": name, "header": "Layers", "prompt": "How many background layers scroll behind the action? You can rename and retune them later.", "options": options}
    if name == "screen_size" and kind == "screen_space":
        options = _opts(SCREENS) + [{"value": OTHER, "label": "Another size", "description": "Give it as WIDTHxHEIGHT in pixels."}]
        return {"id": name, "header": "Screen", "prompt": "What is the base size of your screen, in pixels?", "options": options}
    if name == "screen_scaling" and kind == "screen_space":
        return {"id": name, "header": "Scaling", "prompt": "How should the screen scale to the window?", "options": _opts(SCALING)}
    if name == "directions" and kind != "screen_space":
        return {"id": name, "header": "Facing", "prompt": "How many directions do your characters face?", "options": _opts(DIRECTIONS)}
    if name == "animation":
        return {"id": name, "header": "Movement", "prompt": "How should movement be animated?", "options": _opts(ANIMATION)}
    if name == "image_generator":
        return {"id": name, "header": "Images", "prompt": "Which image generator should Game Arts use for this game? It is used for every picture.",
                "options": _opts(IMAGE_TOOLS)}
    if name == "image_fallback" and answers.get("image_generator", {}).get("value") not in (None, "user_supplied"):
        main = answers["image_generator"]["value"]
        options = [{"value": "none", "label": "No fallback", "description": "If my chosen tool is not available in a session, the agent says so and stops; it never uses another."}]
        options += _opts([t for t in IMAGE_TOOLS if t[0] not in ("user_supplied", main)])
        return {"id": name, "header": "Fallback", "prompt": "If that image generator is not available in a session, is there another one Game Arts may use instead? It is used only then, and the picture records why.",
                "options": options}
    if name == "engine":
        found = [(key, profile["title"], profile["summary"]) for key, profile in sorted(_engines().items())]
        options = _opts(found) + [{"value": OTHER, "label": "Another engine", "description": "Name it; everything works as before and no profile is applied."}]
        return {"id": name, "header": "Engine", "prompt": "Which engine or tool will use this art? 'Generic' means none yet, with plain guidance and no engine assumed.",
                "options": options}
    if name == "palette":
        return {"id": name, "header": "Palette", "prompt": "Do you have a fixed palette of colours?", "options": _opts(PALETTE)}
    return None


def applicable(answers):
    return [question(name, answers) for name in ORDER if question(name, answers) is not None]


def unanswered(answers):
    return [q["id"] for q in applicable(answers) if q["id"] not in answers]


def _needs_text(name, value):
    return value == OTHER or (name in ("image_generator", "image_fallback") and value == "connected_tool") or (name == "palette" and value in ("words", "picture")) or name == "project_name"


def _split_size(text, what):
    try:
        width, height = (int(part) for part in str(text).lower().replace(" ", "").split("x"))
    except ValueError:
        raise ValueError(f"{what} must be given as WIDTHxHEIGHT in pixels, for example 48x48") from None
    if width < 1 or height < 1:
        raise ValueError(f"{what} must be at least 1 x 1")
    return width, height


def check_answer(answers, name, value, text):
    """Refuse an answer that is not one of the question's options, or one that needs the owner's words and has none."""
    asked = question(name, answers)
    if asked is None:
        raise ValueError(f"The question {name!r} does not apply to this game yet; answer {ORDER[0]!r} first or check `next`")
    if value not in {option["value"] for option in asked["options"]}:
        raise ValueError(f"{value!r} is not one of the options of {name!r}: {', '.join(option['value'] for option in asked['options'])}")
    if _needs_text(name, value) and not (text or "").strip():
        raise ValueError(f"{name} {value!r} needs the owner's own words: pass --text")
    if name in ("tile_size", "screen_size") and value == OTHER:
        _split_size(text, "the size")
    if name == "project_name":
        project_slug(text)
    if name == "engine" and value == OTHER:
        engine_slug(text)


def project_slug(text):
    """The game's name as the short lowercase name that prefixes its files: spaces become hyphens, anything but letters, digits and hyphens is refused."""
    slug = "-".join(str(text or "").strip().lower().split())
    if not common.SLUG.fullmatch(slug):
        raise ValueError(f"{text!r} cannot be a project name; use letters, digits and hyphens (for example Sunny Farm becomes sunny-farm)")
    return slug


ENGINE_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")  # the contract's pattern for engine_target.profile (schemas/gamearts-project.schema.json)


def engine_slug(text):
    """An engine the owner names in their own words as the profile name the settings keep: lowercase, spaces become hyphens ("Some Engine 4" is some-engine-4), anything else
    outside letters, digits, hyphens and underscores is refused here, when the owner answers, and not later when the settings are written."""
    slug = "-".join(str(text or "").strip().lower().split())
    if not ENGINE_NAME.fullmatch(slug):
        raise ValueError(f"{text!r} cannot be an engine name; use letters, digits, hyphens and underscores (for example Some Engine 5 becomes some-engine-5)")
    return slug


def check_palette_picture(root, text):
    """The palette picture the owner named must be there and be a picture, now, so the wizard never reports complete for a settings file that cannot be written."""
    from PIL import Image
    source = Path(text.strip())
    source = source if source.is_absolute() else Path(root) / source
    if not source.is_file():
        raise ValueError(f"the palette picture {text.strip()!r} is not a file; give its path (relative to the game folder or absolute)")
    try:
        with Image.open(source) as opened:
            opened.load()
    except (OSError, ValueError) as exc:
        raise ValueError(f"the palette picture {text.strip()!r} cannot be read as a picture: {exc}") from exc


def state_path(root):
    return Path(root) / STATE


def load_answers(root):
    path = state_path(root)
    return common.read_json(path)["answers"] if path.is_file() else {}


def answer(root, name, value, text=None, said=None):
    """Record the owner's choice with their own words, and reset the later questions that depend on it. Returns the new status."""
    if not (said or "").strip():
        raise ValueError("Record the owner's own words behind this pick (--said); a choice is never made for them")
    answers = load_answers(root)
    check_answer(answers, name, value, text)
    if name == "palette" and value == "picture":
        check_palette_picture(root, text)
    same = (answers.get(name) or {}).get("value") == value and (answers.get(name) or {}).get("text") == ((text or "").strip() or None)
    if same:  # choosing the same thing again changes no pick, so the questions that depend on it keep their answers; the owner's words are still recorded
        answers[name]["said"] = said.strip()
        common.atomic_write_json(state_path(root), {"schema_version": "1.0", "answers": answers})
        return status(root)
    answers[name] = {"value": value, "said": said.strip(), "answered_at": datetime.now(timezone.utc).isoformat(), **({"text": text.strip()} if text and text.strip() else {})}
    for dependent, needs in DEPENDS.items():
        if name in needs and dependent in answers and dependent != name:
            del answers[dependent]
    for gone in [key for key in answers if question(key, answers) is None]:  # answers to questions this game no longer asks
        del answers[gone]
    common.atomic_write_json(state_path(root), {"schema_version": "1.0", "answers": answers})
    return status(root)


def version(answers):
    """A short citable version of the picks (12 hex characters): the values and the owner's typed details, not the words or the times, so showing it to the
    owner and confirming it later tie the confirmation to exactly these settings."""
    picks = {key: {"value": item["value"], **({"text": item["text"]} if item.get("text") else {})} for key, item in sorted(answers.items())}
    return hashlib.sha256(json.dumps(picks, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


TRIGGERS = {"project_name": "always", "world_kind": "always", "look": "after the world kind", "soft_edges": "when the chosen look has soft edges, or is your own words",
            "viewpoint": "for a tile map, free movement or scrolling layers", "tile_size": "for a tile map, after the viewpoint",
            "scale": "for free movement or scrolling layers, after the viewpoint", "layers": "for scrolling layers", "screen_size": "for a screen-only game",
            "screen_scaling": "for a screen-only game", "directions": "for every game with a world", "animation": "always", "image_generator": "always", "image_fallback": "when you chose an image generator, to say what to use if it is unavailable",
            "engine": "always", "palette": "always"}


def status(root):
    answers = load_answers(root)
    open_questions = unanswered(answers)
    return {"complete": not open_questions, "answered": [key for key in ORDER if key in answers], "unanswered": open_questions, "version": version(answers)}


def _existing(root):
    path = Path(root) / ".gamearts" / "project.json"
    return common.read_json(path) if path.is_file() else None


def _current(root, name):
    """What an existing game's settings hold for a question, so the wizard can mark that option; never counted as an answer."""
    held = _existing(root)
    if not held:
        return None
    if name == "world_kind":
        return held.get("world_kind", "grid_world")
    if name == "look":
        return (held.get("art_style") or {}).get("preset")
    if name == "directions" and isinstance(held.get("directions"), str):
        return held["directions"]
    if name == "animation":
        return (held.get("animation") or {}).get("preferred_method")
    if name == "image_generator":
        return (held.get("image_generation") or {}).get("tool")
    if name == "image_fallback":
        generation = held.get("image_generation") or {}
        return (generation.get("fallback") or {}).get("tool", "none") if generation.get("tool") else None
    if name == "engine":
        return (held.get("engine_target") or {}).get("profile")
    if name == "project_name":
        return "name" if held.get("project_id") else None
    world, screen = held.get("world") or {}, held.get("screen") or {}
    if name == "viewpoint":
        return next((key for key, view in VIEWS.items() if view[1] == world.get("camera_profile")), None)
    if name == "tile_size" and world.get("ground_tile_px"):
        size = "x".join(str(v) for v in world["ground_tile_px"])
        return size if any(size == f"{w}x{h}" for view in VIEWS.values() for w, h in view[6]) else OTHER
    if name == "scale" and held.get("world_kind", "grid_world") != "grid_world" and world.get("pixels_per_meter"):
        return str(world["pixels_per_meter"])
    if name == "layers" and world.get("layers"):
        return str(len(world["layers"])) if str(len(world["layers"])) in LAYER_STACKS else None
    if name == "screen_size" and screen.get("base_resolution_px"):
        size = "x".join(str(v) for v in screen["base_resolution_px"])
        return size if size in {value for value, _, _ in SCREENS} else OTHER
    if name == "screen_scaling":
        return screen.get("scaling")
    if name == "soft_edges":
        constraints = (held.get("prompting") or {}).get("additional_constraints") or []
        return next((key for key, rule in SOFT_EDGE_RULES.items() if rule in constraints), None)
    if name == "palette":
        reference = (held.get("art_style") or {}).get("palette_reference")
        if not reference:
            return None
        return "none" if reference == "no fixed palette (the owner's choice)" else "picture" if reference.endswith(".json") else "words"
    return None


def render(asked, current=None):
    """The question as plain text to show the owner: the prompt and the numbered options."""
    lines = [asked["prompt"]]
    for number, option in enumerate(asked["options"], 1):
        mark = "  (current setting)" if option["value"] == current else ""
        lines.append(f"  {number}. {option['label']}: {option['description']}{mark}")
    return "\n".join(lines)


def describe(root, asked):
    return {"question": asked, "current": _current(root, asked["id"]), "text": render(asked, _current(root, asked["id"]))}


def show(root):
    answers = load_answers(root)
    return {"questions": [dict(describe(root, q), answered=answers.get(q["id"])) for q in applicable(answers)], **status(root),
            "possible": [{"id": name, "appears": TRIGGERS[name]} for name in ORDER]}


def next_question(root):
    answers = load_answers(root)
    open_questions = unanswered(answers)
    if not open_questions:
        return {"complete": True, "message": "Every setting is answered; run `finish` to write the settings, then confirm them with the owner."}
    asked = question(open_questions[0], answers)
    return dict(describe(root, asked), progress=f"question {len(answers) + 1}; {len(open_questions)} left so far, and an answer can add questions", complete=False)


def build_settings(answers, root, existing=None):
    """The project settings the answers say, and nothing else. Policy constants (the mockup gate, the key colour) are the framework's own, not choices."""
    kind = _kind(answers)
    chosen = (answers["look"]["value"])
    settings = dict(existing or {})
    settings.update({"schema_version": "1.0", "project_id": project_slug(answers["project_name"]["text"])})
    if kind == "grid_world":
        settings.pop("world_kind", None)
    else:
        settings["world_kind"] = kind
    if chosen == OTHER:
        art = {"id": "custom", "reference": answers["look"]["text"]}
    else:
        preset = _styles()[chosen]
        art = dict(preset["art_style"], preset=chosen)
    palette = answers["palette"]
    if palette["value"] == "words":
        art["palette_reference"] = palette["text"]
    elif palette["value"] == "picture":
        import gamearts_palette as palette_tool
        source = Path(palette["text"])
        source = source if source.is_absolute() else Path(root) / source
        palette_tool.extract(source, "main", Path(root) / palette_tool.PALETTE_DIR, 32, Path(root))
        art["palette_reference"] = (palette_tool.PALETTE_DIR / f"main{palette_tool.SUFFIX}").as_posix()
    else:
        art["palette_reference"] = "no fixed palette (the owner's choice)"
    for keep in ("anchor",):  # the style anchor is the owner's separate decision and survives a re-run
        if keep in ((existing or {}).get("art_style") or {}):
            art[keep] = existing["art_style"][keep]
    settings["art_style"] = art
    world = None
    if kind in ("grid_world", "free_world", "layered_scene"):
        grid, camera, _label, _description, object_camera, ground_camera, _tiles = VIEWS[_value(answers, "viewpoint")]
        world = {"camera_profile": camera, "object_camera": object_camera}
        viewpoint = answers["viewpoint"]
        if viewpoint.get("text"):
            world["object_camera"] = f"{object_camera}; the owner's own words: {viewpoint['text']}"
        if kind == "grid_world":
            size = answers["tile_size"]
            width, height = _split_size(size["text"], "the tile size") if size["value"] == OTHER else _split_size(size["value"], "the tile size")
            world.update({"grid": grid, "ground_camera": ground_camera, "logical_tile_m": [1, 1], "ground_tile_px": [width, height],
                          "pixels_per_meter": width, "construction_snap_m": 1})
        else:
            world["pixels_per_meter"] = int(answers["scale"]["value"])
        if kind == "layered_scene":
            world["layers"] = [{"id": name, "scroll_scale": scale} for name, scale in LAYER_STACKS[answers["layers"]["value"]]]
        settings["world"] = world
        direction = answers["directions"]["value"]
        settings["directions"] = "dirs_8" if direction == "per_object" else direction
    else:
        settings.pop("world", None)
        settings.pop("directions", None)
        size = answers["screen_size"]
        width, height = _split_size(size["text"] if size["value"] == OTHER else size["value"], "the screen size")
        settings["screen"] = {"base_resolution_px": [width, height], "scaling": answers["screen_scaling"]["value"]}
    settings["animation"] = {"preferred_method": answers["animation"]["value"], "animated_attachment_anchors": True}
    settings["workflow"] = {"mockup_approval_required": True, "detail_decomposition_required": True}
    settings["export"] = {"background_hex": "#FF00FF", "background_alpha": 255, "atlas_per_sheet": True, "no_zip": True}
    tool = answers["image_generator"]
    settings["image_generation"] = {"tool": tool["value"], **({"tool_name": tool["text"]} if tool["value"] == "connected_tool" else {})}
    fallback = answers.get("image_fallback")
    if fallback and fallback["value"] != "none":
        settings["image_generation"]["fallback"] = {"tool": fallback["value"], **({"tool_name": fallback["text"]} if fallback["value"] == "connected_tool" else {})}
    engine = answers["engine"]
    settings["engine_target"] = {"profile": (engine_slug(engine["text"]) if engine["value"] == OTHER else engine["value"])}
    prompting = dict(settings.get("prompting") or {})
    constraints = [c for c in prompting.get("additional_constraints", []) if c not in SOFT_EDGE_RULES.values()]
    if "soft_edges" in answers:
        constraints.append(SOFT_EDGE_RULES[answers["soft_edges"]["value"]])
    if constraints:
        prompting["additional_constraints"] = constraints
    else:
        prompting.pop("additional_constraints", None)
    if prompting:
        settings["prompting"] = prompting
    else:
        settings.pop("prompting", None)
    settings["setup"] = {"answers": {key: value for key, value in answers.items()}}
    return settings


def _label(name, answers):
    asked = question(name, answers)
    value = answers[name]["value"]
    option = next((o for o in asked["options"] if o["value"] == value), None)
    return (option["label"] if option else value) + (f" ({answers[name]['text']})" if answers[name].get("text") else "")


def summary(answers):
    """The owner's picks in plain words and what each one means for the work, to show them the written settings before they confirm."""
    lines = [f"{question(name, answers)['header']}: {_label(name, answers)}" for name in ORDER if name in answers]
    tool = answers["image_generator"]["value"]
    lines.append({"user_supplied": "Consequence: Game Arts generates no pictures; it prepares requests and imports the files you make.",
                  "built_in_image_gen": "Consequence: every picture is made with your agent's own image tool; the agent never substitutes another.",
                  "cli_image_gen": "Consequence: every picture is made with Codex's command-line image tool, which needs an OpenAI API key.",
                  "connected_tool": "Consequence: every picture is made with the connected tool you named, which may charge for each picture."}[tool])
    if "image_fallback" in answers:
        lines.append("Consequence: if that tool is not available in a session, " + ("the agent says so and stops; it never uses another." if answers["image_fallback"]["value"] == "none"
                     else "the fallback you named is used instead and each picture records why."))
    engine = answers["engine"]["value"]
    lines.append("Consequence: plain guidance for any engine, and no automatic engine-ready copies." if engine == "generic"
                 else "Consequence: import advice and default engine-ready copies come from the engine's profile where one is installed.")
    if "soft_edges" in answers:
        lines.append("Consequence: " + SOFT_EDGE_RULES[answers["soft_edges"]["value"]])
    return lines


def finish(root):
    """Write project.json from a complete wizard. Settings that were confirmed and are materially unchanged keep their confirmation; any other change needs
    the owner's confirmation again (`confirm-settings`)."""
    root = Path(root)
    answers = load_answers(root)
    open_questions = unanswered(answers)
    if open_questions:
        raise ValueError("Not every setting is answered yet: " + ", ".join(open_questions) + ". Ask them with `next`; nothing is assumed")
    existing = _existing(root)
    settings = build_settings(answers, root, existing)
    if existing and existing.get("settings_status") == "owner_confirmed":
        changed = common.canonical_settings_hash(settings) != common.canonical_settings_hash(existing)
        settings["settings_status"] = "needs_review" if changed else "owner_confirmed"
        if changed:
            settings.pop("confirmed_at", None)
            settings.pop("confirmed_by", None)
    else:
        settings["settings_status"] = "inferred"
        settings.pop("confirmed_at", None)
        settings.pop("confirmed_by", None)
    common.validate_schema(settings, "gamearts-project")
    common.atomic_write_json(root / ".gamearts" / "project.json", settings)
    return {"written": ".gamearts/project.json", "settings_status": settings["settings_status"], "version": version(answers), "summary": summary(answers),
            "next": "Show the owner a plain summary and ask them to confirm; then run confirm-settings with their words." if settings["settings_status"] != "owner_confirmed"
            else "The settings are unchanged, so the owner's earlier confirmation stands."}


def setup_problems(settings):
    """What stops these settings from counting as chosen: they carry no wizard answers, or some are missing. An empty list means the owner chose every one."""
    answers = (settings.get("setup") or {}).get("answers")
    if answers is None:
        return ["these settings were not chosen through the setup wizard (gamearts_setup.py); the owner has not answered the questions one by one"]
    return [f"setting not answered: {name}" for name in unanswered(answers)] + [f"no owner words recorded for: {name}" for name, item in answers.items() if not item.get("said")]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    for name in ("show", "next", "status", "finish", "answer"):
        sub = ops.add_parser(name)
        sub.add_argument("--game-root", type=Path, required=True)
        if name == "answer":
            sub.add_argument("--id", required=True)
            sub.add_argument("--value", required=True)
            sub.add_argument("--text")
            sub.add_argument("--said", required=True, help="The owner's own words behind this pick; never invent")
    args = parser.parse_args()
    try:
        if args.operation == "show":
            result = show(args.game_root)
        elif args.operation == "next":
            result = next_question(args.game_root)
        elif args.operation == "status":
            result = status(args.game_root)
        elif args.operation == "answer":
            result = answer(args.game_root, args.id, args.value, args.text, args.said)
        else:
            result = finish(args.game_root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print("BLOCKED", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
