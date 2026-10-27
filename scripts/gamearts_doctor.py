#!/usr/bin/env python3
"""Game Arts environment doctor: is this machine and this game ready, and if not, what exactly fixes it.

Run internally by the agent at first use and whenever a script stops on a missing package, interpreter or folder:
  python scripts/gamearts_doctor.py --game-root GAME

It only looks. It never installs a package, edits a file or creates a folder in the game; each problem comes with the fix to
hand to the user in plain words. It runs with the standard library alone, so it still works when Pillow or jsonschema is missing.
Exit status: 0 when nothing blocks work, 1 when something does.
"""
import argparse
import importlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import gamearts_presets as presets  # noqa: E402

MINIMUM_PYTHON = (3, 11)
PACKAGES = (("PIL", "Pillow"), ("jsonschema", "jsonschema"))
INTERPRETER_NAMES = ("python", "python3", "py")


def check(name, status, detail, fix=None):
    """One finding. status: ok, info (worth knowing), warn (works but should be looked at), fail (blocks work)."""
    item = {"name": name, "status": status, "detail": detail}
    if fix:
        item["fix"] = fix
    return item


def _can_write(folder):
    """True when a file can be created and removed in `folder` (which must exist)."""
    probe = Path(folder) / f".doctor-write-test-{os.getpid()}"
    try:
        probe.write_bytes(b"")
    except OSError:
        return False
    probe.unlink()
    return True


def _nearest_existing(path):
    path = Path(path)
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def check_python(version):
    found = ".".join(str(part) for part in version[:3])
    if tuple(version[:2]) < MINIMUM_PYTHON:
        return check("python", "fail", f"Python {found} is older than {'.'.join(map(str, MINIMUM_PYTHON))}",
                     f"Install Python {'.'.join(map(str, MINIMUM_PYTHON))} or newer and run the scripts with it")
    return check("python", "ok", f"Python {found} at {sys.executable}")


def check_packages(importer):
    findings = []
    for module, package in PACKAGES:
        try:
            loaded = importer(module)
        except ImportError:
            findings.append(check(package.lower(), "fail", f"{package} is not installed for this Python",
                                  f'Run: "{sys.executable}" -m pip install {package}'))
            continue
        findings.append(check(package.lower(), "ok", f"{package} {getattr(loaded, '__version__', 'is installed')}"))
    return findings


def check_interpreters(which):
    found = [name for name in INTERPRETER_NAMES if which(name)]
    if not found:
        return check("interpreter command", "warn", "None of python, python3 or py is on the PATH of this shell",
                     "Use the full path of the interpreter, or add Python to the PATH")
    return check("interpreter command", "info", f"On the PATH: {', '.join(found)}. Hooks and other tools that need a command name should use one of these.")


def check_game_folder(root, can_write):
    if not root.is_dir():
        return [check("game folder", "fail", f"{root} is not a folder", "Open the agent in the game's own folder or pass the right --game-root")]
    findings = [check("game folder", "ok", str(root))]
    marker = root / ".gamearts"
    target = marker / "system" if (marker / "system").is_dir() else marker if marker.is_dir() else _nearest_existing(marker)
    if can_write(target):
        findings.append(check("write access", "ok", f"Files can be written in {target.relative_to(root) if target != root else '.'}"))
    else:
        findings.append(check("write access", "fail", f"Files cannot be written in {target}",
                              "Close any program that has the folder locked, or fix its permissions; Game Arts cannot save settings or art until it can write there"))
    return findings


def check_settings(root):
    path = root / ".gamearts" / "project.json"
    if not path.is_file():
        return [check("settings", "warn", "This game has no Game Arts settings yet", "Run the short setup (\"Set up Game Arts for this game\")")]
    try:
        settings, _, _ = common.load_project_settings(root, require_confirmed=False)
    except common.DependencyMissing as exc:
        return [check("settings", "fail", f"The settings cannot be checked: {exc}", "Install the missing package first (see above)")]
    except ValueError as exc:
        return [check("settings", "fail", f"project.json is not valid: {exc}", "Have the setup repair the settings; nothing is registered until they are valid")]
    findings = []
    if settings.get("settings_status") == "owner_confirmed":
        findings.append(check("settings", "ok", "Settings are valid and confirmed by the owner"))
    else:
        findings.append(check("settings", "warn", f"Settings are valid but {settings.get('settings_status', 'not confirmed')}",
                              "Show the owner the settings and ask for one confirmation; mockups cannot be registered before that"))
    generator = settings.get("image_generation")
    if generator:
        findings.append(check("image generator", "info", f"Saved choice: {generator['tool']}"
                              + (f" ({generator['tool_name']})" if generator.get("tool_name") else "")
                              + ". Whether this session has that tool is for the agent to check against its own tools."))
    else:
        findings.append(check("image generator", "warn", "No image generator is saved for this game",
                              "Ask the owner once which image generator to use and save the answer"))
    engine = presets.resolve_engine_target(settings)
    if engine.get("problem"):
        findings.append(check("engine profile", "fail", engine["problem"], "Restore the damaged profile file from the framework"))
    elif engine["found"]:
        findings.append(check("engine profile", "ok", f"{engine['title']} profile"))
    else:
        findings.append(check("engine profile", "info", engine["message"]))
    return findings


def check_presets():
    findings = []
    for loader, label in ((presets.style_presets, "style presets"), (presets.engine_profiles, "engine profiles")):
        try:
            count = len(loader())
        except ValueError as exc:
            findings.append(check(label, "fail", str(exc), "Restore the damaged file from the framework (the updater replaces files you have not edited)"))
            continue
        if count:
            findings.append(check(label, "ok", f"{count} installed"))
        else:
            findings.append(check(label, "warn", "None are installed", "Update the framework files in this game; the setup offers presets from them"))
    return findings


def check_updater(root):
    state = root / ".gamearts" / "system" / "agent-sync-state.json"
    if not state.is_file():
        return check("updater", "info", "The automatic updater is not set up for this game; the framework files are as they were installed")
    try:
        data = common.read_json(state)
    except ValueError as exc:
        return check("updater", "warn", f"The updater state cannot be read: {exc}", "Ask for \"Update my installed Game Arts skills now\" to rebuild it")
    conflicts = len(data.get("conflicts") or [])
    if conflicts:
        return check("updater", "warn", f"{conflicts} framework file(s) were edited locally and were kept as they are",
                     "Tell the owner which files differ from the framework's; they decide whether to keep their edit")
    return check("updater", "ok", f"Last synchronized revision {str(data.get('revision') or 'unknown')[:12]}")


def run(game_root, importer=importlib.import_module, version=None, which=shutil.which, can_write=_can_write):
    """Collect every finding. The probes are parameters so tests can simulate a missing package or a locked folder."""
    root = Path(game_root).resolve()
    findings = [check_python(version or sys.version_info), *check_packages(importer), check_interpreters(which)]
    findings += check_game_folder(root, can_write)
    if root.is_dir():
        findings += check_settings(root)
        findings += check_presets()
        findings.append(check_updater(root))
    blocking = [f for f in findings if f["status"] == "fail"]
    attention = [f for f in findings if f["status"] == "warn"]
    status = "blocked" if blocking else "needs_attention" if attention else "ready"
    first = (blocking or attention or [None])[0]
    return {"status": status, "checks": findings,
            "next_step": first["fix"] if first and first.get("fix") else "Nothing needs fixing; carry on with the art task."}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.game_root)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
